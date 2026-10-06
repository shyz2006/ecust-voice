"""
校园心理透镜：把热点话题映射到"心理中心可用"的结构化标签。

梗的三维分类借鉴 Nguyen & Ng, "Computational Meme Understanding: A Survey"
(EMNLP 2024)：形式(form) / 功能(function) / 主题(topic)；并补充了国内短视频
语境下常见的形式（转场、BGM 卡点、句式模板、谐音梗等）。

心理维度参考高校心理健康教育常见议题，用于指导活动设计，而不是对个体做判断。
"""

import json
from typing import Dict, List, Optional

from loguru import logger

from . import llm, metrics, storage

CATEGORIES = [
    "社会热点", "梗文化", "短视频玩法", "校园教育", "就业升学", "情感关系",
    "娱乐明星", "体育赛事", "科技数码", "游戏动漫", "健康生活", "财经消费", "国际时政", "其他",
]

MEME_FORMS = [
    "句式模板", "谐音/造词", "表情包/图像宏", "反应图/截图", "短视频转场", "BGM/卡点",
    "挑战/模仿", "角色扮演/人设", "发疯/抽象文学", "AI生成内容",
]
MEME_FUNCTIONS = ["自嘲解压", "情绪共鸣", "幽默娱乐", "讽刺批评", "社交认同", "身份表达", "信息传播"]

PSYCH_DIMENSIONS = [
    "学业压力", "就业焦虑", "人际关系", "恋爱情感", "自我认同", "情绪调节",
    "家庭关系", "身体健康", "网络行为", "价值观/社会公平", "生命安全",
]

# 风险拆为三条独立维度，避免“诈骗新闻”和“自伤信号”混在同一个“重点”里造成告警疲劳
CRISIS_LEVELS = ["无", "关注", "高危"]      # 心理危机信号（自伤自杀、严重心理困扰、校园暴力受害）
CONTENT_RISKS = ["无", "低", "中", "高"]    # 内容安全 / 模仿风险（危险挑战、诈骗、网暴、极端内容、谣言）
# topic_value: 0~3，作为心理中心活动选题的价值

# 规则兜底：LLM 不可用时仍能给出粗分类
_RULES = {
    "category": {
        "就业升学": ["考研", "考公", "考编", "就业", "招聘", "裁员", "实习", "offer", "秋招", "春招", "保研", "毕业"],
        "校园教育": ["高校", "大学", "学生", "教育部", "高考", "开学", "宿舍", "校园", "教师", "军训", "录取"],
        "情感关系": ["恋爱", "分手", "结婚", "离婚", "相亲", "表白", "彩礼", "情侣"],
        "梗文化": ["梗", "文学", "发疯", "破防", "emo", "哈基米", "显眼包", "搭子", "city", "班味", "抽象", "整活"],
        "短视频玩法": ["转场", "挑战", "变装", "卡点", "仿妆", "模仿", "同款", "手势舞", "vlog"],
        "体育赛事": ["国足", "乒乓", "奥运", "冠军", "比赛", "决赛", "联赛", "nba", "世界杯", "亚运"],
        "娱乐明星": ["演唱会", "综艺", "电视剧", "电影", "官宣", "票房", "恋情", "新歌"],
        "科技数码": ["手机", "芯片", "ai", "发布会", "华为", "苹果", "小米", "大模型"],
        "游戏动漫": ["游戏", "原神", "王者", "lol", "动漫", "番剧", "黑神话", "steam"],
        "健康生活": ["疫苗", "流感", "睡眠", "减肥", "健身", "医院", "猝死", "熬夜"],
        "国际时政": ["美国", "访问", "外交", "总统", "峰会", "联合国"],
        "财经消费": ["股市", "房价", "茅台", "消费", "价格", "涨价", "降价", "金价"],
    },
    "psych": {
        "学业压力": ["考试", "期末", "挂科", "绩点", "论文", "内卷", "高考", "考研"],
        "就业焦虑": ["就业", "裁员", "考公", "失业", "招聘", "实习", "秋招", "工资"],
        "人际关系": ["室友", "社恐", "搭子", "朋友", "霸凌", "孤独"],
        "恋爱情感": ["恋爱", "分手", "表白", "彩礼", "出轨", "情侣"],
        "情绪调节": ["emo", "破防", "发疯", "焦虑", "躺平", "摆烂", "解压", "治愈"],
        "网络行为": ["网暴", "诈骗", "沉迷", "开盒", "谣言"],
        "价值观/社会公平": ["公平", "维权", "歧视", "性别"],
        "生命安全": ["自杀", "轻生", "跳楼", "自残", "失联", "溺亡"],
        "身体健康": ["猝死", "熬夜", "流感", "疫苗", "减肥"],
    },
}

_CRISIS_WORDS = ["自杀", "轻生", "跳楼", "自残", "割腕", "遗书", "抑郁症去世", "不想活", "活着没意思"]
_CONTENT_RISK_WORDS = {
    "中": ["诈骗", "骗局", "网暴", "开盒", "谣言", "不实", "传销", "裸聊", "校园贷", "危险挑战"],
    "高": ["约架", "极端", "自制炸", "模仿作案"],
}


def rule_annotate(topic: Dict) -> Dict:
    text = (topic.get("label", "") + " " + " ".join(topic.get("titles", []))).lower()
    cats = [c for c, words in _RULES["category"].items() if any(w in text for w in words)]
    psych = [p for p, words in _RULES["psych"].items() if any(w in text for w in words)]
    # 公开热榜里的危机类新闻是“需要关注的传播”（模仿效应），不是本校学生的高危信号
    crisis = "关注" if any(w in text for w in _CRISIS_WORDS) else "无"
    content_risk = "无"
    for level in ("中", "高"):
        if any(w in text for w in _CONTENT_RISK_WORDS[level]):
            content_risk = level
    if crisis != "无" and content_risk == "无":
        content_risk = "中"
    return {
        "category": cats[0] if cats else "社会热点",
        "is_meme": "梗文化" in cats or "短视频玩法" in cats,
        "meme": None,
        "psych_dimensions": psych,
        "campus_relevance": 2 if ({"校园教育", "就业升学"} & set(cats) or psych) else 1,
        "crisis_level": crisis,
        "content_risk": content_risk,
        "topic_value": 2 if psych else 1,
        "one_liner": "",
        "activity_hint": "",
        "annotator": "rule",
    }


_ANNOTATE_SYSTEM = f"""你是高校心理健康教育中心的舆情助理，负责把网络热榜话题转成心理老师能快速理解的标签。
面向对象是在校大学生群体。只基于给出的标题判断，不确定就保守标注，不要编造事实。

字段要求：
- category: 从 {CATEGORIES} 中选 1 个
- is_meme: 是否属于网络梗 / 流行语 / 短视频玩法（true/false）
- meme: is_meme 为 true 时给出 {{"form": 从{MEME_FORMS}选, "function": 从{MEME_FUNCTIONS}选, "meaning": "20字内释义"}}，否则 null
- psych_dimensions: 该话题明显触及的学生心理议题，从 {PSYCH_DIMENSIONS} 中选 0~2 个；一般资讯（时政、数码新品、体育比分等）没有明显关联时给空数组
- campus_relevance: 0~3，大学生关注/被影响的可能程度
- crisis_level: 从 {CRISIS_LEVELS} 选，只表示学生心理危机信号。公开新闻中涉及自伤自杀、校园暴力的为"关注"（存在模仿与情绪冲击风险）；"高危"只用于学生本人表达自伤自杀意图等情况；诈骗、谣言、一般社会新闻一律为"无"
- content_risk: 从 {CONTENT_RISKS} 选，表示内容安全或模仿风险：危险挑战、诈骗、网暴、极端内容、谣言等；普通资讯为"无"
- topic_value: 0~3，作为高校心理中心活动选题的价值（能否引出情绪、关系、成长等可讨论议题，且适合正向引导）
- one_liner: 30 字内说明学生为什么会关注它
- activity_hint: 若适合作为心理中心活动切入点，给出 20 字内的点子，否则空字符串"""


ANNOT_PREFIX = "annot2:"  # 风险维度拆分后重新标注，旧缓存 annot: 不再使用


def _cache_key(topic: Dict) -> str:
    return ANNOT_PREFIX + topic["label"]


def annotate_topics(topics: List[Dict], use_llm: bool = True, batch_size: int = 10,
                    llm_top_n: int = 30) -> List[Dict]:
    """
    为话题补充 lens 标注。
    - 同一标题的标注会缓存，避免每次采集都重复调用 LLM；
    - 只有综合分前 llm_top_n 的新话题交给 LLM，长尾话题用规则标注，控制成本与耗时。
    """
    pending = []
    for rank, t in enumerate(topics):
        cached = None
        for title in [t["label"], *t.get("titles", [])]:
            blob = storage.kv_get(ANNOT_PREFIX + title)
            if blob:
                cached = json.loads(blob)
                break
        if cached:
            t["lens"] = cached
            metrics.incr("cache_hit:topic")
        else:
            metrics.incr("cache_miss:topic")
            t["lens"] = rule_annotate(t)
            if rank < llm_top_n:
                pending.append(t)

    if not (use_llm and pending):
        return topics
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        listing = "\n".join(
            f'{i}. {t["label"]}（平台：{",".join(t["sources"])}；相关标题：{" / ".join(t["titles"][1:4])}）'
            for i, t in enumerate(chunk)
        )
        try:
            result = llm.chat_json(
                _ANNOTATE_SYSTEM,
                f"请逐条标注以下 {len(chunk)} 个话题，输出 JSON 数组，每个元素包含 index 和上述字段：\n{listing}",
            )
        except Exception as exc:
            logger.warning(f"[CampusPulse] LLM 标注失败，保留规则标注: {exc}")
            return topics
        if isinstance(result, dict):
            result = result.get("items") or result.get("topics") or []
        for row in result if isinstance(result, list) else []:
            try:
                t = chunk[int(row.get("index"))]
            except (TypeError, ValueError, IndexError):
                continue
            lens = _normalize(row, fallback=t["lens"])
            t["lens"] = lens
            storage.kv_set(_cache_key(t), json.dumps(lens, ensure_ascii=False).encode("utf-8"))
    return topics


def _normalize(row: Dict, fallback: Dict) -> Dict:
    def pick(value, allowed, default):
        return value if value in allowed else default

    meme = row.get("meme") if row.get("is_meme") else None
    if isinstance(meme, dict):
        meme = {
            "form": pick(meme.get("form"), MEME_FORMS, "句式模板"),
            "function": pick(meme.get("function"), MEME_FUNCTIONS, "幽默娱乐"),
            "meaning": str(meme.get("meaning") or "")[:60],
        }
    else:
        meme = None
    try:
        relevance = max(0, min(3, int(row.get("campus_relevance", fallback["campus_relevance"]))))
    except (TypeError, ValueError):
        relevance = fallback["campus_relevance"]
    crisis = pick(row.get("crisis_level"), CRISIS_LEVELS, fallback["crisis_level"])
    content_risk = pick(row.get("content_risk"), CONTENT_RISKS, fallback["content_risk"])
    # 规则层识别到危机词时，LLM 不能把心理危机等级降级
    if CRISIS_LEVELS.index(fallback["crisis_level"]) > CRISIS_LEVELS.index(crisis):
        crisis = fallback["crisis_level"]
    try:
        topic_value = max(0, min(3, int(row.get("topic_value", fallback["topic_value"]))))
    except (TypeError, ValueError):
        topic_value = fallback["topic_value"]
    return {
        "category": pick(row.get("category"), CATEGORIES, fallback["category"]),
        "is_meme": bool(meme),
        "meme": meme,
        "psych_dimensions": [p for p in (row.get("psych_dimensions") or []) if p in PSYCH_DIMENSIONS][:3],
        "campus_relevance": relevance,
        "crisis_level": crisis,
        "content_risk": content_risk,
        "topic_value": topic_value,
        "one_liner": str(row.get("one_liner") or "")[:80],
        "activity_hint": str(row.get("activity_hint") or "")[:60],
        "annotator": "llm",
    }


def campus_score(topic: Dict) -> float:
    """面向心理中心的排序分：热度 × 校园相关度 × 选题价值；心理危机信号上浮，内容风险适度上浮。"""
    lens = topic.get("lens") or {}
    rel = lens.get("campus_relevance", 1)
    value = lens.get("topic_value", 1)
    bonus = 1.6 if lens.get("is_meme") else 1.0
    crisis = {"高危": 3.0, "关注": 1.8}.get(lens.get("crisis_level"), 1.0)
    content = {"高": 1.3, "中": 1.15}.get(lens.get("content_risk"), 1.0)
    return topic.get("score", 0) * (0.4 + 0.3 * rel) * (0.6 + 0.3 * value) * bonus * crisis * content



# ------------------------------------------------------------------ 分析结果标签归一化
# 模型撰写深度分析时常把“形式 / 功能 / 心理维度”写成长句，前端显示为超长标签。
# 这里按关键词映射到标准分类，原文保留在 *_detail 字段中单独展示。

_FORM_KEYWORDS = {
    "短视频转场": ["转场"],
    "BGM/卡点": ["bgm", "卡点", "配乐", "音乐"],
    "挑战/模仿": ["挑战", "模仿", "跟拍", "同款", "翻拍"],
    "角色扮演/人设": ["角色", "人设", "扮演", "cos"],
    "发疯/抽象文学": ["发疯", "抽象", "文学"],
    "表情包/图像宏": ["表情包", "梗图", "图片", "图像"],
    "反应图/截图": ["截图", "反应图"],
    "谐音/造词": ["谐音", "造词", "新词", "缩写", "词汇"],
    "AI生成内容": ["ai生成", "ai 生成", "aigc"],
    "句式模板": ["句式", "短句", "文案", "模板", "评论", "弹幕", "造句", "口头禅"],
}
_FUNCTION_KEYWORDS = {
    "自嘲解压": ["自嘲", "解压", "减压"],
    "讽刺批评": ["讽刺", "批评", "反讽", "吐槽"],
    "情绪共鸣": ["共鸣", "情绪", "疲惫", "感受", "宣泄"],
    "幽默娱乐": ["幽默", "娱乐", "搞笑", "调侃", "玩梗"],
    "社交认同": ["社交", "认同", "圈层", "暗号", "拉近"],
    "身份表达": ["身份", "表达自我", "态度"],
    "信息传播": ["传播", "科普", "信息"],
}
_PSYCH_KEYWORDS = {
    dim: list(words) for dim, words in _RULES["psych"].items()
}
for _dim, _extra in {
    "就业焦虑": ["工作", "职场", "上班", "求职", "岗位"],
    "学业压力": ["学业", "课程", "上课", "科研", "学习"],
    "情绪调节": ["疲惫", "耗竭", "麻木", "压力", "情绪", "倦怠"],
    "人际关系": ["社交", "同伴", "人际", "同事"],
    "自我认同": ["认同", "自我", "价值感", "意义"],
    "家庭关系": ["家庭", "父母", "亲子"],
    "身体健康": ["睡眠", "作息", "身体"],
    "生命安全": ["危机"],
}.items():
    _PSYCH_KEYWORDS.setdefault(_dim, []).extend(_extra)


def _map_label(text, allowed: List[str], keywords: Dict[str, List[str]]) -> Optional[str]:
    """精确命中直接返回；否则取在原文中最早出现的关键词对应的类别。"""
    text = str(text or "").strip()
    if not text:
        return None
    if text in allowed:
        return text
    low = text.lower()
    hits = []
    for label, words in keywords.items():
        positions = [low.find(w) for w in words if w in low]
        if positions:
            hits.append((min(positions), allowed.index(label) if label in allowed else 99, label))
    return min(hits)[2] if hits else None


def normalize_result(result: Dict) -> Dict:
    """把深度分析结果中的梗形式、功能和心理维度归一到标准分类（就地修改并返回）。"""
    for t in (result or {}).get("topics") or []:
        meme = t.get("meme")
        if isinstance(meme, dict):
            for field, allowed, kw in (("form", MEME_FORMS, _FORM_KEYWORDS),
                                       ("function", MEME_FUNCTIONS, _FUNCTION_KEYWORDS)):
                raw = str(meme.get(field) or "").strip()
                label = _map_label(raw, allowed, kw)
                if raw and label != raw:
                    meme[field + "_detail"] = raw
                meme[field] = label or ""
        dims, details = [], []
        for raw in t.get("psych_dimensions") or []:
            label = _map_label(raw, PSYCH_DIMENSIONS, _PSYCH_KEYWORDS)
            if label and label not in dims:
                dims.append(label)
            if str(raw).strip() and label != str(raw).strip():
                details.append(str(raw).strip())
        t["psych_dimensions"] = dims[:3]
        if details:
            t["psych_detail"] = details
    return result
