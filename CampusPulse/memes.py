"""
梗 / 短视频玩法发现（无需标题点名）

热榜标题只会写“事件”，很少写“玩法”。这里在用户生成内容（B 站标题/标签/热评、狐友帖子）
上做无监督发现，再交给 LLM 判断是不是梗：

1. 新词/流行语：字符 n-gram(2~5) 的文档频次 + 左右邻字熵（边界自由度）+ 内部凝固度（PMI），
   经典的新词发现方法；词典里已有的常用词、只出现在新闻标题里的人名/事件词会被过滤。
2. 句式模板（snowclone）：固定前缀 + 可替换槽位 + 固定后缀，如“X的尽头是Y”“谁懂啊X”；
   同一框架被 ≥3 个不同填充词使用才算。
3. 同款信号：同一 BGM / 同一投稿活动 / 同一标签被多个热门视频使用，并附带这些视频的剪辑风格
   （卡点、快切）统计 —— 这是“大家都在用、但标题没说”的玩法最直接的证据。

每个候选按批次记录出现量（meme_signals），用于展示“从出现到扩散”的过程。
"""

import math
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

try:
    import jieba

    _DICT = jieba.dt.FREQ if jieba.dt.initialized else None
except Exception:  # pragma: no cover
    jieba = None
    _DICT = None

_CN_RUN = re.compile(r"[一-鿿]{2,}")
_UGC_SOURCES = {"bilibili-title", "bilibili-tag", "bilibili-comment", "huyou-school", "huyou-national", "tieba-school"}
_GENERIC_TAGS = {
    "搞笑", "日常", "vlog", "生活", "生活记录", "记录", "娱乐", "美食", "游戏", "音乐", "知识", "科普",
    "动画", "鬼畜", "影视", "综艺", "明星", "新闻", "资讯", "必剪创作", "b站", "bilibili", "哔哩哔哩",
    "热门", "推荐", "原创", "治愈", "有趣", "干货", "教程", "学习", "旅行", "旅游", "打卡", "单机游戏",
}
_STOP_CHARS = set("的了是在和与及或被把对为从到有也就都而又很更最还并等这那其之以于上下中个我你他她它们吗呢吧啊")


# 稳定常用的口语词（jieba 词典未收录，但显然不是新梗）；人工标注“普通词”后会自动追加
_COMMON_WORDS = {"吐槽", "不知道", "点赞", "微信", "真的", "感觉", "哈哈", "哈哈哈", "好家伙", "离谱", "绝了", "破防",
                 "内卷", "躺平", "打卡", "种草", "安利", "上头", "下头", "摆烂", "emo", "yyds", "牛逼", "无语"}
# B 站投稿活动中大量是创作激励 / 官方征稿，不是学生会模仿的玩法
_INCENTIVE_RE = re.compile(r"激励|直通车|发布会|征稿|创作者|UP主|up主|资讯|开荒季|知识|科普|官方")

FEEDBACK_LABELS = {
    "confirm": "确认流行", "not_meme": "不是梗", "outdated": "过时词", "common": "普通词", "duplicate": "重复候选",
}
_BLOCK_LABELS = {"not_meme", "outdated", "common", "duplicate"}


def feedback_map() -> Dict[str, Dict]:
    """人工快捷标注：{候选 key: {label, by, ts}}"""
    import json as _json

    from . import storage

    return {r["key"]: _json.loads(r["value"]) for r in storage.kv_prefix("memefb:", limit=2000)}


def _dictionary() -> Dict[str, int]:
    global _DICT
    if _DICT is None and jieba is not None:
        jieba.initialize()
        _DICT = jieba.dt.FREQ
    return _DICT or {}


def build_docs(items: List[Dict]) -> List[Tuple[str, str]]:
    """把各来源条目展开为 (文本, 来源类型) 文档；B 站标签单独作为 bilibili-tag 文档。"""
    docs = []
    for it in items:
        src, ex = it["source"], it.get("extra") or {}
        if src == "bilibili-popular":
            docs.append((it["title"], "bilibili-title"))
            if ex.get("desc"):
                docs.append((ex["desc"], "bilibili-title"))
            docs += [(c, "bilibili-comment") for c in ex.get("comments") or []]
        elif src.startswith("huyou") or src == "tieba-school":
            docs.append((ex.get("content") or it["title"], src))
        else:
            docs.append((it["title"], "hotlist"))
    return [(t[:160], s) for t, s in docs if t]


def _entropy(counter: Counter) -> float:
    total = sum(counter.values())
    return -sum(c / total * math.log(c / total) for c in counter.values()) if total else 0.0


def discover_words(docs: List[Tuple[str, str]], min_df: int = 3, top: int = 40,
                   blocked_words: frozenset = frozenset()) -> List[Dict]:
    occ: Counter = Counter()          # n-gram(1~5) 出现次数，用于凝固度
    df: Counter = Counter()           # 文档频次
    ugc_df: Counter = Counter()
    left: Dict[str, Counter] = defaultdict(Counter)
    right: Dict[str, Counter] = defaultdict(Counter)
    sources: Dict[str, set] = defaultdict(set)
    examples: Dict[str, List[str]] = defaultdict(list)
    total = 0
    for text, src in docs:
        seen = set()
        for run in _CN_RUN.findall(text):
            total += len(run)
            for n in range(1, 6):
                for i in range(len(run) - n + 1):
                    g = run[i:i + n]
                    occ[g] += 1
                    if n >= 2:
                        left[g][run[i - 1] if i > 0 else "^"] += 1
                        right[g][run[i + n] if i + n < len(run) else "$"] += 1
                        seen.add(g)
        for g in seen:
            df[g] += 1
            sources[g].add(src)
            if src in _UGC_SOURCES:
                ugc_df[g] += 1
                if len(examples[g]) < 3:
                    examples[g].append(text[:60])
    total = max(total, 1)
    vocab = _dictionary()

    def cohesion(g: str) -> float:
        p = occ[g] / total
        return min(math.log(p / ((occ[g[:k]] / total) * (occ[g[k:]] / total))) for k in range(1, len(g)))

    cands = []
    for g, c in df.items():
        if c < min_df or ugc_df[g] < 3 or g[0] in _STOP_CHARS or g[-1] in _STOP_CHARS:
            continue
        if g in vocab or g in _COMMON_WORDS or g in blocked_words:  # 词典已收录 / 常用口语 / 人工标为普通词
            continue
        le, rt = _entropy(left[g]), _entropy(right[g])
        if min(le, rt) < 0.8 or cohesion(g) < 3.0:
            continue
        cands.append({"key": "w:" + g, "kind": "word", "label": g, "df": c, "ugc_df": ugc_df[g],
                      "sources": sorted(sources[g]), "examples": examples[g],
                      "score": ugc_df[g] * (1 + len(sources[g])) * min(le, rt)})
    cands.sort(key=lambda x: -x["score"])
    # 去掉被更长候选覆盖、频次相近的子串
    kept: List[Dict] = []
    for cand in cands:
        if any(cand["label"] in k["label"] and cand["df"] <= k["df"] * 1.3 for k in kept):
            continue
        kept = [k for k in kept if not (k["label"] in cand["label"] and k["df"] <= cand["df"] * 1.3)]
        kept.append(cand)
        if len(kept) >= top:
            break
    return kept


def discover_templates(docs: List[Tuple[str, str]], min_fillers: int = 4, top: int = 15) -> List[Dict]:
    fillers: Dict[str, set] = defaultdict(set)
    doc_hits: Dict[str, set] = defaultdict(set)
    sources: Dict[str, set] = defaultdict(set)
    examples: Dict[str, List[str]] = defaultdict(list)
    ugc_docs = [(i, t, s) for i, (t, s) in enumerate(docs) if s in _UGC_SOURCES][:2000]
    for i, text, src in ugc_docs:
        for run in _CN_RUN.findall(text[:120]):
            L = len(run)
            for a in range(L):
                for la in (2, 3):
                    if a + la > L:
                        continue
                    prefix = run[a:a + la]
                    for gap in range(1, 5):
                        for lb in (1, 2, 3):
                            b = a + la + gap
                            if b + lb > L or la + lb < 3:
                                continue
                            key = prefix + "…" + run[b:b + lb]
                            fillers[key].add(run[a + la:b])
                            doc_hits[key].add(i)
                            sources[key].add(src)
                            if len(examples[key]) < 3 and text[:60] not in examples[key]:
                                examples[key].append(text[:60])
    out = []
    for key, fs in fillers.items():
        if len(fs) < min_fillers or len(doc_hits[key]) < min_fillers:
            continue
        pre, suf = key.split("…")
        if len(pre + suf) < 4 or sum(ch not in _STOP_CHARS for ch in pre + suf) < 3:
            continue
        out.append({"key": "t:" + key, "kind": "template", "label": key.replace("…", "X"),
                    "df": len(doc_hits[key]), "fillers": sorted(fs)[:8], "sources": sorted(sources[key]),
                    "examples": examples[key], "score": len(fs) * len(doc_hits[key])})
    out.sort(key=lambda x: -x["score"])
    # 同一框架的不同截断只留最强的一个
    kept: List[Dict] = []
    for c in out:
        if any(set(c["fillers"]) & set(k["fillers"]) and (c["label"][:2] == k["label"][:2]) for k in kept):
            continue
        kept.append(c)
        if len(kept) >= top:
            break
    return kept


def _mission_name(mission_id: str) -> str:
    """B 站投稿活动名称（缓存）；取不到时退回编号。"""
    from . import storage
    import json as _json
    import requests

    key = "mission:" + mission_id
    blob = storage.kv_get(key)
    if blob:
        return _json.loads(blob)
    try:
        data = requests.get("https://api.bilibili.com/x/activity/subject/info", params={"sid": mission_id},
                            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"},
                            timeout=10).json().get("data") or {}
        name = data.get("name") or f"#{mission_id}"
    except Exception:
        return f"#{mission_id}"
    storage.kv_set(key, _json.dumps(name, ensure_ascii=False).encode("utf-8"))
    return name


def discover_video_signals(items: List[Dict], vfeat: Dict[str, Dict]) -> List[Dict]:
    videos = [it for it in items if it["source"] == "bilibili-popular"]
    groups: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for it in videos:
        ex = it.get("extra") or {}
        if ex.get("bgm"):
            groups[("bgm", ex["bgm"])].append(it)
        if ex.get("mission_id") and not _INCENTIVE_RE.search(_mission_name(str(ex["mission_id"]))):
            groups[("mission", str(ex["mission_id"]))].append(it)
        for tag in ex.get("tags") or []:
            if tag.lower() not in _GENERIC_TAGS and tag != ex.get("zone"):
                groups[("tag", tag)].append(it)
    out = []
    for (kind, name), vids in groups.items():
        if len(vids) < (2 if kind == "bgm" else 3):
            continue
        feats = [vfeat.get((v.get("extra") or {}).get("bvid")) for v in vids]
        feats = [f for f in feats if f and not f.get("error")]
        styles = Counter(f["style"] for f in feats)
        label = {"bgm": f"BGM：{name}", "mission": f"投稿活动：{_mission_name(name)}", "tag": f"#{name}"}[kind]
        out.append({
            "key": f"{kind[0]}:{name}", "kind": kind, "label": label, "df": len(vids),
            "sources": ["bilibili-popular"],
            "examples": [v["title"][:50] for v in vids[:4]],
            "video_urls": [v.get("url") for v in vids[:4]],
            "views": sum((v.get("extra") or {}).get("view", 0) for v in vids),
            "edit_styles": dict(styles), "analyzed_videos": len(feats),
            "score": len(vids) * (2 if kind != "tag" else 1) * (1 + styles.get("卡点剪辑", 0) + styles.get("快切转场", 0)),
        })
    out.sort(key=lambda x: -x["score"])
    return out[:25]


def discover(items: List[Dict], vfeat: Dict[str, Dict], feedback: Dict[str, Dict] = None) -> List[Dict]:
    feedback = feedback or {}
    blocked_words = frozenset(k[2:] for k, v in feedback.items() if k.startswith("w:") and v.get("label") in _BLOCK_LABELS)
    docs = build_docs(items)
    cands = discover_words(docs, blocked_words=blocked_words) + discover_templates(docs) + \
        discover_video_signals(items, vfeat)
    return [c for c in cands if (feedback.get(c["key"]) or {}).get("label") not in _BLOCK_LABELS]


TIERS = {
    "verified": "已验证趋势",      # 跨批次持续出现且增长 + 至少两个独立来源，或老师人工确认
    "observed": "平台实测出现",    # 本校 / 平台语料中有真实出现频次
    "lead": "外部热点线索",        # 仅博查 / 媒体提及，本校与平台样本中尚未观察到
}


def _source_groups(sources: List[str]) -> set:
    groups = set()
    for s in sources:
        if s.startswith("bilibili"):
            groups.add("bilibili")
        elif s.startswith("huyou"):
            groups.add("huyou")
        elif s.startswith("tieba-school"):
            groups.add("tieba")
        elif s == "web":
            groups.add("web")
        else:
            groups.add("hotlist")
    return groups


POLL_MIN_N, POLL_MIN_SEEN = 20, 0.3


def assign_tier(c: Dict, feedback: Dict[str, Dict], polls: Dict[str, Dict] = None) -> None:
    fb = (feedback.get(c["key"]) or {}).get("label")
    points = [p for p in c.get("timeline", []) if p["df"] > 0]
    internal = _source_groups([s for s in c.get("sources", []) if s != "web"])
    poll = (polls or {}).get(c["key"])
    c["poll"] = poll
    if poll and poll["n"] >= POLL_MIN_N and poll["seen_pct"] >= POLL_MIN_SEEN:
        internal = internal | {"poll"}  # 学生匿名问卷：校准公开社区偏差的独立来源
    growing = len(points) >= 3 and points[-1]["df"] >= points[0]["df"] and (c.get("growth") or 0) >= 1.2
    if fb == "confirm":
        c["tier"], c["tier_reason"] = "verified", "老师人工确认"
    elif c["df"] == 0 and "poll" in internal:
        c["tier"], c["tier_reason"] = "observed", f"学生问卷 {poll['n']} 人中 {round(poll['seen_pct'] * 100)}% 见过"
    elif c["df"] == 0:
        c["tier"], c["tier_reason"] = "lead", "仅外部来源提及，本校与平台样本中尚未出现"
    elif growing and len(internal | ({"web"} if c["kind"] == "web" else set())) >= 2:
        c["tier"], c["tier_reason"] = "verified", f"连续 {len(points)} 个批次出现且增长，{len(internal)} 类独立来源"
    else:
        c["tier"] = "observed"
        c["tier_reason"] = (f"已在 {len(points)} 个批次出现" + ("" if len(internal) >= 2 else "，仅单一来源")
                            + ("" if growing else "，尚无持续增长"))
    c["tier_label"] = TIERS[c["tier"]]
    c["feedback"] = fb
    # 只有平台实测出现的才可能“新出现”；外部线索永远不标新出现
    if c["tier"] == "lead":
        c["is_new"] = False


def attach_history(cands: List[Dict], history: Dict[str, List[Dict]], batch_ts: int,
                   feedback: Dict[str, Dict] = None) -> None:
    """history: {key: [{batch_ts, df}, ...]}（不含本批次）→ 首次出现时间、增长倍数、扩散时间线、证据等级。"""
    feedback = feedback or {}
    from . import storage
    polls = storage.poll_stats_by_key()
    cold_start = not any(history.values())  # 刚接入时没有任何历史，不能把所有候选都标成“新出现”
    for c in cands:
        past = history.get(c["key"], [])
        c["first_seen"] = min([p["batch_ts"] for p in past] + [batch_ts])
        recent = [p["df"] for p in past if batch_ts - p["batch_ts"] <= 86400]
        base = sum(recent) / len(recent) if recent else 0
        c["growth"] = round(c["df"] / base, 2) if base else None
        c["is_new"] = (not cold_start) and batch_ts - c["first_seen"] < 6 * 3600
        c["timeline"] = [*({"ts": p["batch_ts"], "df": p["df"]} for p in past[-47:]), {"ts": batch_ts, "df": c["df"]}]
        assign_tier(c, feedback, polls)
        tier_w = {"verified": 3.0, "observed": 1.0, "lead": 0.4}[c["tier"]]
        c["score"] = round(c["score"] * tier_w * (1.5 if c["is_new"] else 1.0)
                           * (min(c["growth"], 4) if c["growth"] else 1.0), 3)


# ------------------------------------------------------------------ LLM 精筛
MEME_TYPES = ["网络流行语", "句式模板", "短视频玩法", "BGM/音频模板", "话题挑战", "非梗"]


def annotate_candidates(cands: List[Dict], use_llm: bool, max_new: int = 24, batch_size: int = 12) -> List[Dict]:
    """统计召回的候选交给 LLM 判断是否为梗；判断结果按 key 缓存，“非梗”以后直接过滤。"""
    import json as _json

    from . import llm, metrics, storage
    from .lens import CONTENT_RISKS, CRISIS_LEVELS, MEME_FORMS, MEME_FUNCTIONS

    fb = feedback_map()
    negatives = "、".join([k.split(":", 1)[1] for k, v in fb.items() if v.get("label") in _BLOCK_LABELS][-30:])
    pending = []
    for c in cands:
        if c["kind"] in ("web", "transition"):  # 外部召回 / 转场识别在抽取时已由模型给出类型与释义
            continue
        blob = storage.kv_get("memecand:" + c["key"])
        if blob:
            c["lens"] = _json.loads(blob)
            metrics.incr("cache_hit:meme")
        else:
            metrics.incr("cache_miss:meme")
            c["lens"] = None
            pending.append(c)
    if use_llm and pending:
        system = (
            "你是熟悉中文互联网亚文化与短视频生态的研究助理，为高校心理中心判断候选词/句式/视频信号是否构成“梗”或“短视频玩法”。"
            "新闻里的人名、事件名、普通词语、游戏角色名、平台创作激励活动一般不算梗，判为“非梗”。"
            + (f"心理中心老师已人工否定过这些候选（类似的也应判为非梗）：{negatives}。" if negatives else "")
            + "字段：\n"
            f"- type: 从 {MEME_TYPES} 选\n- meaning: 25 字内释义（非梗留空）\n"
            f"- form: 从 {MEME_FORMS} 选\n- function: 从 {MEME_FUNCTIONS} 选\n"
            "- student_usage: 20 字内说明大学生可能如何使用\n"
            f"- crisis_level: 从 {CRISIS_LEVELS} 选（仅当梗本身与自伤自杀等相关）\n"
            f"- content_risk: 从 {CONTENT_RISKS} 选（危险挑战、歧视、网暴、低俗等）\n"
            "- topic_value: 0~3，作为心理健康教育活动切入点的价值\n- confidence: 0~1")
        for start in range(0, min(len(pending), max_new), batch_size):
            chunk = pending[start:start + batch_size]
            listing = "\n".join(
                f'{i}. [{c["kind"]}] {c["label"]}｜出现 {c["df"]} 次｜来源 {",".join(c["sources"])}'
                f'{"｜填充词 " + "/".join(c.get("fillers", [])[:5]) if c.get("fillers") else ""}'
                f'｜例：{" / ".join(c["examples"][:3])}'
                for i, c in enumerate(chunk))
            try:
                rows = llm.chat_json(system, f"逐条判断，输出 JSON 数组，元素含 index 与上述字段：\n{listing}")
            except Exception as exc:
                from loguru import logger
                logger.warning(f"[CampusPulse] 梗候选精筛失败: {exc}")
                break
            if isinstance(rows, dict):
                rows = rows.get("items") or []
            for row in rows if isinstance(rows, list) else []:
                try:
                    c = chunk[int(row.get("index"))]
                except (TypeError, ValueError, IndexError):
                    continue
                lens = {
                    "type": row.get("type") if row.get("type") in MEME_TYPES else "非梗",
                    "meaning": str(row.get("meaning") or "")[:60],
                    "form": row.get("form") if row.get("form") in MEME_FORMS else "",
                    "function": row.get("function") if row.get("function") in MEME_FUNCTIONS else "",
                    "student_usage": str(row.get("student_usage") or "")[:50],
                    "crisis_level": row.get("crisis_level") if row.get("crisis_level") in CRISIS_LEVELS else "无",
                    "content_risk": row.get("content_risk") if row.get("content_risk") in CONTENT_RISKS else "无",
                    "topic_value": max(0, min(3, int(row.get("topic_value") or 0))) if str(row.get("topic_value", "0")).isdigit() else 0,
                    "confidence": float(row.get("confidence") or 0) if isinstance(row.get("confidence"), (int, float)) else 0.5,
                }
                c["lens"] = lens
                storage.kv_set("memecand:" + c["key"], _json.dumps(lens, ensure_ascii=False).encode("utf-8"))
    # 未经 LLM 判断的视频同款信号仍然保留（统计证据本身就有意义），文本候选需判断后才展示
    out = []
    for c in cands:
        lens = c.get("lens")
        if lens and lens["type"] == "非梗":
            continue
        if not lens and c["kind"] in ("word", "template"):
            continue
        out.append(c)
    return out


# ------------------------------------------------------------------ 外部检索召回
WEB_QUERIES = ["最近网络热梗 盘点", "本周热梗 年轻人", "大学生 最近 流行语"]
WEB_RECALL_INTERVAL = 6 * 3600


def web_recall(ugc_docs: List[Tuple[str, str]], now_ts: int, use_llm: bool) -> List[Dict]:
    """
    站内样本有限（B 站热评不登录只给 3 条），新梗可能还没进入样本。每 6 小时用博查检索一次“热梗盘点”，
    由 LLM 从检索结果中抽取梗名与释义（必须引用检索结果编号），再回到站内语料核对出现次数：
    站内也出现的标为“站内已出现”，否则标为“仅外部来源”。结果缓存，两次检索之间复用。
    """
    import json as _json

    from . import llm, search, storage

    blob = storage.kv_get("webrecall:cands")
    cached = _json.loads(blob) if blob else {"ts": 0, "items": []}
    if use_llm and now_ts - cached["ts"] >= WEB_RECALL_INTERVAL:
        pages = []
        for q in WEB_QUERIES:
            try:
                pages += search.web_search(q, count=6, freshness="oneWeek")
            except Exception:
                continue
        if pages:
            listing = "\n".join(f"[W{i + 1}] {p['title']}：{p['snippet'][:220]}" for i, p in enumerate(pages[:18]))
            try:
                rows = llm.chat_json(
                    "你是网络流行文化研究助理。只从给定检索结果中抽取近期流行的网络梗、流行语或短视频玩法，"
                    "不要编造；每条必须引用来源编号。",
                    f"检索结果：\n{listing}\n\n输出 JSON 数组（最多 12 条），元素字段：name（梗本身的写法，10 字内）、"
                    f"type（从 {MEME_TYPES[:-1]} 选）、meaning（25 字内）、evidence（来源编号数组）")
                items = []
                for r in rows if isinstance(rows, list) else []:
                    name = str(r.get("name") or "").strip()
                    ev = [e for e in (r.get("evidence") or []) if isinstance(e, str) and e.startswith("W")]
                    idx = [int(e[1:]) - 1 for e in ev if e[1:].isdigit() and 0 < int(e[1:]) <= len(pages)]
                    if 1 < len(name) <= 12 and idx:
                        items.append({"name": name, "type": r.get("type") if r.get("type") in MEME_TYPES else "网络流行语",
                                      "meaning": str(r.get("meaning") or "")[:60],
                                      "links": [{"title": pages[i]["title"], "url": pages[i]["url"]} for i in idx[:3]]})
                cached = {"ts": now_ts, "items": items}
                storage.kv_set("webrecall:cands", _json.dumps(cached, ensure_ascii=False).encode("utf-8"))
            except Exception as exc:
                from loguru import logger
                logger.warning(f"[CampusPulse] 外部热梗召回失败: {exc}")
    out = []
    for it in cached["items"]:
        hits = [(t, s) for t, s in ugc_docs if it["name"] in t]
        out.append({
            "key": "x:" + it["name"], "kind": "web", "label": it["name"], "df": len(hits),
            "sources": sorted({s for _, s in hits} | {"web"}),
            "examples": [t[:60] for t, _ in hits[:3]] or [l["title"][:60] for l in it["links"]],
            "video_urls": [l["url"] for l in it["links"]] if not hits else None,
            "web_links": it["links"],
            "in_corpus": bool(hits),
            "lens": {"type": it["type"], "meaning": it["meaning"], "form": "", "function": "", "student_usage": "",
                     "crisis_level": "无", "content_risk": "无", "topic_value": 1, "confidence": 0.6},
            "score": (len(hits) + 1) * 3,
        })
    return out
