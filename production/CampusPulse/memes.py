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


# ------------------------------------------------------------------ 全网多平台（B站/抖音/微博/百度/知乎/贴吧）青年梗文化目录
NETWORK_MEME_BASE = [
    {
        "term": "已老实，求放过",
        "type": "网络流行语",
        "form": "句式模板",
        "function": "自嘲解压",
        "platforms": ["B站", "抖音", "微博", "百度"],
        "keywords": ["已老实", "求放过", "老实了"],
        "meaning": "源自网络消费与期末周调侃，年轻人在面对高难度课程、繁重实验、高物价或师长追问时，用夸张的“认怂滑跪”姿态化解压力。",
        "usage": "常用于期末复习破防、实验数据跑不通、熬夜赶DDL后的评论区自嘲（如“高数已老实，求放过”）。",
        "psych_dimensions": ["学业压力", "情绪调节"],
        "activity_hint": "可结合期末季开展“卸下防御·真实表达”减压工作坊，引导学生区分幽默自嘲与习得性无助。",
        "examples": ["做完三天物理化学实验后：已老实，求放过", "月底看了一眼校园卡账单，大学生已老实"],
    },
    {
        "term": "脆皮大学生",
        "type": "网络流行语",
        "form": "角色扮演/人设",
        "function": "情绪共鸣",
        "platforms": ["抖音", "B站", "微博", "百度"],
        "keywords": ["脆皮", "脆皮大学生", "体测", "生病", "医院"],
        "meaning": "走红于抖音与B站的青年群体自画像，形容当代大学生虽然年纪轻，但因熬夜、久坐、缺乏运动而频频出现各种哭笑不得的身体小状况。",
        "usage": "体测800米/1000米跑完、换季感冒、熬夜赶作业后自称“脆皮大学生今日战损”。",
        "psych_dimensions": ["身体健康", "情绪调节"],
        "activity_hint": "适合联合体育学院或校医院开展“告别脆皮·微运动打卡”或睡眠健康朋辈互助营。",
        "examples": ["伸个懒腰差点闪了腰，确诊为脆皮大学生", "体测完在操场躺平：脆皮但难杀"],
    },
    {
        "term": "班味 / 课味太重",
        "type": "网络流行语",
        "form": "谐音/造词",
        "function": "自嘲解压",
        "platforms": ["微博", "抖音", "B站", "百度"],
        "keywords": ["班味", "课味", "早八", "实习", "秋招"],
        "meaning": "由“上班后的疲惫气质（班味）”延伸到高校场景，形容连续早八、满课、实验室打卡或秋招实习后眼神流露出的疲惫感。",
        "usage": "周一连续四节专业课或去企业实习通勤时自嘲“身上有一股浓浓的早八课味/班味”，周末出游则称“去班味”。",
        "psych_dimensions": ["学业压力", "就业焦虑", "情绪调节"],
        "activity_hint": "可设计“20分钟公园效应·校园去课味漫步”心育活动，帮助学生在自然与微社交中恢复心理能量。",
        "examples": ["连上四天早八，连呼吸都带着股课味", "去奉贤海边吹吹风，洗掉身上的班味"],
    },
    {
        "term": "偷感很重",
        "type": "网络流行语",
        "form": "角色扮演/人设",
        "function": "身份表达",
        "platforms": ["抖音", "B站", "微博"],
        "keywords": ["偷感", "社恐", "一个人"],
        "meaning": "形容由于内向、社恐或害怕被注视，在做正常事情（如独自去食堂吃饭、去图书馆占座、拍照打卡）时表现得小心翼翼、像在做贼一样。",
        "usage": "新生或社恐同学独自参加社团招新、一个人在食堂拍照发朋友圈时调侃自己“偷感好重”。",
        "psych_dimensions": ["人际关系", "自我认同"],
        "activity_hint": "切中大学生社交焦虑（聚光灯效应），可开展“脱掉隐形斗篷·社恐友好型破冰沙龙”。",
        "examples": ["一个人去食堂吃火锅，偷感重得像在搞地下工作", "在校园里想拍张照，有人路过立刻假装看手机"],
    },
    {
        "term": "草台班子理论",
        "type": "网络流行语",
        "form": "句式模板",
        "function": "情绪共鸣",
        "platforms": ["B站", "微博", "知乎", "百度"],
        "keywords": ["草台班子", "大创", "组队", "汇报", "答辩"],
        "meaning": "全网广泛共鸣的祛魅流行语（“世界就是一个巨大的草台班子”），帮助青年人放下完美主义焦虑，接受万事万物都在边摸索边推进。",
        "usage": "大学生在准备大创答辩、社团办活动、考研复试或面试紧张时，用这句话互相宽慰、消解对权威的过度敬畏。",
        "psych_dimensions": ["自我认同", "学业压力", "就业焦虑"],
        "activity_hint": "非常契合“克服冒充者综合征与完美主义焦虑”主题班会，鼓励学生先行动、在试错中成长。",
        "examples": ["别怕答辩出错，记住世界是个巨大的草台班子，大胆上台讲！", "第一次办社团晚会手忙脚乱，但大家开心就够了"],
    },
    {
        "term": "浓人 vs 淡人",
        "type": "网络流行语",
        "form": "角色扮演/人设",
        "function": "社交认同",
        "platforms": ["微博", "B站", "抖音", "百度"],
        "keywords": ["淡人", "浓人", "情绪稳定", "随缘"],
        "meaning": "继 i人/e人 之后在微博与B站兴起的人格温度标签：“淡人”情绪起伏小、对待得失云淡风轻；“浓人”情感充沛、对生活充满热烈表达。",
        "usage": "宿舍室友相处、找学习搭子或自我介绍时用来描述处事风格（如“淡人室友遇上浓人室友”）。",
        "psych_dimensions": ["自我认同", "人际关系", "情绪调节"],
        "activity_hint": "可用于宿舍人际关系团辅，引导学生理解不同情绪表达风格（非冷漠也非矫情），增进室友包容。",
        "examples": ["查期末成绩时：浓人已经在尖叫，淡人默默关掉教务网去吃饭", "找个淡人考研搭子，情绪稳定互不内耗"],
    },
    {
        "term": "卡点变装 / 踮脚转场",
        "type": "短视频玩法",
        "form": "短视频转场",
        "function": "身份表达",
        "platforms": ["抖音", "B站"],
        "keywords": ["转场", "变装", "卡点", "短视频", "vlog"],
        "meaning": "抖音与B站高校圈高赞短视频玩法，通过节拍卡点与动作衔接（如踮脚、遮镜、甩头），从日常素颜/工科实验服一秒切换到盛装或青春高光时刻。",
        "usage": "军训结束、穿着白大褂做完化学实验、毕业季学位服打卡时，拍摄反差感转场视频展现多元自我。",
        "psych_dimensions": ["自我认同", "情绪调节"],
        "activity_hint": "可发起“实验服下的AB面·发现多元自我”校园短视频征集活动，增强专业认同感与生活热情。",
        "examples": ["前1秒还在实验室刷烧杯，卡点一转场变身音乐节乐手", "从早八卫衣到社团汉服的丝滑转场"],
    },
    {
        "term": "精神状态遥遥领先",
        "type": "网络流行语",
        "form": "发疯/抽象文学",
        "function": "自嘲解压",
        "platforms": ["B站", "抖音", "百度", "贴吧"],
        "keywords": ["精神状态", "遥遥领先", "发疯", "抽象"],
        "meaning": "融合科技热词与“发疯文学”的幽默反讽，指在面对学业或求职高压时，用无厘头、脑洞大开的乐观/抽象表达代替内耗。",
        "usage": "备考周、写毕业论文或改方案时，在朋友圈或B站弹幕里用夸张搞笑的图片/段子宣告“今日精神状态美丽”。",
        "psych_dimensions": ["情绪调节", "学业压力"],
        "activity_hint": "可引导讨论“幽默宣泄与积极心理防御机制”，设立校园创意涂鸦墙或情绪树洞。",
        "examples": ["论文改到第八版，我的精神状态已经遥遥领先于人类了", "当代大学生主打一个不内耗"],
    },
    {
        "term": "古希腊掌管XX的神",
        "type": "句式模板",
        "form": "句式模板",
        "function": "幽默娱乐",
        "platforms": ["抖音", "B站", "微博"],
        "keywords": ["掌管", "的神", "学霸", "食堂"],
        "meaning": "源自抖音与B站的高频夸赞/调侃句式模板，将某人在某个细分领域的特长或趣味习惯封为“古希腊掌管XX的神”。",
        "usage": "夸赞身边擅长做笔记的同学是“掌管期末重点的神”，或调侃食堂阿姨、抢课手速快的室友。",
        "psych_dimensions": ["自我认同", "人际关系"],
        "activity_hint": "可用于新生破冰或班会“夸夸群/闪光点互评”环节，让每位同学被看见自己的微特长。",
        "examples": ["室友三秒抢到体育选修课，简直是古希腊掌管选课的神", "华理红烧肉窗口：古希腊掌管碳水快乐的神"],
    },
    {
        "term": "搭子文化（饭搭子/考研搭子）",
        "type": "网络流行语",
        "form": "谐音/造词",
        "function": "社交认同",
        "platforms": ["B站", "抖音", "微博", "贴吧"],
        "keywords": ["搭子", "饭搭子", "考研搭子", "图书馆"],
        "meaning": "轻量化、精准垂直的新型青年社交模式：不需要全方位的深度捆绑，而是在吃饭、泡图书馆、考研、运动等特定场景下互相陪伴支持。",
        "usage": "校园圈与贴吧高频出现“找图书馆自习搭子”“约羽毛球搭子”“食堂饭搭子”，降低孤立感同时保留个人边界。",
        "psych_dimensions": ["人际关系", "学业压力"],
        "activity_hint": "心理中心可借势搭建“心育微社群·21天习惯养成搭子匹配”活动，将原子化个体连接为互助同伴。",
        "examples": ["求一位奉贤校区图书馆考研搭子，互相监督不玩手机", "有没有一起去吃食堂新品的饭搭子"],
    },
    {
        "term": "水灵灵地XX",
        "type": "句式模板",
        "form": "句式模板",
        "function": "幽默娱乐",
        "platforms": ["抖音", "微博", "B站", "百度"],
        "keywords": ["水灵灵"],
        "meaning": "源自网络热门语录的副词活用句式（“就这么水灵灵地…”），用生动鲜活的语气描述某件出人意料或略带尴尬的小事发生的过程。",
        "usage": "用于化解日常小尴尬，如“上课回答问题就这么水灵灵地叫错了老师名字”“闹钟没响水灵灵地睡过了早八”。",
        "psych_dimensions": ["情绪调节", "人际关系"],
        "activity_hint": "体现青年话语用轻盈幽默消解日常挫败的能力，可在校园新媒体推文中自然融入该句式拉近距离。",
        "examples": ["本来想在学长面前装高冷，结果就这么水灵灵地平地摔了一跤", "以为今天周五，水灵灵地把周四晚课忘了"],
    },
    {
        "term": "赛博电子布洛芬",
        "type": "网络流行语",
        "form": "谐音/造词",
        "function": "情绪共鸣",
        "platforms": ["B站", "抖音", "微博"],
        "keywords": ["电子布洛芬", "治愈", "哈基米", "解压"],
        "meaning": "大学生将B站/抖音上能迅速抚平焦虑、带来治愈感的内容（如萌宠哈基米视频、搞笑番剧、解压手工、校园美景）比作“电子止痛药”。",
        "usage": "在经历考试压力、秋招受挫或情绪低落时，通过观看治愈系视频进行短暂的自我情绪安抚。",
        "psych_dimensions": ["情绪调节", "学业压力"],
        "activity_hint": "可策划“我的治愈书单/影单/校园角落共享”心育征集，引导学生建立健康的日常情绪工具箱。",
        "examples": ["看半小时校园小猫视频，简直是期末周的电子布洛芬", "每次焦虑的时候就来看这段鬼畜，我的快乐源泉"],
    },
]


def network_meme_catalog(now_ts: int = None) -> List[Dict]:
    """聚合全网平台（B站、抖音、微博、百度、知乎、贴吧）与实测语料的青年梗文化列表。"""
    import time as _time
    from urllib.parse import quote as _quote
    from . import storage

    now_ts = now_ts or int(_time.time())
    all_sources = [
        "bilibili-popular", "bilibili-hot-search", "douyin", "weibo",
        "baidu", "zhihu", "tieba", "toutiao", "thepaper",
        "huyou-national", "huyou-school", "tieba-school",
    ]
    rows = storage.recent_items(all_sources, now_ts - 7 * 86400)
    docs = build_docs(rows)
    recalled = web_recall(docs, now_ts, use_llm=False)

    out = []
    seen_terms = set()
    for base in NETWORK_MEME_BASE:
        term = base["term"]
        seen_terms.add(term)
        kws = base["keywords"]
        matched_rows = []
        school_hits = 0
        for r in rows:
            ex = r.get("extra") or {}
            txt = (r.get("title") or "") + " " + (ex.get("content") or "") + " " + (ex.get("desc") or "")
            if any(k in txt for k in kws):
                matched_rows.append(r)
                if r.get("source") in ("huyou-school", "tieba-school"):
                    school_hits += 1
        links = []
        seen_urls = set()
        for r in matched_rows:
            ex = r.get("extra") or {}
            u = ex.get("link") or r.get("url")
            if u and u not in seen_urls:
                seen_urls.add(u)
                src_label = {
                    "bilibili-popular": "B站热门", "bilibili-hot-search": "B站热搜",
                    "douyin": "抖音", "weibo": "微博", "baidu": "百度", "zhihu": "知乎",
                    "tieba": "贴吧", "huyou-school": "华理狐友", "tieba-school": "华理贴吧",
                }.get(r.get("source"), "平台来源")
                links.append({"title": f"{src_label} · {(r.get('title') or ex.get('content') or term)[:36]}", "url": u})
            if len(links) >= 3:
                break
        q = _quote(term.split("（")[0].split("/")[0].strip())
        platform_search = {
            "B站": f"https://search.bilibili.com/all?keyword={q}",
            "抖音": f"https://www.douyin.com/search/{q}",
            "微博": f"https://s.weibo.com/weibo?q={q}",
            "百度": f"https://www.baidu.com/s?wd={q}",
            "知乎": f"https://www.zhihu.com/search?type=content&q={q}",
            "贴吧": f"https://tieba.baidu.com/f/search/res?qw={q}",
        }
        for pf in base["platforms"]:
            if len(links) < 4 and pf in platform_search:
                links.append({"title": f"在 {pf} 查看「{term}」原视频与热议 ↗", "url": platform_search[pf]})

        out.append({
            "term": term,
            "label": term,
            "type": base["type"],
            "form": base["form"],
            "function": base["function"],
            "platforms": base["platforms"],
            "meaning": base["meaning"],
            "usage": base["usage"],
            "psych_dimensions": base["psych_dimensions"],
            "activity_hint": base["activity_hint"],
            "examples": base["examples"],
            "school_hits": school_hits,
            "network_hits": len(matched_rows),
            "links": links,
        })

    for w in recalled:
        name = w.get("label") or ""
        if not name or name in seen_terms:
            continue
        seen_terms.add(name)
        lens_info = w.get("lens") or {}
        q = _quote(name)
        links = list(w.get("web_links") or [])
        if not links:
            links = [{"title": f"在 B站 查看「{name}」 ↗", "url": f"https://search.bilibili.com/all?keyword={q}"}]
        out.append({
            "term": name,
            "label": name,
            "type": lens_info.get("type") or "网络流行语",
            "form": lens_info.get("form") or "句式模板",
            "function": lens_info.get("function") or "情绪共鸣",
            "platforms": ["B站", "抖音", "微博"],
            "meaning": lens_info.get("meaning") or "近期在青年社交平台快速扩散的网络流行表达。",
            "usage": lens_info.get("student_usage") or "常用于大学生日常社交互动与评论区共鸣。",
            "psych_dimensions": ["情绪调节", "人际关系"],
            "activity_hint": "可结合青年近期关注热点作为主题班会或新媒体互动切入点。",
            "examples": w.get("examples") or [],
            "school_hits": w.get("df") or 0,
            "network_hits": max(1, w.get("df") or 1),
            "links": links,
        })
    return out



