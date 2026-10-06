"""
具体转场手法识别（低成本多模态）

video_features 只能量化“切得快不快、是否踩点”。对其中的高潜力视频（卡点剪辑 / 快切转场），
这里再做一步视觉识别：
  1. 选最多 6 个切点，各取切点前 0.3 秒、后 0.2 秒两帧（240px 宽 JPEG）；
  2. 一次请求交给视觉模型，判断每个切点的转场手法、触发动作与变化内容；
  3. 模型同时给出人类可读的玩法名（如“跺脚换装”），同名 / 同手法的视频聚成“玩法模板”。
每个视频只识别一次（缓存），每天有调用上限（PULSE_VISION_PER_DAY，默认 40）。
"""

import base64
import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from loguru import logger

from . import llm, metrics, storage
from .config import settings

TRANSITION_TYPES = ["动作触发换装", "遮挡转场", "甩镜转场", "推拉变焦", "动作匹配", "场景匹配", "手势触发", "普通硬切", "其他"]
_SKIP_NAMES = {"", "普通硬切", "无", "其他", "普通剪辑"}


def _budget_ok() -> bool:
    key = "vision:" + time.strftime("%Y%m%d", time.gmtime(time.time() + 8 * 3600))
    used = int((storage.kv_get(key) or b"0").decode())
    if used >= int(os.getenv("PULSE_VISION_PER_DAY", "40")):
        return False
    storage.kv_set(key, str(used + 1).encode())
    return True


def _pick_cuts(cuts: List[float], duration: float, n: int = 6) -> List[float]:
    cuts = [c for c in cuts if 0.6 < c < duration - 0.3]
    if len(cuts) <= n:
        return cuts
    step = len(cuts) / n
    return [cuts[int(i * step)] for i in range(n)]


def _frame(path: str, t: float) -> Optional[str]:
    proc = subprocess.run(
        ["nice", "-n", "15", "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, t):.2f}", "-i", path,
         "-frames:v", "1", "-vf", "scale=240:-2", "-q:v", "7", "-f", "image2", "-c:v", "mjpeg", "-"],
        capture_output=True, timeout=30)
    return base64.b64encode(proc.stdout).decode() if proc.stdout else None


def analyze(path: str, bvid: str, cuts: List[float], duration: float) -> Optional[Dict]:
    if not settings.llm_ready or storage.kv_get("vtrans:" + bvid) or not _budget_ok():
        return None
    picked = _pick_cuts(cuts, duration)
    if len(picked) < 2:
        return None
    content = [{"type": "text", "text": (
        f"下面是一个短视频在 {len(picked)} 个剪辑切点前后的画面，每个切点给出“前一帧”和“后一帧”。"
        f"请逐个切点判断转场手法（从 {TRANSITION_TYPES} 选），描述触发动作（如跺脚、拍手、捂镜头、转身、甩头）"
        "和变化内容（服装 / 场景 / 人物 / 道具 / 无）。如果多个切点重复同一种可模仿的玩法，给出 8 字以内的人类可读玩法名"
        "（例如“跺脚换装”“捂镜头变装”“转身换场景”），否则留空。只输出 JSON："
        '{"cuts":[{"index":1,"type":"","trigger":"","change":"","confidence":0.0}],"template_name":"","summary":"30字内"}')}]
    for i, t in enumerate(picked, start=1):
        before, after = _frame(path, t - 0.3), _frame(path, t + 0.2)
        if not (before and after):
            continue
        content += [{"type": "text", "text": f"切点{i} 前一帧："},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + before}},
                    {"type": "text", "text": f"切点{i} 后一帧："},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + after}}]
    try:
        client = llm._get_client()
        resp = client.chat.completions.create(model=settings.llm_model, messages=[{"role": "user", "content": content}],
                                              temperature=0.1, timeout=settings.llm_timeout, max_tokens=900)
        usage = getattr(resp, "usage", None)
        metrics.incr("llm_calls")
        metrics.incr("vision_calls")
        metrics.incr("llm_prompt_tokens", getattr(usage, "prompt_tokens", 0) or 0)
        metrics.incr("llm_completion_tokens", getattr(usage, "completion_tokens", 0) or 0)
        data = llm.parse_json(resp.choices[0].message.content or "")
    except Exception as exc:
        metrics.incr("llm_failures")
        logger.warning(f"[CampusPulse] 转场识别失败 {bvid}: {exc}")
        return None
    rows = [r for r in (data.get("cuts") or []) if isinstance(r, dict)]
    for r in rows:
        if r.get("type") not in TRANSITION_TYPES:
            r["type"] = "其他"
    types = Counter(r["type"] for r in rows if (r.get("confidence") or 0) >= 0.5)
    result = {
        "cuts": rows[:6],
        "dominant": types.most_common(1)[0][0] if types else None,
        "template_name": str(data.get("template_name") or "").strip()[:12],
        "summary": str(data.get("summary") or "")[:60],
        "analyzed_at": int(time.time()),
        "tokens": getattr(usage, "prompt_tokens", 0) + getattr(usage, "completion_tokens", 0) if usage else None,
    }
    storage.kv_set("vtrans:" + bvid, json.dumps(result, ensure_ascii=False).encode("utf-8"))
    logger.info(f"[CampusPulse] 转场识别 {bvid}: {result['template_name'] or result['dominant']}")
    return result


def template_candidates(videos: List[Dict]) -> List[Dict]:
    """把本批次热门视频的转场识别结果按玩法名（否则按主手法）聚类为候选。"""
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for v in videos:
        blob = storage.kv_get("vtrans:" + (v.get("bvid") or ""))
        if not blob:
            continue
        r = json.loads(blob)
        name = r.get("template_name") or r.get("dominant") or ""
        if name in _SKIP_NAMES:
            continue
        groups[name].append({**v, "_trans": r})
    out = []
    for name, vids in groups.items():
        triggers = Counter(c.get("trigger") for v in vids for c in v["_trans"]["cuts"] if c.get("trigger"))
        types = Counter(v["_trans"].get("dominant") for v in vids if v["_trans"].get("dominant"))
        out.append({
            "key": "v:" + name, "kind": "transition", "label": f"转场玩法：{name}", "df": len(vids),
            "sources": ["bilibili-popular"],
            "examples": [v["_trans"].get("summary") or "" for v in vids[:3]],
            "video_urls": [f"https://www.bilibili.com/video/{v['bvid']}" for v in vids[:3]],
            "transition_types": dict(types),
            "triggers": [t for t, _ in triggers.most_common(4)],
            "lens": {"type": "短视频玩法", "meaning": vids[0]["_trans"].get("summary") or "", "form": "短视频转场",
                     "function": "", "student_usage": "", "crisis_level": "无", "content_risk": "无",
                     "topic_value": 2, "confidence": 0.6},
            "score": 4 * len(vids),
        })
    return out
