"""
本校声音：狐友本校圈帖子 → 主题聚合（近 7 天）

与公开热榜不同，本校帖子反映的是学生身边的具体困扰（选课、宿舍、食堂、恋爱、找搭子……）。
每条帖子只标注一次（按内容哈希缓存），看板只展示聚合结果：
主题帖数、互动量、24 小时趋势、情绪分布、心理维度，以及去标识化的短摘要。

危机信号（自伤自杀等）只计数、不展示原文，默认也不提供原帖链接 ——
是否对个体帖子开展干预属于学校心理危机干预制度的范畴，需由学校确定流程后再开启
（PULSE_SHOW_CRISIS_EXCERPTS=1 时显示去标识化摘要）。
"""

import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from loguru import logger

from . import llm, metrics, storage
from .lens import CONTENT_RISKS, CRISIS_LEVELS, PSYCH_DIMENSIONS, _CRISIS_WORDS

CAMPUS_THEMES = [
    "学业课程", "考试考证", "升学就业", "宿舍室友", "恋爱情感", "社交孤独", "找搭子/兴趣活动",
    "食堂与生活服务", "校园设施与管理", "跑腿/二手交易", "失物招领/求助", "身心健康", "情绪宣泄", "灌水/水楼", "其他",
]
# 热度降权：灌水楼、交易、失物招领对心理中心的信息量低
THEME_WEIGHT = {"灌水/水楼": 0.1, "跑腿/二手交易": 0.4, "失物招领/求助": 0.5, "其他": 0.6}
NON_PSYCH_THEMES = {"灌水/水楼", "跑腿/二手交易", "失物招领/求助"}
TREND_MIN_DAYS = float(os.getenv("PULSE_TREND_MIN_DAYS", "7"))
EMOTIONS = ["积极", "中性", "消极"]
SCHOOL_SOURCES = ["huyou-school", "tieba-school"]
_PREFIX = "post3:"  # 增加广告识别与“灌水/水楼”主题后重新标注

_RULE_THEMES = {
    "灌水/水楼": ["水楼", "水贴", "氵", "升级", "经验", "签到", "七级", "八级", "等级墙"],
    "跑腿/二手交易": ["代取", "有偿", "闲置", "二手", "转让", "代课", "代写"],
    "学业课程": ["课", "作业", "老师", "教室", "选课", "专业", "论文", "学分", "绩点", "期中"],
    "考试考证": ["考试", "四级", "六级", "雅思", "托福", "二级", "考证", "期末", "挂科"],
    "升学就业": ["考研", "保研", "实习", "offer", "秋招", "春招", "工作", "简历", "考公"],
    "宿舍室友": ["宿舍", "舍友", "室友", "寝室", "楼道", "走廊", "吹风机", "干发器"],
    "恋爱情感": ["男朋友", "女朋友", "对象", "恋爱", "表白", "分手", "喜欢", "暗恋"],
    "社交孤独": ["孤独", "一个人", "没朋友", "社恐", "独行", "破冰", "融入"],
    "找搭子/兴趣活动": ["搭子", "一起", "有没有人", "组队", "社团", "招募", "拼"],
    "食堂与生活服务": ["食堂", "外卖", "快递", "早餐", "接水", "饮水", "洗衣", "超市"],
    "校园设施与管理": ["图书馆", "厕所", "空调", "网络", "校园卡", "教务", "宽带", "vpn"],
    "失物招领/求助": ["丢", "捡到", "求助", "有没有人知道", "请问"],
    "身心健康": ["失眠", "生病", "医院", "医保", "焦虑", "抑郁"],
}

# 广告 / 商业推广：关键词命中 ≥2 个，或命中强特征词
_AD_STRONG = ["钜惠", "限时优惠", "扫码领取", "加盟", "招代理", "日结", "团购价", "开业大吉", "私信下单", "咨询热线"]
_AD_WORDS = ["优惠", "折扣", "报名", "招生", "门店", "连锁", "健身房", "课程顾问", "免费试听", "福利", "活动价",
             "低至", "特价", "办卡", "会员", "双节同庆", "旗舰店", "高端", "公众号", "代理", "推广", "宽带", "兼职",
             "小班", "师资", "联系老师", "看图联系", "试听", "包过", "提分", "机构"]


def is_ad(content: str) -> bool:
    if any(w in content for w in _AD_STRONG):
        return True
    return sum(w in content for w in _AD_WORDS) >= 2 or content.count("✅") + content.count("💥") >= 3


_SYSTEM = f"""你是高校心理中心的助理，对本校学生论坛的匿名帖子做主题归类，只输出聚合统计需要的标签，不评价个人。
字段：
- is_ad: 是否为广告 / 商业推广 / 引流帖（商家促销、培训招生、兼职代理、办卡拉新等），学生个人的二手转让或求助不算广告
- theme: 从 {CAMPUS_THEMES} 选 1 个
- emotion: 从 {EMOTIONS} 选 1 个
- psych_dimensions: 从 {PSYCH_DIMENSIONS} 选 0~2 个，没有明显心理议题给空数组（失物招领、交易、灌水楼一律为空）
  “灌水/水楼”指水楼、刷经验升级、签到等无实际话题的帖子
- crisis_level: 从 {CRISIS_LEVELS} 选；只有明确表达自伤自杀意图、严重绝望或遭受暴力时才为"高危"，明显的持续低落/求助为"关注"
- content_risk: 从 {CONTENT_RISKS} 选（诈骗、网暴、危险行为等）
- gist: 15 字以内的去标识化概括（不含人名、联系方式、具体位置）"""


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _rule(content: str) -> Dict:
    theme = next((t for t, words in _RULE_THEMES.items() if any(w in content.lower() for w in words)), "其他")
    crisis = "高危" if any(w in content for w in _CRISIS_WORDS) else "无"
    return {"theme": theme, "emotion": "中性", "psych_dimensions": [], "crisis_level": crisis,
            "content_risk": "无", "gist": "", "is_ad": is_ad(content), "annotator": "rule"}


def annotate_posts(posts: List[Dict], use_llm: bool, batch_size: int = 20, max_llm: int = 60) -> Dict[str, Dict]:
    """posts: [{content, ...}] → {hash: 标注}；已缓存的不再调用 LLM。"""
    out: Dict[str, Dict] = {}
    pending = []
    for p in posts:
        h = _hash(p["content"])
        if h in out:
            continue
        blob = storage.kv_get(_PREFIX + h)
        if blob:
            out[h] = json.loads(blob)
            metrics.incr("cache_hit:post")
        else:
            metrics.incr("cache_miss:post")
            out[h] = _rule(p["content"])
            pending.append((h, p["content"]))
    if not (use_llm and pending):
        return out
    for start in range(0, min(len(pending), max_llm), batch_size):
        chunk = pending[start:start + batch_size]
        listing = "\n".join(f"{i}. {c[:150]}" for i, (_, c) in enumerate(chunk))
        try:
            rows = llm.chat_json(_SYSTEM, f"逐条标注以下 {len(chunk)} 条帖子，输出 JSON 数组，元素含 index 与上述字段：\n{listing}")
        except Exception as exc:
            logger.warning(f"[CampusPulse] 本校帖子标注失败，保留规则标注: {exc}")
            break
        if isinstance(rows, dict):
            rows = rows.get("items") or rows.get("posts") or []
        for row in rows if isinstance(rows, list) else []:
            try:
                h, content = chunk[int(row.get("index"))]
            except (TypeError, ValueError, IndexError):
                continue
            rule = out[h]
            crisis = row.get("crisis_level") if row.get("crisis_level") in CRISIS_LEVELS else "无"
            if CRISIS_LEVELS.index(rule["crisis_level"]) > CRISIS_LEVELS.index(crisis):
                crisis = rule["crisis_level"]  # 危机词命中时不允许降级
            ann = {
                "theme": row.get("theme") if row.get("theme") in CAMPUS_THEMES else rule["theme"],
                "emotion": row.get("emotion") if row.get("emotion") in EMOTIONS else "中性",
                "psych_dimensions": [d for d in (row.get("psych_dimensions") or []) if d in PSYCH_DIMENSIONS][:2],
                "crisis_level": crisis,
                "content_risk": row.get("content_risk") if row.get("content_risk") in CONTENT_RISKS else "无",
                "gist": str(row.get("gist") or "")[:30],
                "is_ad": bool(row.get("is_ad")) or (rule["is_ad"] and crisis == "无"),
                "annotator": "llm",
            }
            out[h] = ann
            storage.kv_set(_PREFIX + h, json.dumps(ann, ensure_ascii=False).encode("utf-8"))
    return out


def simhash(text: str) -> int:
    """64 位 SimHash（字符 3-gram）：用于合并转载 / 重复求助 / 几乎相同的帖子。"""
    text = re.sub(r"\[[^\]]*\]|[^\w\u4e00-\u9fff]", "", (text or "").lower())  # 去掉表情 / 标点 / 空白
    grams = [text[i:i + 3] for i in range(max(1, len(text) - 2))]
    v = [0] * 64
    for g in grams:
        h = int(hashlib.md5(g.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(64):
            v[i] += 1 if (h >> i) & 1 else -1
    return sum(1 << i for i in range(64) if v[i] > 0)


def _near_dup(a: int, b: int, threshold: int = 8) -> bool:
    return bin(a ^ b).count("1") <= threshold


def _raw_engagement(p: Dict) -> float:
    # 各平台指标含义不同：狐友有曝光量，贴吧只有回复数 —— 先各自取原始值，再在来源内做分位数
    return p["exposure"] + 20 * p["comments"] if p["scope"].startswith("huyou") else p["comments"]


def _percentiles(posts: List[Dict]) -> None:
    by_src: Dict[str, List[Dict]] = defaultdict(list)
    for p in posts:
        by_src[p["scope"]].append(p)
    for group in by_src.values():
        ranked = sorted(group, key=_raw_engagement)
        n = len(ranked)
        for i, p in enumerate(ranked):
            p["heat_pct"] = (i + 1) / n if n > 1 else 0.5


def _dedupe(posts: List[Dict]) -> List[Dict]:
    kept: List[Dict] = []
    for p in sorted(posts, key=lambda p: p["first_seen"]):
        p["simhash"] = simhash(p["content"])
        twin = next((k for k in kept if _near_dup(k["simhash"], p["simhash"])), None)
        if twin:
            twin["duplicates"] = twin.get("duplicates", 0) + 1
            twin["exposure"] = max(twin["exposure"], p["exposure"])
            twin["comments"] = max(twin["comments"], p["comments"])
            continue
        kept.append(p)
    return kept


def _confidence(n: int, observed_days: float) -> str:
    if observed_days >= TREND_MIN_DAYS and n >= 500:
        return "高"
    if observed_days >= 3 and n >= 150:
        return "中"
    return "低"


def summarize(now_ts: int, use_llm: bool, days: int = 7) -> Dict:
    """聚合近 N 天本校公开社区帖子，返回“本校公开社区信号”看板数据。"""
    rows = storage.recent_items([*SCHOOL_SOURCES, "huyou-national"], now_ts - days * 86400)
    posts: Dict[str, Dict] = {}
    for r in rows:
        ex = r["extra"] or {}
        content = ex.get("content") or r["title"]
        h = _hash(content)
        p = posts.setdefault(h, {"content": content, "scope": r["source"], "first_seen": r["batch_ts"],
                                 "exposure": 0, "comments": 0, "circle": ex.get("circle", ""),
                                 "link": ex.get("link"), "published": ex.get("published")})
        p["exposure"] = max(p["exposure"], ex.get("exposure") or 0)
        p["comments"] = max(p["comments"], ex.get("comments") or 0)
        p["first_seen"] = min(p["first_seen"], ex.get("published") or r["batch_ts"])
    raw_school = [p for p in posts.values() if p["scope"] in SCHOOL_SOURCES]
    school = _dedupe(raw_school)
    national = _dedupe([p for p in posts.values() if p["scope"] == "huyou-national"])
    ann = annotate_posts(sorted(school, key=lambda p: -p["first_seen"]) + national, use_llm)
    show_crisis = os.getenv("PULSE_SHOW_CRISIS_EXCERPTS", "0") == "1"

    themes: Dict[str, Dict] = defaultdict(lambda: {"posts": 0, "posts_24h": 0, "heat": 0.0, "duplicates": 0,
                                                    "emotions": Counter(), "psych": Counter(), "examples": []})
    crisis = {"高危": 0, "关注": 0, "excerpts": []}
    content_risk = Counter()
    ads = 0
    kept = []
    for p in school:
        a = ann.get(_hash(p["content"])) or _rule(p["content"])
        if a.get("is_ad") and a["crisis_level"] == "无":
            ads += 1
            continue  # 广告帖不计入任何主题
        if a["crisis_level"] != "无":
            crisis[a["crisis_level"]] += 1
            if show_crisis and len(crisis["excerpts"]) < 5:
                crisis["excerpts"].append(a.get("gist") or "（待模型概括）")
            continue  # 危机帖不进入主题示例
        p["ann"] = a
        kept.append(p)
    _percentiles(kept)
    for p in sorted(kept, key=lambda p: -p["heat_pct"]):
        a = p["ann"]
        theme = a["theme"]
        if a["content_risk"] in ("中", "高"):
            content_risk[a["content_risk"]] += 1
        t = themes[theme]
        t["posts"] += 1
        t["duplicates"] += p.get("duplicates", 0)
        t["posts_24h"] += int(now_ts - p["first_seen"] <= 86400)
        t["heat"] += p["heat_pct"] * THEME_WEIGHT.get(theme, 1.0)
        t["emotions"][a["emotion"]] += 1
        if theme not in NON_PSYCH_THEMES:  # 失物招领、交易、灌水不附心理维度（避免“丢了校园卡 → 学业压力”）
            t["psych"].update(a["psych_dimensions"])
        # 只展示模型写的去标识化概括：正则无法去除帖子里的真实姓名，规则标注的帖子不展示原文片段
        if len(t["examples"]) < 3 and a.get("gist"):
            t["examples"].append(a["gist"])
    nat_ann = [ann.get(_hash(p["content"])) or _rule(p["content"]) for p in national]
    nat_themes = Counter(a["theme"] for a in nat_ann if not a.get("is_ad"))
    n_school = sum(t["posts"] for t in themes.values()) or 1
    n_nat = sum(nat_themes.values()) or 1

    # 数据实际覆盖的天数；不足 TREND_MIN_DAYS 天不给出“上升/下降”结论
    observed = storage.recent_items(SCHOOL_SOURCES, now_ts - days * 86400)
    first_ts = min((r["batch_ts"] for r in observed), default=now_ts)
    span_days = min(days, (now_ts - first_ts) / 86400)
    trend_ready = span_days >= TREND_MIN_DAYS
    theme_list = []
    for name, t in themes.items():
        before = t["posts"] - t["posts_24h"]
        baseline = before / (span_days - 1) if trend_ready else None
        theme_list.append({
            "theme": name,
            "posts": t["posts"],
            "posts_24h": t["posts_24h"],
            "duplicates_merged": t["duplicates"],
            "trend": round(t["posts_24h"] / baseline, 2) if baseline else None,
            "heat": round(t["heat"], 2),
            "weight": THEME_WEIGHT.get(name, 1.0),
            "share": round(t["posts"] / n_school, 3),
            "national_share": round(nat_themes.get(name, 0) / n_nat, 3),
            "negative_ratio": round(t["emotions"]["消极"] / t["posts"], 2) if t["posts"] else 0,
            "psych": [d for d, _ in t["psych"].most_common(3)],
            "examples": t["examples"],
        })
    theme_list.sort(key=lambda x: -x["heat"])
    n_valid = len(kept)
    return {
        "generated_at": now_ts,
        "days": days,
        "circles": sorted({p["circle"] for p in school if p["circle"]}),
        "school_posts": n_valid,
        "raw_posts": len(raw_school),
        "duplicates_merged": len(raw_school) - len(school),
        "ads_filtered": ads,
        "by_source": {s: sum(1 for p in kept if p["scope"] == s) for s in SCHOOL_SOURCES},
        "national_posts": len(national),
        "annotated_by_llm": sum(1 for p in kept if p["ann"].get("annotator") == "llm"),
        "observed_days": round(span_days, 2),
        "trend_ready": trend_ready,
        "trend_min_days": TREND_MIN_DAYS,
        "confidence": _confidence(n_valid, span_days),
        "themes": theme_list,
        "crisis": crisis,
        "crisis_excerpts_enabled": show_crisis,
        "content_risk": dict(content_risk),
    }


def theme_posts(theme: str, now_ts: int, days: int = 7, limit: Optional[int] = None) -> Dict:
    """某主题下的本校帖子明细（脱敏正文 + 模型概括 + 情绪/心理维度），不含发帖人信息。
    默认返回全部可展示记录；显式传入 limit 的内部调用仍保留数量限制。
    广告帖不返回；危机帖默认不返回原文（PULSE_SHOW_CRISIS_EXCERPTS=1 时返回）。"""
    from .sources.huyou import mask_names

    show_crisis = os.getenv("PULSE_SHOW_CRISIS_EXCERPTS", "0") == "1"
    rows = storage.recent_items(SCHOOL_SOURCES, now_ts - days * 86400)
    seen, out, hidden = set(), [], 0
    for r in sorted(rows, key=lambda r: -r["batch_ts"]):
        ex = r["extra"] or {}
        content = ex.get("content") or r["title"]
        h = _hash(content)
        if h in seen:
            continue
        seen.add(h)
        blob = storage.kv_get(_PREFIX + h)
        a = json.loads(blob) if blob else _rule(content)
        if a.get("is_ad") and a["crisis_level"] == "无":
            continue
        is_crisis = a["crisis_level"] != "无"
        if theme == "__crisis__":
            if not is_crisis:
                continue
        elif a["theme"] != theme or is_crisis:
            continue
        if is_crisis and not show_crisis:
            hidden += 1
            continue
        sh = simhash(content)
        if any(_near_dup(sh, o["_sh"]) for o in out):
            continue
        out.append({
            "_sh": sh,
            "content": mask_names(content),   # 旧数据入库时尚未遮蔽姓名，展示时再处理一次
            "gist": a.get("gist") or "",
            "emotion": a.get("emotion"),
            "psych_dimensions": a.get("psych_dimensions") or [],
            "crisis_level": a["crisis_level"],
            "content_risk": a.get("content_risk", "无"),
            "source": r["source"],
            "circle": ex.get("circle", ""),
            "comments": ex.get("comments") or 0,
            "exposure": ex.get("exposure") or 0,
            "published": ex.get("published") or r["batch_ts"],
            "link": ex.get("link"),
            "annotator": a.get("annotator"),
        })
    for o in out:
        o.pop("_sh", None)
        if a_theme_nonpsych(theme):
            o["psych_dimensions"] = []
    from .observatory import raw_heat
    import bisect
    for source in SCHOOL_SOURCES:
        group = [p for p in out if p['source'] == source]
        ranks = sorted(raw_heat(source,p['exposure'],p['comments']) for p in group)
        for p in group:
            raw = raw_heat(source,p['exposure'],p['comments'])
            p['heat'] = round(100*bisect.bisect_right(ranks,raw)/len(ranks),1) if raw else 0
    out.sort(key=lambda p: (-p['heat'], -(p['published'] or 0)))
    return {"theme": theme, "posts": out[:limit], "total": len(out), "hidden_crisis": hidden}


def a_theme_nonpsych(theme: str) -> bool:
    return theme in NON_PSYCH_THEMES
