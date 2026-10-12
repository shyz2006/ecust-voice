"""
B 站公开数据采集 —— 短视频玩法信号

热榜标题无法反映“大家都在用、但标题没写”的玩法，这里补充视频层面的元数据：
- 热门榜：标题、简介、分区、时长、播放/点赞/分享、投稿活动 mission_id（同一挑战/活动的参与视频）
- 标签：UP 主打的话题标签（“转场”“变装”“卡点”“挑战”等玩法常出现在这里）
- BGM：视频使用的背景音乐（同一 BGM 被大量使用 = 音频模板）
- 热评：评论区的高赞句式（梗常在评论区复用）

均为公开接口、无需登录；每个视频的详情只抓一次并缓存；请求间隔 ≥0.6 秒。
抖音 / 快手的对应接口需要签名参数，这里不做绕过。
"""

import json
import re
import time
from typing import Any, Dict, List

import requests
from loguru import logger

from .. import storage
from .huyou import deidentify

API = "https://api.bilibili.com"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.bilibili.com/",
}
_EMOTE_RE = re.compile(r"\[[^\[\]]{1,8}\]")


def _get(path: str, **params) -> Any:
    resp = requests.get(API + path, params=params, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"{path} code={body.get('code')} {body.get('message')}")
    return body.get("data")


def _details(video: Dict[str, Any], n_comments: int) -> Dict[str, Any]:
    """标签 + BGM + 热评；按 bvid 缓存（这些信息发布后基本不变）。"""
    key = "bili:" + video["bvid"]
    blob = storage.kv_get(key)
    if blob:
        return json.loads(blob)
    out: Dict[str, Any] = {"tags": [], "bgm": None, "comments": []}
    try:
        out["tags"] = [t["tag_name"] for t in (_get("/x/tag/archive/tags", bvid=video["bvid"]) or [])][:12]
        time.sleep(0.6)
        bgm = _get("/x/copyright-music-publicity/bgm/entrance", aid=video["aid"], cid=video["cid"]) or {}
        info = bgm.get("music_info") or {}
        out["bgm"] = info.get("music_title") or None
        time.sleep(0.6)
        replies = (_get("/x/v2/reply", type=1, oid=video["aid"], sort=1, ps=n_comments, pn=1) or {}).get("replies") or []
        out["comments"] = [
            c for c in (deidentify(_EMOTE_RE.sub("", (r.get("content") or {}).get("message", ""))) for r in replies)
            if 2 <= len(c) <= 120
        ]
        time.sleep(0.6)
    except Exception as exc:
        logger.debug(f"[CampusPulse] B站详情获取失败 {video['bvid']}: {exc}")
        return out  # 失败不缓存，下次重试
    storage.kv_set(key, json.dumps(out, ensure_ascii=False).encode("utf-8"))
    return out


def collect(pages: int = 3, detail_top: int = 80, n_comments: int = 20) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}
    videos: List[Dict[str, Any]] = []
    for pn in range(1, pages + 1):
        try:
            videos += (_get("/x/web-interface/popular", ps=50, pn=pn) or {}).get("list") or []
            time.sleep(0.8)
        except Exception as exc:
            errors[f"bilibili:popular:{pn}"] = str(exc)[:200]
            break
    for rank, v in enumerate(videos, start=1):
        stat = v.get("stat") or {}
        extra = {
            "bvid": v.get("bvid"),
            "aid": v.get("aid"),
            "cid": v.get("cid"),
            "zone": v.get("tnamev2") or v.get("tname") or "",
            "duration": v.get("duration"),
            "mission_id": v.get("mission_id") or None,
            "desc": deidentify(v.get("desc") or "")[:200] if (v.get("desc") or "-") != "-" else "",
            "view": stat.get("view", 0),
            "like": stat.get("like", 0),
            "share": stat.get("share", 0),
            "reply": stat.get("reply", 0),
            "pubdate": v.get("pubdate"),
            "rcmd_reason": (v.get("rcmd_reason") or {}).get("content") or "",
        }
        if rank <= detail_top and extra["bvid"]:
            extra.update(_details({"bvid": extra["bvid"], "aid": extra["aid"], "cid": extra["cid"]}, n_comments))
        items.append({
            "source": "bilibili-popular",
            "rank": rank,
            "title": (v.get("title") or "").strip(),
            "url": f"https://www.bilibili.com/video/{extra['bvid']}" if extra["bvid"] else None,
            "extra": extra,
        })
    logger.info(f"[CampusPulse] B站热门：{len(items)} 个视频")
    return {"items": [i for i in items if i["title"]], "errors": errors}
