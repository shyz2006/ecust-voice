"""
本校社区检索（免费来源，研究检索优先使用）：

1. 本校贴吧实时吧内搜索：贴吧移动版公开搜索接口 /mo/q/search/thread（无需登录、无签名）；
2. 本校狐友圈 / 贴吧已采集帖子：CampusPulse 每 30 分钟采集并去标识化后的帖子（data/campus_pulse.db）。

隐私：沿用 CampusPulse 规则——正文脱敏（手机号 / 微信 / QQ / 邮箱 / 学号 / @提及 / 姓名），不返回作者；
含自伤自杀等危机信号的帖子不返回原文，只返回“已隐去 N 条”的计数提示，个体干预须按学校流程人工核查。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List

from loguru import logger

from utils.campus_index import GENERIC_TERMS, keywords

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PULSE_DB = Path(os.getenv("PULSE_DB_PATH", str(PROJECT_ROOT / "data" / "campus_pulse.db")))
TIEBA_FORUMS = [f.strip() for f in os.getenv("CAMPUS_TIEBA_FORUMS", "华东理工大学").split(",") if f.strip()]
_SEARCH_URL = "https://tieba.baidu.com/mo/q/search/thread"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"),
    "Referer": "https://tieba.baidu.com/",
}
_rate_lock = threading.Lock()
_last_call = [0.0]


def _privacy():
    from CampusPulse.sources.huyou import deidentify, mask_names
    from CampusPulse.lens import _CRISIS_WORDS

    try:
        from CampusPulse.campus import is_ad
    except Exception:  # pragma: no cover
        def is_ad(_text):
            return False
    return deidentify, mask_names, _CRISIS_WORDS, is_ad


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def _date(ts) -> str:
    try:
        ts = int(ts or 0)
    except (TypeError, ValueError):
        return ""
    if ts > 1e12:
        ts //= 1000
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else ""




def _weight(term: str) -> float:
    return 0.5 if term in GENERIC_TERMS else 1.0


def _covered(text: str, terms: List[str]) -> float:
    return sum(_weight(t) for t in terms if t in text)


def _need(terms: List[str]) -> float:
    total = sum(_weight(t) for t in terms)
    specific = [t for t in terms if _weight(t) == 1.0]
    return max(total * 0.5, 1.0 if specific else 0.5)


def _coverage(text: str, terms: List[str]) -> float:
    total = sum(_weight(t) for t in terms) or 1.0
    return _covered(text, terms) / total


def _has_specific(text: str, terms: List[str]) -> bool:
    specific = [t for t in terms if _weight(t) == 1.0]
    return not specific or any(t in text for t in specific)


def _fetch_tieba(forum: str, word: str) -> List[Dict]:
    import requests

    for attempt in range(2):
        with _rate_lock:  # 与其他线程 / 引擎共享访问节奏
            wait = 1.5 - (time.time() - _last_call[0])
            if wait > 0:
                time.sleep(wait)
            _last_call[0] = time.time()
        try:
            resp = requests.get(_SEARCH_URL, params={"word": word, "fname": forum, "pn": 1, "rn": 30, "st": 5},
                                headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            return ((resp.json() or {}).get("data") or {}).get("post_list") or []
        except Exception as exc:
            if attempt == 0:
                time.sleep(2)
                continue
            logger.warning(f"[本校检索] 贴吧吧内搜索失败 {forum}: {exc}")
    return []


def tieba_search(query: str, limit: int = 8) -> Dict[str, object]:
    """本校贴吧实时吧内搜索。返回 {"results": [...], "hidden_crisis": n}。"""
    deidentify, mask_names, crisis_words, is_ad = _privacy()
    terms = keywords(query, limit=4)
    if not terms:
        return {"results": [], "hidden_crisis": 0}
    word = " ".join(terms)
    try:  # 同一检索 6 小时内复用（两个引擎、多个段落常会查相同内容）
        from utils import search_gateway

        cached = search_gateway.cache_get("tieba-live", word, "sixHours", limit, False)
    except Exception:
        search_gateway, cached = None, None
    if cached is not None:
        return cached
    results, hidden, seen = [], 0, set()
    # 贴吧搜索是“全部词都要出现”：先用最具体的两个词，结果少时再单用最具体的词放宽
    specific = [t for t in terms if _weight(t) == 1.0] or terms
    words = [" ".join(specific[:2])]
    if len(specific) > 1:
        words.append(specific[0])
    for forum in TIEBA_FORUMS:
        posts = []
        for w in words:
            got = _fetch_tieba(forum, w)
            posts += got
            if len(got) >= 10:
                break
        for p in posts:
            tid = str(p.get("tid") or "")
            title = _clean(p.get("title"))
            body = _clean(p.get("content"))
            raw = f"{title} {body}"
            if (not tid or tid in seen or is_ad(raw) or _covered(raw, terms) < _need(terms)
                    or not _has_specific(raw, terms)):
                continue
            seen.add(tid)
            if any(w in raw for w in crisis_words):
                hidden += 1
                continue
            text = mask_names(deidentify(body))[:400]
            results.append({
                "title": mask_names(deidentify(title))[:80] or text[:40],
                "url": f"https://tieba.baidu.com/p/{tid}",
                "snippet": text,
                "published": _date(p.get("time") or p.get("create_time")),
                "site": f"{forum}吧",
                "kind": "tieba-live",
                "coverage": _coverage(raw, terms),
            })
    results.sort(key=lambda r: (r["coverage"], r["published"]), reverse=True)
    out = {"results": results[:limit], "hidden_crisis": hidden}
    if search_gateway is not None:
        search_gateway.cache_put("tieba-live", word, "sixHours", limit, False, out)
    return out


def stored_posts(query: str, limit: int = 8, days: int = 365) -> Dict[str, object]:
    """在 CampusPulse 已采集的本校狐友圈 / 贴吧帖子（已去标识化）中检索。"""
    if not PULSE_DB.exists():
        return {"results": [], "hidden_crisis": 0}
    _, mask_names, crisis_words, is_ad = _privacy()
    terms = keywords(query)
    if not terms:
        return {"results": [], "hidden_crisis": 0}
    since = int(time.time()) - days * 86400
    try:
        conn = sqlite3.connect(f"file:{PULSE_DB}?mode=ro", uri=True, timeout=10)
        rows = conn.execute(
            "SELECT source, title, extra, batch_ts FROM snapshots WHERE source IN ('huyou-school','tieba-school') "
            "AND batch_ts >= ? ORDER BY batch_ts DESC", (since,)).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        logger.warning(f"[本校检索] 读取本校帖子失败: {exc}")
        return {"results": [], "hidden_crisis": 0}
    best: Dict[str, Dict] = {}
    hidden = set()
    for source, title, extra, batch_ts in rows:
        try:
            ex = json.loads(extra or "{}")
        except ValueError:
            ex = {}
        content = ex.get("content") or title or ""
        if content in best or content in hidden or is_ad(content):
            continue
        if _covered(content, terms) < _need(terms) or not _has_specific(content, terms):
            continue
        if any(w in content for w in crisis_words):
            hidden.add(content)
            continue
        is_tieba = source == "tieba-school"
        best[content] = {
            "title": mask_names(content)[:80],
            "url": ex.get("link") or "https://hy.sns.sohu.com/?tab=circle",
            "snippet": mask_names(content)[:400],
            "published": _date(ex.get("published")) or _date(batch_ts),
            "site": ex.get("circle") or ("本校贴吧" if is_tieba else "本校狐友圈"),
            "kind": "tieba-stored" if is_tieba else "huyou-stored",
            "coverage": _coverage(content, terms),
            "engagement": int(ex.get("comments") or 0),
        }
    results = sorted(best.values(), key=lambda r: (r["coverage"], r["engagement"], r["published"]), reverse=True)
    return {"results": results[:limit], "hidden_crisis": len(hidden)}
