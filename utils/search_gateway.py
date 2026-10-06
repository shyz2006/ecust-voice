"""
检索网关：所有博查（Bocha）调用的统一入口，目标是把付费检索降到最少。

每次检索按顺序：
1. 结果缓存：相同检索（归一化后的查询词 + 时效参数）在有效期内直接复用；Query / Media 引擎、多个任务共享；
2. 免费本地来源：本校贴吧实时吧内搜索、已采集的本校狐友圈 / 贴吧帖子、学校官网索引；
3. 博查兜底：本地结果不足时才调用，且受每个研究任务的调用上限（BOCHA_MAX_CALLS_PER_TASK）约束；
   不属于研究任务的调用（如校园脉搏）受每日上限（BOCHA_MAX_CALLS_PER_DAY_OTHER）约束。

研究任务 ID 由后台 worker 写入环境变量 BETTAFISH_TASK_ID。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("SEARCH_GATEWAY_DB", str(PROJECT_ROOT / "data" / "search_gateway.sqlite3")))
TASK_CAP = int(os.getenv("BOCHA_MAX_CALLS_PER_TASK", "5") or 5)
OTHER_DAILY_CAP = int(os.getenv("BOCHA_MAX_CALLS_PER_DAY_OTHER", "30") or 30)
LOCAL_ENOUGH = int(os.getenv("SEARCH_LOCAL_ENOUGH", "4") or 4)
_TTL_HOURS = {"oneDay": 2, "sixHours": 6, "oneWeek": 12, "oneMonth": 24}
DEFAULT_TTL_HOURS = float(os.getenv("SEARCH_CACHE_TTL_HOURS", "72"))


# ---------------------------------------------------------------- 存储
def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY, created REAL, count INTEGER, answer INTEGER, query TEXT, payload TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS usage (
        scope TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0, updated REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        ts REAL, scope TEXT, kind TEXT, query TEXT, local INTEGER, detail TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_scope ON events(scope)")
    return conn


def current_scope() -> str:
    task_id = os.getenv("BETTAFISH_TASK_ID", "").strip()
    return task_id or "other:" + time.strftime("%Y-%m-%d")


def _cap(scope: str) -> int:
    """研究任务默认 BOCHA_MAX_CALLS_PER_TASK 次；任务 metadata 中的 bocha_cap 可单独放宽或收紧。"""
    if scope.startswith("other:"):
        return OTHER_DAILY_CAP
    try:
        meta = json.loads((PROJECT_ROOT / "runtime" / "tasks" / scope / "metadata.json").read_text(encoding="utf-8"))
        if meta.get("bocha_cap") is not None:
            return max(0, int(meta["bocha_cap"]))
    except (OSError, ValueError, TypeError):
        pass
    return TASK_CAP


def _normalize(query: str) -> str:
    return re.sub(r"[\s　，,。.；;：:！!？?、\"'“”‘’（）()【】\[\]]+", "", (query or "").lower())


def _cache_key(endpoint: str, query: str, freshness: str) -> str:
    raw = json.dumps([endpoint, _normalize(query), freshness or ""], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _event(scope: str, kind: str, query: str, local: int = 0, detail: str = "") -> None:
    try:
        conn = _connect()
        conn.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (time.time(), scope, kind, query[:200], local, detail[:300]))
        conn.close()
    except sqlite3.Error:
        pass


def cache_get(endpoint: str, query: str, freshness: str, count: int, answer: bool) -> Optional[dict]:
    ttl = _TTL_HOURS.get(freshness or "", DEFAULT_TTL_HOURS) * 3600
    try:
        conn = _connect()
        row = conn.execute("SELECT created, count, answer, payload FROM cache WHERE key=?",
                           (_cache_key(endpoint, query, freshness),)).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row or time.time() - row[0] > ttl:
        return None
    if row[1] < count or (answer and not row[2]):
        return None
    try:
        return json.loads(row[3])
    except ValueError:
        return None


def cache_put(endpoint: str, query: str, freshness: str, count: int, answer: bool, payload: dict) -> None:
    try:
        conn = _connect()
        conn.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?,?,?,?)",
                     (_cache_key(endpoint, query, freshness), time.time(), count, int(answer), query[:200],
                      json.dumps(payload, ensure_ascii=False)))
        conn.close()
    except sqlite3.Error as exc:
        logger.debug(f"[检索网关] 写缓存失败: {exc}")


def try_consume(scope: str) -> bool:
    """原子地占用一次博查额度；多个引擎进程共享同一计数。"""
    cap = _cap(scope)
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT calls FROM usage WHERE scope=?", (scope,)).fetchone()
        used = row[0] if row else 0
        if used >= cap:
            conn.execute("ROLLBACK")
            return False
        conn.execute("INSERT INTO usage(scope, calls, updated) VALUES(?, 1, ?) "
                     "ON CONFLICT(scope) DO UPDATE SET calls=calls+1, updated=excluded.updated", (scope, time.time()))
        conn.execute("COMMIT")
        return True
    except sqlite3.Error:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        return True  # 计数故障时不阻断检索
    finally:
        conn.close()


def refund(scope: str) -> None:
    """博查调用失败（未产生结果）时退回额度。"""
    try:
        conn = _connect()
        conn.execute("UPDATE usage SET calls=MAX(calls-1, 0) WHERE scope=?", (scope,))
        conn.close()
    except sqlite3.Error:
        pass


# ---------------------------------------------------------------- 本地来源
def local_search(query: str, limit: int = 10) -> Tuple[List[Dict], int]:
    """免费来源合并：本校贴吧实时搜索 → 已采集本校帖子 → 学校官网索引。返回 (结果, 隐去的危机帖数)。"""
    results: List[Dict] = []
    hidden = 0
    try:
        from utils import campus_sources

        live = campus_sources.tieba_search(query, limit=limit)
        stored = campus_sources.stored_posts(query, limit=limit)
        results += live["results"] + stored["results"]
        hidden += int(live["hidden_crisis"]) + int(stored["hidden_crisis"])
    except Exception as exc:
        logger.warning(f"[检索网关] 本校社区检索失败: {exc}")
    try:
        from utils import campus_index

        for r in campus_index.search(query, limit=limit):
            r = dict(r)
            r["kind"] = "official"
            results.append(r)
    except Exception as exc:
        logger.warning(f"[检索网关] 学校官网索引检索失败: {exc}")
    seen, merged = set(), []
    for r in sorted(results, key=lambda r: r.get("coverage", 0), reverse=True):
        key = r.get("url") if r.get("kind") != "huyou-stored" else r.get("snippet")
        if key in seen:
            continue
        seen.add(key)
        merged.append(r)
    return merged[:limit], hidden


_KIND_LABEL = {"tieba-live": "本校贴吧", "tieba-stored": "本校贴吧（已采集）",
               "huyou-stored": "本校狐友圈（去标识化）", "official": "学校官网"}


def describe(r: Dict) -> str:
    """把来源、日期写进摘要：研究引擎只读 标题 / 链接 / 摘要。"""
    bits = [_KIND_LABEL.get(r.get("kind"), "本地"), r.get("site") or ""]
    if r.get("published"):
        bits.append(f"发布日期 {r['published']}")
    if r.get("source"):
        bits.append(f"来源 {r['source']}")
    head = "｜".join(b for b in bits if b)
    return f"【{head}】{r.get('snippet') or ''}"


def crisis_notice(hidden: int) -> Optional[Dict]:
    if not hidden:
        return None
    return {"title": f"本校社区中有 {hidden} 条含心理危机信号的帖子已隐去原文",
            "url": "", "kind": "notice", "site": "",
            "snippet": (f"检索到 {hidden} 条含自伤自杀等危机信号的本校帖子，按隐私与危机干预原则不提供原文；"
                        "如需关注个体，请按学校心理危机干预流程由人工在原平台核查。")}


# ---------------------------------------------------------------- 博查入口
def bocha_search(query: str, count: int, freshness: str, answer: bool, endpoint: str,
                 remote: Callable[[], Optional[dict]], to_local_payload: Callable[[List[Dict]], dict],
                 merge: Callable[[dict, dict], dict]) -> dict:
    """
    返回博查格式的原始响应（dict）。
    remote(): 真正调用博查，失败返回 None；to_local_payload(results): 把本地结果转成博查格式；
    merge(local_payload, remote_payload): 本地结果在前合并。
    """
    scope = current_scope()
    local, hidden = local_search(query, limit=max(count, 6))
    notice = crisis_notice(hidden)
    local_payload = to_local_payload(local + ([notice] if notice else []))

    cached = cache_get(endpoint, query, freshness, count, answer)
    if cached is not None:
        _event(scope, "cache_hit", query, len(local))
        logger.info(f"[检索网关] 缓存命中：{query}（本地 {len(local)} 条）")
        return merge(local_payload, cached)

    strong = [r for r in local if r.get("coverage", 0) >= 0.8]
    if len(strong) >= LOCAL_ENOUGH:
        _event(scope, "local_only", query, len(local))
        logger.info(f"[检索网关] 本地来源充足（{len(strong)} 条高匹配），跳过博查：{query}")
        return local_payload

    if not try_consume(scope):
        _event(scope, "budget_block", query, len(local))
        logger.info(f"[检索网关] 本任务博查额度（{_cap(scope)} 次）已用完，仅用本地来源 {len(local)} 条：{query}")
        return local_payload

    payload = remote()
    if not payload:
        refund(scope)
        _event(scope, "bocha_failed", query, len(local))
        return local_payload
    cache_put(endpoint, query, freshness, count, answer, payload)
    _event(scope, "bocha", query, len(local))
    logger.info(f"[检索网关] 调用博查（本任务第 {usage(scope)}/{_cap(scope)} 次）：{query}（本地 {len(local)} 条）")
    return merge(local_payload, payload)


def usage(scope: str) -> int:
    try:
        conn = _connect()
        row = conn.execute("SELECT calls FROM usage WHERE scope=?", (scope,)).fetchone()
        conn.close()
        return row[0] if row else 0
    except sqlite3.Error:
        return 0


def stats(scope: Optional[str] = None, limit: int = 20) -> Dict[str, object]:
    conn = _connect()
    try:
        where, params = ("WHERE scope=?", (scope,)) if scope else ("", ())
        kinds = dict(conn.execute(f"SELECT kind, COUNT(*) FROM events {where} GROUP BY kind", params).fetchall())
        recent = conn.execute(
            "SELECT scope, SUM(kind='bocha'), SUM(kind='cache_hit'), SUM(kind='local_only'), SUM(kind='budget_block'), "
            "COUNT(*), MAX(ts) FROM events GROUP BY scope ORDER BY MAX(ts) DESC LIMIT ?", (limit,)).fetchall()
        return {
            "task_cap": TASK_CAP, "other_daily_cap": OTHER_DAILY_CAP, "events": kinds,
            "cache_entries": conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0],
            "by_scope": [{"scope": r[0], "bocha": r[1], "cache_hit": r[2], "local_only": r[3],
                          "budget_block": r[4], "searches": r[5],
                          "last": time.strftime("%Y-%m-%d %H:%M", time.localtime(r[6]))} for r in recent],
        }
    finally:
        conn.close()
