"""
分析结果的结构规范化（在中心验证之前执行）

模型经常不严格遵守输出契约，例如：
- 把整段事实说明塞进 evidence 数组：["[H1] 哔哩哔哩热榜出现……", "[W1][W2] 相关报道……"]
- 把 risk_notes / talking_points 写成对象：[{"note": "...", "evidence": [...]}]
- 仍使用旧的单一 risk 字段

如果不先规范化，验证器会把有效证据误判为“伪造证据”，前端会显示 [object Object]。
这里只做无损的结构整理：证据编号从文字中提取，文字本身保留在 evidence_notes。
"""

import re
from typing import Any, Dict, List

EVIDENCE_ID_RE = re.compile(r"(?<![A-Za-z0-9])([HWMFB]\d{1,3})(?![0-9])")

CRISIS_LEVELS = ["无", "关注", "高危"]
CONTENT_RISKS = ["无", "低", "中", "高"]


def extract_evidence(raw: Any) -> Dict[str, List[str]]:
    """把 evidence 字段拆成 {ids: [...], notes: [...]}；纯编号条目不产生 note。"""
    items = raw if isinstance(raw, list) else ([raw] if raw else [])
    ids: List[str] = []
    notes: List[str] = []
    for item in items:
        if isinstance(item, dict):
            item = " ".join(str(v) for v in item.values() if isinstance(v, (str, int, float)))
        text = str(item or "").strip()
        if not text:
            continue
        found = EVIDENCE_ID_RE.findall(text)
        for eid in found:
            if eid not in ids:
                ids.append(eid)
        rest = EVIDENCE_ID_RE.sub("", text).strip(" []【】,，;；、")
        if rest and len(rest) > 1:
            notes.append(text)
    return {"ids": ids, "notes": notes}


def _to_text(value: Any) -> str:
    """对象 → 可读文本：优先取常见文本字段，并把其 evidence 编号以 [H1] 形式附在末尾。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "note", "content", "point", "tip", "suggestion", "risk", "message", "value"):
            if isinstance(value.get(key), str) and value[key].strip():
                text = value[key].strip()
                break
        else:
            text = "；".join(str(v) for v in value.values() if isinstance(v, str) and v.strip())
        ev = extract_evidence(value.get("evidence"))["ids"]
        if ev:
            text += " " + "".join(f"[{e}]" for e in ev)
        return text
    if isinstance(value, (list, tuple)):
        return "；".join(_to_text(v) for v in value if v)
    return str(value) if value is not None else ""


def _text_list(value: Any) -> List[str]:
    if not value:
        return []
    if not isinstance(value, list):
        value = [value]
    return [t for t in (_to_text(v) for v in value) if t]


def _pick(value: Any, allowed: List[str], default: str) -> str:
    value = str(value or "").strip()
    return value if value in allowed else default


def _split_legacy_risk(unit: Dict) -> None:
    """旧的单一 risk 字段 → 心理危机等级 / 内容安全风险 两个维度（保守映射）。"""
    legacy = unit.pop("risk", None)
    if "crisis_level" not in unit:
        text = _to_text({k: v for k, v in unit.items() if isinstance(v, str)})
        crisis_words = re.search(r"自杀|轻生|自伤|自残|跳楼|割腕|遗书|校园暴力|霸凌", text)
        unit["crisis_level"] = "关注" if (legacy == "重点" and crisis_words) else "无"
    if "content_risk" not in unit:
        unit["content_risk"] = {"重点": "中", "关注": "低"}.get(legacy, "无")


def normalize_output(result: Any) -> Dict:
    """就地整理并返回规范化的分析结果。"""
    if not isinstance(result, dict):
        return {}
    result["summary"] = _to_text(result.get("summary"))
    result["emotional_tone"] = _to_text(result.get("emotional_tone"))
    result["risk_notes"] = _text_list(result.get("risk_notes"))
    result["talking_points"] = _text_list(result.get("talking_points"))

    topics = [t for t in (result.get("topics") or []) if isinstance(t, dict)]
    for t in topics:
        ev = extract_evidence(t.get("evidence"))
        t["evidence"], t["evidence_notes"] = ev["ids"], ev["notes"]
        for key in ("name", "what_happened", "why_students_care"):
            t[key] = _to_text(t.get(key))
        _split_legacy_risk(t)
        t["crisis_level"] = _pick(t.get("crisis_level"), CRISIS_LEVELS, "无")
        t["content_risk"] = _pick(t.get("content_risk"), CONTENT_RISKS, "无")
        if not isinstance(t.get("psych_dimensions"), list):
            t["psych_dimensions"] = _text_list(t.get("psych_dimensions"))
        meme = t.get("meme")
        if meme is not None and not isinstance(meme, dict):
            t["meme"] = {"meaning": _to_text(meme)} if _to_text(meme) else None
    result["topics"] = topics

    acts = [a for a in (result.get("activities") or []) if isinstance(a, dict)]
    for a in acts:
        ev = extract_evidence(a.get("evidence"))
        a["evidence"], a["evidence_notes"] = ev["ids"], ev["notes"]
        a["steps"] = _text_list(a.get("steps"))
        a['materials'] = _text_list(a.get('materials'))
        for key in ("title", "format", "target", "duration", "evaluation", "short_video_idea", "cautions"):
            a[key] = _to_text(a.get(key))
    result["activities"] = acts
    return result
