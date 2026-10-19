"""
中心验证器 —— 以 MAST 失败分类法为检查清单

Cemri et al., "Why Do Multi-Agent LLM Systems Fail?" (NeurIPS 2025) 把 MAS 失败归为
14 种模式、3 大类：系统设计问题 / 智能体间失配 / 任务验证缺失。其中"验证缺失或验证错误"
是最常见且最容易被忽视的一类；Kim et al. (2025) 也发现缺少中心验证的拓扑会放大错误。

BettaFish 原流程在论坛讨论之后直接进入报告生成，没有独立的验证环节。这里在编排器与
输出之间加一道确定性检查（可选再加 LLM 裁判），每项检查都标注对应的 MAST 失败模式，
检查结果既用于触发修订，也作为工作流选择器的奖励信号。
"""

import json
import re
from typing import Dict, List

from .. import llm
from ..burst import tokenize

_PLACEHOLDER_RE = re.compile(r"无法获取|未找到相关|暂无信息|无法回答|作为AI|作为一个AI")
_STIGMA_RE = re.compile(r"神经病|精神病人|疯子|脑残|玻璃心|矫情")
_CRISIS_RE = re.compile(r"自杀|轻生|跳楼|自残|割腕|遗书")
_CRISIS_GUIDE_RE = re.compile(r"危机干预|12356|心理援助热线|转介|心理中心值班")

CHECKS = [
    # (id, MAST 模式, 说明, 权重)
    ("spec", "FM-1.1 违背任务规格", "必需字段完整且符合任务类型", 0.12),
    ("derail", "FM-2.3 任务偏离", "输出围绕老师的问题展开", 0.08),
    ("premature", "FM-3.1 过早终止", "证据存在时不以“无法获取”敷衍", 0.05),
    ("grounding", "FM-3.3 验证错误", "事实性条目引用了真实存在的证据编号", 0.12),
    ("entail", "FM-3.3 主张—证据蕴含", "每条观察事实都被所引证据实际支持", 0.28),
    ("sources", "来源交叉验证", "关键事实有 A/B 级来源或至少两个独立来源", 0.10),
    ("repetition", "FM-1.3 步骤重复", "检索语句没有重复空转", 0.05),
    ("safety", "领域安全", "无污名化用语；危机话题附带干预提示", 0.20),
]
_SENT_RE = re.compile(r"(?<=[。！？；])")


def _check_spec(result: Dict, intent: str) -> List[str]:
    issues = []
    if not isinstance(result, dict):
        return ["输出不是 JSON 对象"]
    if not str(result.get("summary") or "").strip():
        issues.append("缺少 summary 总览")
    topics = result.get("topics") or []
    if not topics:
        issues.append("缺少 topics 话题解读")
    for t in topics:
        if not t.get("why_students_care"):
            issues.append(f"话题「{t.get('name', '?')}」缺少“学生为何关注”")
    if intent == "meme_explain" and not any(isinstance(t.get("meme"), dict) and t["meme"].get("meaning") for t in topics):
        issues.append("梗释义任务但没有给出 meme.meaning")
    if intent in ("activity_design", "trend_scan") and not (result.get("activities") or []):
        issues.append("缺少 activities 活动建议")
    for a in result.get("activities") or []:
        if not a.get("steps"):
            issues.append(f"活动「{a.get('title', '?')}」缺少可执行步骤")
    return issues


def _check_derail(result: Dict, query: str, intent: str) -> List[str]:
    if intent == "trend_scan":
        return []
    q_terms = set(tokenize(query)) - {"什么", "意思", "活动", "策划", "学生", "大学生", "心理"}
    if not q_terms:
        return []
    text = json.dumps(result, ensure_ascii=False).lower()
    hit = [t for t in q_terms if t in text]
    if len(hit) / len(q_terms) < 0.5:
        return [f"输出与问题关键词匹配度低（命中 {hit or '无'} / {sorted(q_terms)}），可能偏离任务"]
    return []


def _check_premature(result: Dict, n_evidence: int) -> List[str]:
    text = json.dumps(result, ensure_ascii=False)
    if n_evidence > 0 and _PLACEHOLDER_RE.search(text):
        return ["证据池非空，但输出包含“无法获取/暂无信息”等敷衍表述"]
    if n_evidence == 0:
        return ["证据池为空：结论缺乏依据，需补充检索"]
    return []


def _check_grounding(result: Dict, valid_ids: set) -> (List[str], float):
    issues = []
    units = list(result.get("topics") or []) + list(result.get("activities") or [])
    if not units:
        return issues, 0.0
    grounded = 0
    for u in units:
        cited = [str(e).strip("[]【】 ") for e in (u.get("evidence") or [])]
        fake = [e for e in cited if e not in valid_ids]
        name = u.get("name") or u.get("title") or "?"
        if fake:
            issues.append(f"「{name}」引用了不存在的证据编号 {fake}")
        if any(e in valid_ids for e in cited):
            grounded += 1
        elif "证据不足" not in json.dumps(u, ensure_ascii=False):
            issues.append(f"「{name}」没有引用任何证据，也未标注“证据不足”")
    return issues, grounded / len(units)


def _check_repetition(trace: List[Dict]) -> List[str]:
    queries = [q for step in trace for q in step.get("queries", [])]
    dup = {q for q in queries if queries.count(q) > 1}
    return [f"重复检索：{sorted(dup)}"] if dup else []


def _check_safety(result: Dict, evidence_text: str) -> List[str]:
    issues = []
    text = json.dumps(result, ensure_ascii=False)
    stigma = set(_STIGMA_RE.findall(text))
    if stigma:
        issues.append(f"出现可能污名化的用语 {sorted(stigma)}，请改为中性表述")
    # 只有“心理危机”才要求危机干预提示；诈骗、谣言等内容安全风险不触发，避免告警疲劳
    crisis = _CRISIS_RE.search(text + evidence_text) or any(
        t.get("crisis_level") in ("关注", "高危") for t in result.get("topics") or [])
    if crisis and not _CRISIS_GUIDE_RE.search(text):
        issues.append("涉及心理危机信号，但未提示危机干预流程（如转介心理中心、心理援助热线 12356）")
    return issues


def _claims(result: Dict) -> List[Dict]:
    """抽取需要证据支持的“观察事实”主张（推断与建议不在此列）。"""
    claims = []
    for ti, t in enumerate(result.get("topics") or []):
        ev = [e for e in t.get("evidence") or []]
        for sent in [x.strip() for x in _SENT_RE.split(str(t.get("what_happened") or "")) if len(x.strip()) >= 6][:5]:
            claims.append({"topic": ti, "field": "what_happened", "text": sent, "evidence": ev})
        meme = t.get("meme") if isinstance(t.get("meme"), dict) else {}
        if meme.get("meaning"):
            claims.append({"topic": ti, "field": "meme.meaning", "text": str(meme["meaning"]), "evidence": ev})
    return claims[:16]


def _check_entailment(result: Dict, pool, meter) -> (List[str], float, List[Dict], bool):
    """逐条判断“主张是否被其引用的证据蕴含”。返回 (问题, 得分, 主张明细, 是否存在不被支持的事实)。"""
    claims = _claims(result)
    if not claims:
        return [], 1.0, [], False
    lines = []
    for i, c in enumerate(claims, start=1):
        ev_text = "；".join(
            f"[{e}] {pool.items[e].get('title', '')} {str(pool.items[e].get('snippet', '') or pool.items[e].get('note', ''))[:220]}"
            for e in c["evidence"] if e in pool.items)[:900]
        lines.append(f"{i}. 主张：{c['text']}\n   所引证据：{ev_text or '（无）'}")
    prompt = ("逐条判断每个“主张”是否被其“所引证据”支持。只依据给出的证据文本，不用常识补全。"
              "verdict 取值：支持 / 部分支持 / 不支持 / 证据不足。输出 JSON 数组，元素为 "
              '{"i": 序号, "verdict": "", "note": "15字内理由"}。\n\n' + "\n".join(lines))
    try:
        rows = llm.chat_json("你是严格的事实核查员，只做文本蕴含判断。", prompt, temperature=0.0, meter=meter,
                             max_tokens=1200)
    except Exception as exc:
        return [f"蕴含检查未完成（模型不可用：{str(exc)[:40]}）"], 0.5, claims, False
    verdicts = {int(r.get("i", 0)): r for r in rows if isinstance(r, dict) and str(r.get("i", "")).isdigit()} \
        if isinstance(rows, list) else {}
    issues, total, unsupported = [], 0.0, False
    for i, c in enumerate(claims, start=1):
        v = verdicts.get(i) or {}
        c["verdict"] = v.get("verdict") if v.get("verdict") in ("支持", "部分支持", "不支持", "证据不足") else "证据不足"
        c["note"] = str(v.get("note") or "")[:40]
        total += {"支持": 1.0, "部分支持": 0.5}.get(c["verdict"], 0.0)
        if c["verdict"] == "不支持":
            unsupported = True
            issues.append(f"事实主张不被所引证据支持：“{c['text'][:40]}”（{c['note']}）")
        elif c["verdict"] in ("部分支持", "证据不足"):
            issues.append(f"事实主张证据{c['verdict']}：“{c['text'][:40]}”")
    return issues, total / len(claims), claims, unsupported


def _check_sources(result: Dict, pool) -> List[str]:
    issues = []
    for t in result.get("topics") or []:
        cited = [pool.items[e] for e in t.get("evidence") or [] if e in pool.items]
        if not cited:
            continue
        tiers = {c.get("tier") for c in cited}
        domains = {c.get("domain") for c in cited}
        if tiers <= {"D"}:
            issues.append(f"「{t.get('name', '?')}」只依据梗百科 / 自媒体来源，缺少平台原帖或主流媒体佐证")
        elif "A" not in tiers and len(domains) < 2:
            issues.append(f"「{t.get('name', '?')}」只有单一来源（{next(iter(domains))}），缺少交叉验证")
    return issues


def _llm_judge(query: str, result: Dict, evidence_text: str, meter) -> Dict:
    prompt = (f"老师的问题：{query}\n证据池：\n{evidence_text[:5000]}\n\n待审稿件：\n"
              f"{json.dumps(result, ensure_ascii=False)[:5000]}\n\n"
              "你是独立审稿人。逐条核对稿件中的事实是否被证据支持，活动建议是否安全可行、对心理老师是否有用。输出 JSON："
              '{"groundedness": 1-5, "usefulness": 1-5, "issues": ["具体问题，最多5条"]}')
    try:
        verdict = llm.chat_json("你是严格、简洁的事实核查员。", prompt, temperature=0.0, meter=meter)
        return verdict if isinstance(verdict, dict) else {}
    except Exception as exc:
        return {"error": str(exc)}


def verify(query: str, intent: str, result: Dict, pool, trace: List[Dict],
           use_judge: bool, meter=None) -> Dict:
    evidence_text = pool.render()
    grounding_issues, grounded_ratio = _check_grounding(result or {}, pool.ids())
    if meter is not None and result:
        entail_issues, entail_score, claims, unsupported = _check_entailment(result, pool, meter)
    else:  # 无模型时无法做蕴含判断：给中性分，并如实标注
        entail_issues, entail_score, claims, unsupported = (["未做蕴含检查（无模型）"], 0.5, [], False)
    per_check = {
        "spec": _check_spec(result, intent),
        "derail": _check_derail(result or {}, query, intent),
        "premature": _check_premature(result or {}, len(pool.ids())),
        "grounding": grounding_issues,
        "repetition": _check_repetition(trace),
        "entail": entail_issues,
        "sources": _check_sources(result or {}, pool),
        "safety": _check_safety(result or {}, evidence_text),
    }
    score = 0.0
    report = []
    for cid, mode, desc, weight in CHECKS:
        issues = per_check[cid]
        if cid == "grounding":
            passed_frac = grounded_ratio if not any("不存在" in i for i in issues) else grounded_ratio * 0.5
        elif cid == "entail":
            passed_frac = entail_score
        else:
            passed_frac = 1.0 if not issues else 0.0
        score += weight * passed_frac
        report.append({"id": cid, "mast": mode, "desc": desc, "passed": not issues, "issues": issues})

    judge = None
    if use_judge and result:
        judge = _llm_judge(query, result, evidence_text, meter)
        g, u = judge.get("groundedness"), judge.get("usefulness")
        if isinstance(g, (int, float)) and isinstance(u, (int, float)):
            score = 0.7 * score + 0.3 * ((g + u) / 10)
    all_issues = [i for c in report for i in c["issues"]]
    hard = [c["mast"] for c in report if c["issues"] and c["id"] in ("spec", "safety")]
    if judge and judge.get("issues"):
        all_issues += [f"[审稿人] {i}" for i in judge["issues"][:5]]
    # 规格、安全、伪造证据编号是硬约束，任一不通过都要求修订
    fabricated = any("不存在" in i for i in grounding_issues)
    if fabricated:
        hard.append("FM-3.3 伪造证据编号")
    if unsupported:
        hard.append("FM-3.3 事实主张不被证据支持")
    hard_fail = bool(hard)
    return {
        "score": round(score, 3),
        "passed": score >= 0.75 and not hard_fail,
        "hard_fail": hard_fail,
        "hard_fail_reasons": hard,
        "checks": report,
        "claims": claims,
        "judge": judge,
        "issues": all_issues,
    }
