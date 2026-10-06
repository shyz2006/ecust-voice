"""
编排器可调度的工作者（worker）

工具型工作者（不调用 LLM）：热榜侦察员 TrendScout、网络检索员 WebResearcher、梗词典 MemeMemory
推理型工作者（调用 LLM）：规划者 Planner、单智能体写手 SoloWriter、
                         专家 Interpreter / PsychLens / ActivityDesigner、修订者 Reviser

所有推理型工作者只能引用证据池里的证据编号（H=热榜，W=网页，M=梗词典记忆），
中心验证器据此检查"有没有编造依据"。
"""

import json
import time
from typing import Dict, List, Optional

from .. import llm, search, storage
from ..burst import tokenize
from . import sources_quality
from ..lens import MEME_FORMS, MEME_FUNCTIONS, PSYCH_DIMENSIONS, campus_score
from .analysis_options import prompt as selected_directions


class EvidencePool:
    def __init__(self):
        self.items: Dict[str, Dict] = {}
        self._counters = {"H": 0, "W": 0, "M": 0}
        self._urls = set()

    def add(self, kind: str, item: Dict) -> Optional[str]:
        url = item.get("url")
        if url and url in self._urls:
            return None
        if url:
            self._urls.add(url)
        self._counters[kind] += 1
        eid = f"{kind}{self._counters[kind]}"
        tier = sources_quality.classify(kind, url or "")
        self.items[eid] = {"id": eid, "kind": kind, **item, "tier": tier,
                           "tier_label": sources_quality.TIER_LABELS[tier],
                           "domain": sources_quality.domain(url or "") or ("热榜" if kind == "H" else "梗词典")}
        return eid

    def ids(self) -> set:
        return set(self.items)

    fact_pack: Optional[str] = None

    def brief(self, max_chars: int = 9000) -> str:
        """给推理型专家看的证据：有事实包时用事实包（短、结构化），否则用原始证据。"""
        return self.fact_pack or self.render(max_chars)

    def render(self, max_chars: int = 9000) -> str:
        lines = []
        for eid, it in self.items.items():
            if it["kind"] == "H":
                lines.append(f"[{eid}] 热榜：{it['title']}｜平台 {it.get('sources', '')}｜最好名次 {it.get('best_rank', '?')}"
                             f"｜上榜 {it.get('n_batches', 1)} 次{('｜' + it['note']) if it.get('note') else ''}")
            elif it["kind"] == "W":
                lines.append(f"[{eid}]（{it['tier']}级·{it['tier_label']}）网页：{it['title']}（{it.get('site', '')} "
                             f"{it.get('date', '')[:10]}）{it.get('snippet', '')[:300]}")
            else:
                lines.append(f"[{eid}] 梗词典记忆：{it['title']}：{it.get('snippet', '')}")
        text = "\n".join(lines)
        return text[:max_chars] if text else "（证据池为空）"

    def as_list(self) -> List[Dict]:
        return list(self.items.values())


# ------------------------------------------------------------ 工具型工作者

def trend_scout(query: str, intent: str, keywords: List[str], pool: EvidencePool) -> Dict:
    started = time.time()
    added = 0
    if intent == "trend_scan":
        latest = storage.latest_topics()
        topics = sorted(latest["topics"], key=lambda t: -campus_score(t))[:12]
        for t in topics:
            lens = t.get("lens") or {}
            note = "；".join(filter(None, [
                lens.get("category"),
                ("梗:" + lens["meme"]["meaning"]) if lens.get("meme") else "",
                ("心理维度:" + "/".join(lens.get("psych_dimensions") or [])) if lens.get("psych_dimensions") else "",
                ("心理危机:" + lens["crisis_level"]) if lens.get("crisis_level", "无") != "无" else "",
                ("内容风险:" + lens["content_risk"]) if lens.get("content_risk", "无") != "无" else "",
            ]))
            if pool.add("H", {"title": t["label"], "sources": ",".join(t["sources"]), "best_rank": t["best_rank"],
                              "n_batches": 1, "url": (t.get("entries") or [{}])[0].get("url"), "note": note}):
                added += 1
    else:
        terms = list(dict.fromkeys([*keywords, *tokenize(query)]))
        since = int(time.time()) - 7 * 86400
        for row in storage.search_titles(terms, since):
            if pool.add("H", {"title": row["title"], "sources": row["sources"], "best_rank": row["best_rank"],
                              "n_batches": row["n_batches"], "url": row["url"]}):
                added += 1
    return {"worker": "TrendScout", "added": added, "seconds": round(time.time() - started, 2)}


def web_researcher(queries: List[str], pool: EvidencePool, seen: set, per_query: int = 6) -> Dict:
    started = time.time()
    added, errors, ran = 0, [], []
    for q in queries[:3]:
        q = q.strip()
        if not q or q in seen:
            continue
        seen.add(q)
        ran.append(q)
        try:
            for r in search.web_search(q, count=per_query):
                if pool.add("W", r):
                    added += 1
        except search.SearchUnavailable as exc:
            errors.append(str(exc))
    return {"worker": "WebResearcher", "queries": ran, "added": added, "errors": errors,
            "seconds": round(time.time() - started, 2)}


def meme_memory(query: str, pool: EvidencePool) -> Dict:
    """记忆模块：复用此前经过验证的梗解读。"""
    added = 0
    for term in set(tokenize(query)):
        blob = storage.kv_get("meme:" + term)
        if not blob:
            continue
        card = json.loads(blob)
        if pool.add("M", {"title": term, "snippet": card.get("meaning", "")[:200]}):
            added += 1
    return {"worker": "MemeMemory", "added": added}


def remember_memes(result: Dict) -> None:
    for t in result.get("topics") or []:
        meme = t.get("meme")
        if isinstance(meme, dict) and meme.get("meaning") and t.get("name"):
            storage.kv_set("meme:" + t["name"].strip().lower(),
                           json.dumps(meme, ensure_ascii=False).encode("utf-8"))


# ------------------------------------------------------------ 推理型工作者

ROLE = ("你在高校心理健康教育中心工作，熟悉大学生网络文化、短视频生态与心理健康教育。"
        "你的读者是心理老师，他们需要了解学生在关注什么、为什么关注、可以怎样借势开展活动。"
        "只使用证据池中的信息陈述事实，每条事实性内容都要在 evidence 字段引用证据编号；"
        "证据不足时明确写“证据不足”，不要编造出处、数据或事件细节。"
        "what_happened 只写证据中能直接看到的观察事实；why_students_care 是你的推断，要用“可能”“或许”等措辞；"
        "证据标注了来源等级（A 官方/主流、B 平台原帖、C 普通媒体、D 梗百科/自媒体），关键事实优先引用 A/B 级且尽量多来源互证。"
        "涉及自伤、自杀等内容时，不描述方式细节，并提醒老师启动危机干预流程。")

RISK_RULES = ("风险分两个独立维度：crisis_level 只表示学生心理危机信号（自伤自杀、严重心理困扰、校园暴力受害等），"
              "一般社会新闻、诈骗、谣言都应为“无”；content_risk 表示内容安全或模仿风险（危险挑战、诈骗、网暴、极端内容、谣言）。"
              "evidence 数组只能放证据编号字符串，如 [\"H1\", \"W3\"]，说明文字写在正文字段里。"
              "risk_notes 与 talking_points 必须是字符串数组。")

LABEL_RULES = (f"标签取值约束：meme.form 只能从 {MEME_FORMS} 中选一个；meme.function 只能从 {MEME_FUNCTIONS} 中选一个；"
               f"psych_dimensions 只能从 {PSYCH_DIMENSIONS} 中选 0~3 个。补充说明写进 meaning / usage / why_students_care，"
               "不要写进标签字段。" + RISK_RULES)

OUTPUT_SCHEMA = """{
  "summary": "120字内的总览，说明这是什么、学生为何关注",
  "topics": [{
     "name": "话题/梗名称",
     "what_happened": "发生了什么/梗的来龙去脉",
     "why_students_care": "学生关注的心理动因",
     "meme": {"form": "形式", "function": "功能", "meaning": "含义", "usage": "典型用法示例"} 或 null,
     "psych_dimensions": ["学业压力", ...],
     "crisis_level": "无|关注|高危",
     "content_risk": "无|低|中|高",
     "evidence": ["H1", "W2"]
  }],
  "emotional_tone": "整体情绪基调",
  "risk_notes": ["需要老师注意的点"],
  "activities": [{
     "title": "活动名称", "format": "形式（工作坊/团辅/短视频征集/班会…）", "target": "对象",
     "steps": ["步骤1", "步骤2"], "short_video_idea": "可借鉴的短视频/转场玩法",
     "cautions": "注意事项", "evidence": ["H1"]
  }],
  "talking_points": ["老师与学生沟通时可用的切入语"]
}"""


def planner(query: str, profile: Dict, pool: EvidencePool, meter) -> Dict:
    """Magentic-One 任务账本：已知事实 / 待查事实 / 待推导事实 / 合理猜测 / 计划。"""
    prompt = (selected_directions(profile) + f"老师的问题：{query}\n任务类型：{profile['intent_label']}\n"
              f"已有证据：\n{pool.render(3000)}\n\n"
              "请建立任务账本，输出 JSON："
              '{"facts_given": [], "facts_to_lookup": [], "facts_to_derive": [], "educated_guesses": [], '
              '"keywords": ["用于检索热榜的2~5个关键词"], "search_queries": ["最多3条博查搜索语句"], "plan": ["步骤"]}')
    ledger = llm.chat_json(ROLE, prompt, meter=meter)
    if not isinstance(ledger, dict):
        ledger = {}
    ledger.setdefault("keywords", [])
    ledger.setdefault("search_queries", [])
    return ledger


def default_queries(query: str, intent: str) -> List[str]:
    if intent == "meme_explain":
        return [f"{query} 梗 出处 含义", f"{query} 网络流行语"]
    if intent == "trend_scan":
        return ["大学生 最近 热门话题", "最近流行的网络梗 大学生"]
    if intent == "activity_design":
        return [query, f"{query} 高校 心理健康 活动 案例"]
    return [query, f"{query} 最新进展"]


def solo_writer(query: str, profile: Dict, ledger: Dict, pool: EvidencePool, meter, max_tokens: int = None) -> Dict:
    prompt = (selected_directions(profile) + f"老师的问题：{query}\n任务类型：{profile['intent_label']}\n"
              f"任务账本：{json.dumps(ledger, ensure_ascii=False)[:1500]}\n\n证据池：\n{pool.render()}\n\n"
              f"请独立完成全部分析，输出 JSON，结构如下：\n{OUTPUT_SCHEMA}\n{LABEL_RULES}")
    return llm.chat_json(ROLE, prompt, meter=meter, max_tokens=max_tokens)


def interpreter(query: str, profile: Dict, pool: EvidencePool, meter, max_tokens: int = None) -> Dict:
    prompt = (selected_directions(profile) + f"老师的问题：{query}\n任务类型：{profile['intent_label']}\n证据池：\n{pool.brief()}\n\n"
              "你是【热点/梗解读专家】。只负责讲清楚是什么、怎么来的、学生为何关注。输出 JSON："
              '{"summary": "", "topics": [{"name": "", "what_happened": "", "why_students_care": "", '
              '"meme": {"form": "", "function": "", "meaning": "", "usage": ""} 或 null, "evidence": []}]}\n' + LABEL_RULES)
    return llm.chat_json(ROLE, prompt, meter=meter, max_tokens=max_tokens)


def psych_lens(query: str, profile: Dict, pool: EvidencePool, meter, max_tokens: int = None) -> Dict:
    prompt = (selected_directions(profile) + f"老师的问题：{query}\n证据池：\n{pool.brief()}\n\n"
              "你是【心理透镜专家】。从大学生心理需求角度分析这些热点折射出的情绪与压力源，"
              "不对任何个人做诊断。输出 JSON："
              '{"emotional_tone": "", "per_topic": [{"name": "", "psych_dimensions": [], "crisis_level": "无|关注|高危", "content_risk": "无|低|中|高"}], '
              '"risk_notes": [], "talking_points": []}\n' + LABEL_RULES)
    return llm.chat_json(ROLE, prompt, meter=meter, max_tokens=max_tokens)


def activity_designer(query: str, profile: Dict, draft: Dict, pool: EvidencePool, meter, max_tokens: int = None) -> Dict:
    prompt = (selected_directions(profile) + f"老师的问题：{query}\n已有解读：{json.dumps(draft, ensure_ascii=False)[:3500]}\n"
              f"证据池：\n{pool.brief(4000)}\n\n"
              "你是【心理活动策划专家】。借助学生正在关注的热点、梗或短视频玩法，设计 2~3 个可落地的心理健康教育活动。"
              "要求：正向引导、不消费负面事件、不暴露个人隐私、适合高校心理中心组织。输出 JSON："
              '方案必须有目标、对象、时间、准备材料、可执行步骤和效果评估，不能只有活动形式。'
              '{"activities": [{"title": "", "format": "", "target": "", "duration": "", "materials": [], "evaluation": "", "steps": [], "short_video_idea": "", '
              '"cautions": "", "evidence": []}]}')
    return llm.chat_json(ROLE, prompt, meter=meter, max_tokens=max_tokens)


def reviser(query: str, draft: Dict, issues: List[str], pool: EvidencePool, meter, max_tokens: int = None, profile: Dict = None) -> Dict:
    prompt = (selected_directions(profile or {}) + f"老师的问题：{query}\n当前草稿：{json.dumps(draft, ensure_ascii=False)[:6000]}\n\n"
              f"中心验证器发现的问题：\n- " + "\n- ".join(issues) +
              f"\n\n证据池：\n{pool.render()}\n\n请逐条修正问题（证据不足的内容删除或标注“证据不足”），"
              f"输出完整 JSON，结构如下：\n{OUTPUT_SCHEMA}\n{LABEL_RULES}")
    return llm.chat_json(ROLE, prompt, meter=meter, max_tokens=max_tokens)


def fact_pack(query: str, pool: EvidencePool, meter) -> str:
    """把证据压缩成结构化事实包（≤25 条、每条带证据编号），供多个专家共享，避免各自重复携带全文。"""
    rows = llm.chat_json(
        "你是研究助理，只做信息抽取，不做推断。",
        f"问题：{query}\n证据：\n{pool.render()}\n\n抽取与问题相关的关键事实（最多 25 条，每条 50 字内，保留原证据编号与来源等级），"
        '输出 JSON 数组：[{"id": "W3", "fact": ""}]', meter=meter, max_tokens=1500)
    lines = [f"[{r.get('id')}]（{pool.items[r['id']]['tier']}级）{str(r.get('fact'))[:80]}"
             for r in rows if isinstance(r, dict) and r.get("id") in pool.items] if isinstance(rows, list) else []
    return "\n".join(lines)
