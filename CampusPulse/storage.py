"""
轻量持久化层（SQLite）

CampusPulse 只保存公开热榜条目和聚合结果，不采集、不存储任何学生个人数据。
"""

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_ts INTEGER NOT NULL,
    source TEXT NOT NULL,
    rank INTEGER NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    extra TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_batch ON snapshots(batch_ts);
CREATE INDEX IF NOT EXISTS idx_snapshots_title ON snapshots(title);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_ts INTEGER NOT NULL,
    label TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topics_batch ON topics(batch_ts);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    query TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    topology TEXT NOT NULL,
    payload TEXT NOT NULL,
    auto_score REAL,
    status TEXT NOT NULL DEFAULT 'formal'
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    analysis_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    username TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value BLOB
);
"""

_lock = threading.Lock()
_initialized = False


def _db_path() -> Path:
    path = settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _migrate(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(feedback)")}
    if "username" not in cols:
        conn.execute("ALTER TABLE feedback ADD COLUMN username TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_analysis ON feedback(analysis_id, username)")

    cols = {r[1] for r in conn.execute("PRAGMA table_info(analyses)")}
    if "status" not in cols:
        # 旧记录按当时的验证结果回填：未通过的转为草稿，并退出工作流奖励统计
        conn.execute("ALTER TABLE analyses ADD COLUMN status TEXT NOT NULL DEFAULT 'formal'")
        for row in conn.execute("SELECT id, payload FROM analyses").fetchall():
            payload = json.loads(row[1])
            if payload.get("degraded"):
                status = "degraded"
            elif (payload.get("verdict") or {}).get("passed"):
                status = "formal"
            else:
                status = "draft"
            payload["status"] = status
            conn.execute(
                "UPDATE analyses SET status=?, payload=?, auto_score=CASE WHEN ?='formal' THEN auto_score END "
                "WHERE id=?",
                (status, json.dumps(payload, ensure_ascii=False), status, row[0]),
            )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS batches (
            batch_ts INTEGER PRIMARY KEY,
            status TEXT NOT NULL,              -- fetched | complete | failed | superseded
            fetched_at INTEGER NOT NULL,
            completed_at INTEGER,
            stats TEXT,
            error TEXT
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meme_signals (
            key TEXT NOT NULL,
            batch_ts INTEGER NOT NULL,
            kind TEXT NOT NULL,
            df INTEGER NOT NULL,
            PRIMARY KEY (key, batch_ts)
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS polls (
            token TEXT PRIMARY KEY,
            created_ts INTEGER NOT NULL,
            closes_ts INTEGER NOT NULL,
            created_by TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            items TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS poll_votes (
            token TEXT NOT NULL,
            voter TEXT NOT NULL,          -- 随机 cookie 的哈希，不含任何身份信息
            ts INTEGER NOT NULL,
            answers TEXT NOT NULL,        -- {候选 key: {"seen": 0/1/2, "follow": 0/1}}
            PRIMARY KEY (token, voter)
        )""")
    # 旧库回填：有话题的批次视为完整，只有快照的批次视为已抓取未分析
    conn.execute("""
        INSERT OR IGNORE INTO batches(batch_ts, status, fetched_at, completed_at)
        SELECT s.batch_ts,
               CASE WHEN EXISTS (SELECT 1 FROM topics t WHERE t.batch_ts = s.batch_ts) THEN 'complete' ELSE 'fetched' END,
               s.batch_ts,
               CASE WHEN EXISTS (SELECT 1 FROM topics t WHERE t.batch_ts = s.batch_ts) THEN s.batch_ts END
        FROM (SELECT DISTINCT batch_ts FROM snapshots) s""")


@contextmanager
def connect():
    global _initialized
    conn = sqlite3.connect(str(_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if not _initialized:
            with _lock:
                conn.executescript(_SCHEMA)
                _migrate(conn)
                from . import telemetry
                telemetry.initialize(conn)
                _initialized = True
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- snapshots

def save_snapshot(batch_ts: int, items: Iterable[Dict[str, Any]]) -> int:
    items = list(items)
    rows = [
        (
            batch_ts,
            it["source"],
            int(it["rank"]),
            it["title"],
            it.get("url"),
            json.dumps(it.get("extra") or {}, ensure_ascii=False),
        )
        for it in items
    ]
    with connect() as conn:
        conn.executemany(
            "INSERT INTO snapshots(batch_ts, source, rank, title, url, extra) VALUES (?,?,?,?,?,?)",
            rows,
        )
        from . import telemetry
        telemetry.record_rows(conn,items)
    return len(rows)


# ---------------------------------------------------------------- batches
# 批次的两阶段提交：fetched（原始快照已落库）→ complete（话题 + 草图 + 状态在同一事务提交）

def record_fetch(batch_ts: int, items: Iterable[Dict[str, Any]], stats: Dict[str, Any]) -> None:
    items = list(items)
    rows = [
        (batch_ts, it["source"], int(it["rank"]), it["title"], it.get("url"),
         json.dumps(it.get("extra") or {}, ensure_ascii=False))
        for it in items
    ]
    with connect() as conn:
        conn.executemany(
            "INSERT INTO snapshots(batch_ts, source, rank, title, url, extra) VALUES (?,?,?,?,?,?)", rows)
        conn.execute(
            "INSERT OR REPLACE INTO batches(batch_ts, status, fetched_at, stats) VALUES (?,?,?,?)",
            (batch_ts, "fetched", int(time.time()), json.dumps(stats, ensure_ascii=False)))
        from . import telemetry
        telemetry.record_rows(conn, items)


def commit_analysis(batch_ts: int, topics: List[Dict[str, Any]], kv_updates: Dict[str, bytes],
                    stats: Dict[str, Any], meme_rows: Optional[List[Dict[str, Any]]] = None) -> None:
    """话题、加速度草图等派生状态与批次完成标记原子提交；失败则整体回滚。"""
    with connect() as conn:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM topics WHERE batch_ts=?", (batch_ts,))
        conn.executemany(
            "INSERT INTO topics(batch_ts, label, payload) VALUES (?,?,?)",
            [(batch_ts, t["label"], json.dumps(t, ensure_ascii=False)) for t in topics],
        )
        for key, value in kv_updates.items():
            conn.execute(
                "INSERT INTO kv(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
        conn.executemany(
            "INSERT OR REPLACE INTO meme_signals(key, batch_ts, kind, df) VALUES (?,?,?,?)",
            [(m["key"], batch_ts, m["kind"], int(m["df"])) for m in meme_rows or []])
        old = conn.execute("SELECT stats FROM batches WHERE batch_ts=?", (batch_ts,)).fetchone()
        merged = {**(json.loads(old["stats"]) if old and old["stats"] else {}), **stats}  # 保留抓取阶段的错误与耗时
        conn.execute(
            "UPDATE batches SET status='complete', completed_at=?, stats=?, error=NULL WHERE batch_ts=?",
            (int(time.time()), json.dumps(merged, ensure_ascii=False), batch_ts))
        # 更早的未完成批次不再补做（草图必须按时间顺序更新）
        conn.execute("UPDATE batches SET status='superseded' WHERE batch_ts<? AND status IN ('fetched','failed')",
                     (batch_ts,))


def refresh_views(batch_ts: int, topics: List[Dict[str, Any]], kv_updates: Dict[str, bytes],
                  stats_patch: Dict[str, Any]) -> bool:
    """模型增强完成后原子替换该批次的话题与视图；若已有更新的完整批次则放弃（返回 False）。"""
    with connect() as conn:
        conn.execute("BEGIN")
        newer = conn.execute("SELECT 1 FROM batches WHERE status='complete' AND batch_ts>? LIMIT 1",
                             (batch_ts,)).fetchone()
        row = conn.execute("SELECT stats FROM batches WHERE batch_ts=? AND status='complete'", (batch_ts,)).fetchone()
        if newer or not row:
            return False
        conn.execute("DELETE FROM topics WHERE batch_ts=?", (batch_ts,))
        conn.executemany("INSERT INTO topics(batch_ts, label, payload) VALUES (?,?,?)",
                         [(batch_ts, t["label"], json.dumps(t, ensure_ascii=False)) for t in topics])
        for key, value in kv_updates.items():
            conn.execute("INSERT INTO kv(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (key, value))
        stats = json.loads(row["stats"] or "{}")
        stats.update(stats_patch)
        conn.execute("UPDATE batches SET stats=? WHERE batch_ts=?", (json.dumps(stats, ensure_ascii=False), batch_ts))
    return True


def recent_batches(limit: int = 30) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM batches ORDER BY batch_ts DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["stats"] = json.loads(d["stats"]) if d.get("stats") else {}
        out.append(d)
    return out


def analysis_costs(limit: int = 100) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT id, ts, workflow_id, status, payload FROM analyses ORDER BY id DESC LIMIT ?",
                            (limit,)).fetchall()
    out = []
    for r in rows:
        p = json.loads(r["payload"])
        out.append({"id": r["id"], "ts": r["ts"], "workflow": r["workflow_id"], "status": r["status"],
                    "intent": (p.get("profile") or {}).get("intent"),
                    "tokens": (p.get("usage") or {}).get("total_tokens"),
                    "seconds": (p.get("usage") or {}).get("wall_seconds"),
                    "calls": (p.get("usage") or {}).get("calls")})
    return out


def mark_batch_failed(batch_ts: int, error: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE batches SET status='failed', error=? WHERE batch_ts=?", (error[:500], batch_ts))


def latest_batch(status: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        if status:
            row = conn.execute("SELECT * FROM batches WHERE status=? ORDER BY batch_ts DESC LIMIT 1",
                               (status,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM batches ORDER BY batch_ts DESC LIMIT 1").fetchone()
    if not row:
        return None
    out = dict(row)
    out["stats"] = json.loads(out["stats"]) if out.get("stats") else None
    return out


def previous_batch_titles(before_ts: int) -> Dict[str, int]:
    """上一个完整批次中每个标题的最好名次，用于“新上榜 / 名次变化”。"""
    with connect() as conn:
        row = conn.execute(
            "SELECT batch_ts FROM batches WHERE status='complete' AND batch_ts<? ORDER BY batch_ts DESC LIMIT 1",
            (before_ts,)).fetchone()
        if not row:
            return {}
        rows = conn.execute("SELECT title, MIN(rank) AS r FROM snapshots WHERE batch_ts=? GROUP BY title",
                            (row["batch_ts"],)).fetchall()
    return {r["title"]: r["r"] for r in rows}


def recent_items(sources: List[str], since_ts: int) -> List[Dict[str, Any]]:
    """最近一段时间内指定来源的快照条目（extra 已解析）。"""
    marks = ",".join("?" for _ in sources)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT batch_ts, source, rank, title, url, extra FROM snapshots "
            f"WHERE batch_ts>=? AND source IN ({marks}) ORDER BY batch_ts",
            [since_ts, *sources]).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["extra"] = json.loads(d["extra"]) if d["extra"] else {}
        out.append(d)
    return out


def load_batch_items(batch_ts: int) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT source, rank, title, url, extra FROM snapshots WHERE batch_ts=?",
                            (batch_ts,)).fetchall()
    return [{**dict(r), "extra": json.loads(r["extra"]) if r["extra"] else {}} for r in rows]


def meme_history(keys: List[str], since_ts: int, before_ts: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
    before_ts = before_ts or 2 ** 40
    out: Dict[str, List[Dict[str, Any]]] = {}
    with connect() as conn:
        for i in range(0, len(keys), 400):
            chunk = keys[i:i + 400]
            marks = ",".join("?" for _ in chunk)
            for r in conn.execute(
                    f"SELECT key, batch_ts, df FROM meme_signals WHERE batch_ts>=? AND batch_ts<? AND key IN ({marks}) "
                    f"ORDER BY batch_ts", [since_ts, before_ts, *chunk]).fetchall():
                out.setdefault(r["key"], []).append({"batch_ts": r["batch_ts"], "df": r["df"]})
    return out


def batch_timestamps(limit: int = 50) -> List[int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT batch_ts FROM snapshots ORDER BY batch_ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [r["batch_ts"] for r in rows]


def load_batch(batch_ts: int) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT source, rank, title, url FROM snapshots WHERE batch_ts=? ORDER BY source, rank",
            (batch_ts,),
        ).fetchall()
    return [dict(r) for r in rows]


def title_history(titles: List[str], since_ts: int) -> Dict[str, List[Dict[str, Any]]]:
    """返回每个标题在 since_ts 之后各批次中的最好名次，用于画热度曲线。"""
    if not titles:
        return {}
    marks = ",".join("?" for _ in titles)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT title, batch_ts, MIN(rank) AS rank, COUNT(DISTINCT source) AS n_src "
            f"FROM snapshots WHERE batch_ts>=? AND title IN ({marks}) "
            f"GROUP BY title, batch_ts ORDER BY batch_ts",
            [since_ts, *titles],
        ).fetchall()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["title"], []).append(
            {"ts": r["batch_ts"], "rank": r["rank"], "sources": r["n_src"]}
        )
    return out


def search_titles(terms: List[str], since_ts: int, limit: int = 15) -> List[Dict[str, Any]]:
    """在历史热榜中检索包含任一关键词的标题，按上榜次数与最好名次排序。"""
    terms = [t for t in terms if t][:8]
    if not terms:
        return []
    cond = " OR ".join("title LIKE ?" for _ in terms)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT title, MIN(rank) AS best_rank, COUNT(DISTINCT batch_ts) AS n_batches,
                   GROUP_CONCAT(DISTINCT source) AS sources,
                   MIN(batch_ts) AS first_seen, MAX(batch_ts) AS last_seen, MAX(url) AS url
            FROM snapshots WHERE batch_ts>=? AND ({cond})
            GROUP BY title ORDER BY n_batches DESC, best_rank ASC LIMIT ?
            """,
            [since_ts, *[f"%{t}%" for t in terms], limit],
        ).fetchall()
    return [dict(r) for r in rows]


def prune(keep_days: int = 30) -> None:
    cutoff = int(time.time()) - keep_days * 86400
    with connect() as conn:
        conn.execute("DELETE FROM snapshots WHERE batch_ts<?", (cutoff,))
        conn.execute("DELETE FROM topics WHERE batch_ts<?", (cutoff,))
        conn.execute("DELETE FROM meme_signals WHERE batch_ts<?", (cutoff,))
        conn.execute("DELETE FROM batches WHERE batch_ts<?", (cutoff,))


# ------------------------------------------------------------------ topics

def save_topics(batch_ts: int, topics: List[Dict[str, Any]]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM topics WHERE batch_ts=?", (batch_ts,))
        conn.executemany(
            "INSERT INTO topics(batch_ts, label, payload) VALUES (?,?,?)",
            [(batch_ts, t["label"], json.dumps(t, ensure_ascii=False)) for t in topics],
        )


def latest_topics(scope: str = "public") -> Dict[str, Any]:
    """最近一个“完整”批次的话题；scope: public（公开热点）| meme（梗/玩法候选）。"""
    with connect() as conn:
        row = conn.execute(
            "SELECT MAX(t.batch_ts) AS ts FROM topics t "
            "LEFT JOIN batches b ON b.batch_ts = t.batch_ts WHERE b.status IS NULL OR b.status='complete'"
        ).fetchone()
        if not row or row["ts"] is None:
            return {"batch_ts": None, "topics": []}
        rows = conn.execute(
            "SELECT id, payload FROM topics WHERE batch_ts=? ORDER BY id", (row["ts"],)
        ).fetchall()
    topics = []
    for r in rows:
        t = json.loads(r["payload"])
        if t.get("scope", "public") != scope:
            continue
        t["id"] = r["id"]
        topics.append(t)
    return {"batch_ts": row["ts"], "topics": topics}


def get_topic(topic_id: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT id, payload FROM topics WHERE id=?", (topic_id,)).fetchone()
    if not row:
        return None
    t = json.loads(row["payload"])
    t["id"] = row["id"]
    return t


def update_topic(topic_id: int, patch: Dict[str, Any]) -> None:
    with connect() as conn:
        row = conn.execute("SELECT payload FROM topics WHERE id=?", (topic_id,)).fetchone()
        if not row:
            return
        t = json.loads(row["payload"])
        t.update(patch)
        conn.execute(
            "UPDATE topics SET payload=? WHERE id=?", (json.dumps(t, ensure_ascii=False), topic_id)
        )


# ---------------------------------------------------------------- analyses

def save_analysis(query: str, workflow_id: str, topology: str, payload: Dict[str, Any],
                  auto_score: Optional[float], status: str = "formal") -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO analyses(ts, query, workflow_id, topology, payload, auto_score, status) "
            "VALUES (?,?,?,?,?,?,?)",
            (int(time.time()), query, workflow_id, topology, json.dumps(payload, ensure_ascii=False),
             auto_score, status),
        )
        return int(cur.lastrowid)


def review_analysis(analysis_id: int, decision: str, reviewer: str, note: str = "") -> Optional[Dict[str, Any]]:
    """教师复核：草稿或 AI 验证稿 → approved（教师已复核，活动方案可执行）/ rejected（归档）。
    草稿复核通过不回补自动奖励（其 auto_score 为空）。"""
    status = {"approve": "approved", "reject": "rejected"}[decision]
    with connect() as conn:
        row = conn.execute("SELECT payload, status FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if not row or row["status"] not in ("draft", "formal"):
            return None
        payload = json.loads(row["payload"])
        payload["status"] = status
        payload["review"] = {"reviewer": reviewer, "note": note[:500], "ts": int(time.time()), "decision": status}
        conn.execute("UPDATE analyses SET status=?, payload=? WHERE id=?",
                     (status, json.dumps(payload, ensure_ascii=False), analysis_id))
    return payload


def get_analysis(analysis_id: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["payload"] = json.loads(out["payload"])
    return out


def recent_analyses(limit: int = 20) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.ts, a.query, a.workflow_id, a.topology, a.auto_score, a.status,
                   (SELECT ROUND(AVG(rating), 1) FROM feedback f WHERE f.analysis_id = a.id) AS avg_rating
            FROM analyses a ORDER BY a.id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_feedback(analysis_id: int, rating: int, comment: Optional[str], username: str = "") -> None:
    """每位老师对每条分析只保留一个评分；再次打分即覆盖。"""
    with connect() as conn:
        conn.execute("DELETE FROM feedback WHERE analysis_id=? AND username=?", (analysis_id, username))
        conn.execute(
            "INSERT INTO feedback(ts, analysis_id, rating, comment, username) VALUES (?,?,?,?,?)",
            (int(time.time()), analysis_id, rating, comment, username),
        )


def feedback_summary(analysis_id: int, username: str = "") -> Dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, AVG(rating) AS avg FROM feedback WHERE analysis_id=?", (analysis_id,)
        ).fetchone()
        mine = conn.execute(
            "SELECT rating FROM feedback WHERE analysis_id=? AND username=? ORDER BY id DESC LIMIT 1",
            (analysis_id, username),
        ).fetchone()
    return {
        "my_rating": mine["rating"] if mine else None,
        "n_ratings": row["n"],
        "avg_rating": round(row["avg"], 1) if row["avg"] is not None else None,
    }


def workflow_rewards() -> List[Dict[str, Any]]:
    """每个工作流变体的自动评分与人工反馈，供工作流选择器使用。"""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT a.workflow_id AS workflow_id,
                   COUNT(a.auto_score) AS n,
                   AVG(a.auto_score) AS auto_mean,
                   AVG(f.rating_mean) AS human_mean,
                   COUNT(f.analysis_id) AS n_human
            FROM analyses a
            LEFT JOIN (
                SELECT analysis_id, AVG(rating) AS rating_mean
                FROM feedback GROUP BY analysis_id
            ) f ON f.analysis_id = a.id
            WHERE a.auto_score IS NOT NULL AND a.status IN ('formal', 'approved')
            GROUP BY a.workflow_id
            """
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------- kv

def kv_get(key: str) -> Optional[bytes]:
    with connect() as conn:
        row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def kv_prefix(prefix: str, limit: int = 200) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT key, value FROM kv WHERE key LIKE ? ORDER BY rowid DESC LIMIT ?", (prefix + "%", limit)
        ).fetchall()
    return [{"key": r["key"][len(prefix):], "value": r["value"]} for r in rows]


def kv_set(key: str, value: bytes) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO kv(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ------------------------------------------------------------------ 匿名投票

def create_poll(token: str, title: str, items: List[Dict[str, Any]], created_by: str, days: int = 14) -> None:
    now = int(time.time())
    with connect() as conn:
        conn.execute("INSERT INTO polls(token, created_ts, closes_ts, created_by, title, items) VALUES (?,?,?,?,?,?)",
                     (token, now, now + days * 86400, created_by, title, json.dumps(items, ensure_ascii=False)))


def get_poll(token: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM polls WHERE token=?", (token,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["items"] = json.loads(d["items"])
    d["open"] = bool(d["active"]) and d["closes_ts"] > time.time()
    return d


def list_polls(limit: int = 20) -> List[Dict[str, Any]]:
    with connect() as conn:
        tokens = [r["token"] for r in conn.execute("SELECT token FROM polls ORDER BY created_ts DESC LIMIT ?",
                                                   (limit,)).fetchall()]
    return [{**get_poll(t), "results": poll_results(t)} for t in tokens]


def close_poll(token: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE polls SET active=0 WHERE token=?", (token,))


def add_vote(token: str, voter: str, answers: Dict[str, Any]) -> bool:
    """同一 voter 每个投票只能提交一次；返回是否为新提交。"""
    with connect() as conn:
        cur = conn.execute("INSERT OR IGNORE INTO poll_votes(token, voter, ts, answers) VALUES (?,?,?,?)",
                           (token, voter, int(time.time()), json.dumps(answers, ensure_ascii=False)))
        return cur.rowcount == 1


def poll_results(token: str) -> Dict[str, Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT answers FROM poll_votes WHERE token=?", (token,)).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        for key, a in json.loads(r["answers"]).items():
            d = out.setdefault(key, {"n": 0, "seen": 0, "used": 0, "follow": 0})
            d["n"] += 1
            d["seen"] += int(a.get("seen", 0) >= 1)
            d["used"] += int(a.get("seen", 0) >= 2)
            d["follow"] += int(bool(a.get("follow")))
    for d in out.values():
        d["seen_pct"] = round(d["seen"] / d["n"], 3) if d["n"] else 0
        d["follow_pct"] = round(d["follow"] / d["n"], 3) if d["n"] else 0
    return out


def poll_stats_by_key(days: int = 30) -> Dict[str, Dict[str, Any]]:
    """所有近期投票按候选 key 汇总（用于校准梗的证据等级）。"""
    since = int(time.time()) - days * 86400
    with connect() as conn:
        tokens = [r["token"] for r in conn.execute("SELECT token FROM polls WHERE created_ts>=?", (since,)).fetchall()]
    agg: Dict[str, Dict[str, Any]] = {}
    for t in tokens:
        for key, d in poll_results(t).items():
            a = agg.setdefault(key, {"n": 0, "seen": 0, "used": 0, "follow": 0})
            for k in ("n", "seen", "used", "follow"):
                a[k] += d[k]
    for a in agg.values():
        a["seen_pct"] = round(a["seen"] / a["n"], 3) if a["n"] else 0
        a["follow_pct"] = round(a["follow"] / a["n"], 3) if a["n"] else 0
    return agg
