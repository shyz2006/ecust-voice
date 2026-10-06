"""
学校官网本地索引：爬取华东理工大学公开网站（默认学校主页与新闻网），存入本地 SQLite，供研究检索免费使用。

- 只抓公开页面、只在配置的站点内爬取、每次请求间隔 CAMPUS_INDEX_DELAY 秒；遇到 403/429 暂停本轮，不做任何绕过。
- 站点为 WebPlus 系统：栏目列表 /<栏目>/list{n}.htm，文章 /YYYY/MMDD/c<栏目>a<编号>/page.htm（网址自带发布日期）。
- 首次运行回填 CAMPUS_INDEX_SINCE 之后的文章；之后每 CAMPUS_INDEX_INTERVAL_HOURS 小时增量更新（遇到已收录的文章即停止翻页）。
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("CAMPUS_INDEX_DB", str(PROJECT_ROOT / "data" / "campus_index.sqlite3")))
SITES = [s.strip() for s in os.getenv(
    "CAMPUS_INDEX_SITES", "https://www.ecust.edu.cn/,https://news.ecust.edu.cn/").split(",") if s.strip()]
SINCE = os.getenv("CAMPUS_INDEX_SINCE", "2021-01-01")
DELAY = float(os.getenv("CAMPUS_INDEX_DELAY", "1.0"))
INTERVAL_HOURS = float(os.getenv("CAMPUS_INDEX_INTERVAL_HOURS", "12"))
USER_AGENT = "Mozilla/5.0 (compatible; ECUSTCampusIndex/1.0; campus psychological center research)"

ARTICLE_RE = re.compile(r"/(\d{4})/(\d{2})(\d{2})/c\d+a\d+/page\.htm$")
LIST_RE = re.compile(r"/[A-Za-z0-9_]+/list(\d*)\.htm$")
SCHOOL_WORDS = {"华理", "华东理工", "华东理工大学", "ecust", "学校", "我校", "本校", "高校", "大学"}
STOP_WORDS = {"的", "了", "和", "与", "及", "是", "在", "为", "有", "吗", "呢", "什么", "如何", "怎么",
              "官方", "通知", "新闻", "最新", "情况", "相关", "信息", "发布", "时间", "原因", "影响"}

# 校园语境下几乎处处出现的泛词：检索时排在具体关键词之后，打分只算半分
GENERIC_TERMS = {"校区", "食堂", "学生", "同学", "老师", "宿舍", "学院", "教室", "上课", "考试", "图书馆",
                 "徐汇", "奉贤", "金山", "一楼", "二楼", "三楼", "今天", "现在", "大家"}

_lock = threading.Lock()
_started = False


# ---------------------------------------------------------------- 存储
def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS pages (
        url TEXT PRIMARY KEY, site TEXT, title TEXT, published TEXT, source TEXT,
        text TEXT, fetched_at REAL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pages_published ON pages(published)")
    conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
    return conn


def _kv_get(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
    return row[0] if row else default


def _kv_set(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO kv(k, v) VALUES(?, ?)", (key, value))
    conn.commit()


# ---------------------------------------------------------------- 抓取
class _Blocked(RuntimeError):
    pass


class _Fetcher:
    def __init__(self):
        import requests

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last = 0.0
        self.requests = 0

    def get(self, url: str) -> Optional[str]:
        wait = DELAY - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        self.requests += 1
        try:
            resp = self.session.get(url, timeout=20)
        except Exception as exc:
            logger.debug(f"[校园索引] 请求失败 {url}: {exc}")
            return None
        if resp.status_code in (403, 429):
            raise _Blocked(f"{resp.status_code} {url}")
        if resp.status_code != 200 or "html" not in resp.headers.get("Content-Type", "html"):
            return None
        resp.encoding = resp.apparent_encoding if resp.encoding in (None, "ISO-8859-1") else resp.encoding
        return resp.text


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def _links(html: str, base: str) -> List[str]:
    out = []
    for href in re.findall(r"href=[\"']([^\"'#]+)[\"']", html):
        if href.startswith(("javascript:", "mailto:")) or "_redirect" in href:
            continue
        out.append(urljoin(base, href.strip()).replace("http://", "https://", 1))
    return out


def _article_date(url: str) -> str:
    m = ARTICLE_RE.search(urlparse(url).path)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_article(html: str, url: str) -> Dict[str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title_el = soup.select_one(".arti_title, .Article_Title, h1")
    title = _clean(title_el.get_text(" ")) if title_el else _clean(soup.title.get_text() if soup.title else "")
    body_el = soup.select_one(".wp_articlecontent, .entry, .article, .Article_Content, #vsb_content")
    text = _clean(body_el.get_text(" ")) if body_el else ""
    meta_el = soup.select_one(".arti_metas, .arti_update")
    meta = _clean(meta_el.get_text(" ")) if meta_el else ""
    source = ""
    m = re.search(r"稿件来源[:：]\s*([^|｜]+)", meta)
    if m:
        source = m.group(1).strip()
    published = _article_date(url)
    if not published:
        m = re.search(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})", meta)
        if m:
            published = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return {"title": title, "text": text, "source": source, "published": published}


def _discover_columns(fetcher: _Fetcher, site: str, allowed: Set[str]) -> List[str]:
    html = fetcher.get(site)
    if not html:
        return []
    columns = []
    for link in _links(html, site):
        if _host(link) in allowed and LIST_RE.search(urlparse(link).path):
            base = re.sub(r"list\d*\.htm$", "list.htm", link)
            if base not in columns:
                columns.append(base)
    return columns


def _list_page_url(column: str, page: int) -> str:
    return column if page == 1 else column.replace("list.htm", f"list{page}.htm")


def _crawl_column(conn, fetcher: _Fetcher, column: str, allowed: Set[str], since: str,
                  incremental: bool, max_pages: int) -> int:
    added = 0
    total_pages = None
    page = 1
    while page <= (total_pages or max_pages):
        html = fetcher.get(_list_page_url(column, page))
        if not html:
            break
        if total_pages is None:
            m = re.search(r"all_pages[^0-9]{0,20}(\d+)", html)
            total_pages = min(int(m.group(1)), max_pages) if m else 1
        articles = []
        for link in _links(html, column):
            if _host(link) in allowed and ARTICLE_RE.search(urlparse(link).path) and link not in articles:
                articles.append(link)
        if not articles:
            break
        known = {row[0] for row in conn.execute(
            f"SELECT url FROM pages WHERE url IN ({','.join('?' * len(articles))})", articles)}
        fresh = [a for a in articles if a not in known and _article_date(a) >= since]
        for url in fresh:
            html_a = fetcher.get(url)
            if not html_a:
                continue
            doc = parse_article(html_a, url)
            if not doc["text"] and not doc["title"]:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO pages(url, site, title, published, source, text, fetched_at) VALUES(?,?,?,?,?,?,?)",
                (url, _host(url), doc["title"], doc["published"], doc["source"], doc["text"][:20000], time.time()))
            conn.commit()
            added += 1
        dates = [_article_date(a) for a in articles if _article_date(a)]
        if dates and max(dates) < since:
            break  # 整页都早于回填起点
        if incremental and len(fresh) < len(articles):
            break  # 增量模式：已遇到收录过的文章
        page += 1
    return added


def crawl(incremental: Optional[bool] = None, max_pages: int = 1000) -> Dict[str, int]:
    """抓取一轮。incremental=None 时：已完成过回填则增量，否则回填。"""
    if not _lock.acquire(blocking=False):
        return {"skipped": 1}
    try:
        conn = _connect()
        if incremental is None:
            incremental = _kv_get(conn, "backfill_done") == "1"
        allowed = {_host(s) for s in SITES}
        fetcher = _Fetcher()
        stats = {"added": 0, "columns": 0}
        mode = "增量" if incremental else f"回填（{SINCE} 起）"
        logger.info(f"[校园索引] 开始{mode}抓取：{', '.join(SITES)}")
        try:
            for site in SITES:
                for column in _discover_columns(fetcher, site, allowed):
                    stats["columns"] += 1
                    stats["added"] += _crawl_column(conn, fetcher, column, allowed, SINCE, incremental,
                                                    3 if incremental else max_pages)
        except _Blocked as exc:
            logger.warning(f"[校园索引] 站点返回 {exc}，本轮暂停，下次再试")
            stats["blocked"] = 1
        else:
            if not incremental:
                _kv_set(conn, "backfill_done", "1")
        stats["requests"] = fetcher.requests
        _kv_set(conn, "last_crawl", datetime.now().isoformat(timespec="seconds"))
        _kv_set(conn, "last_stats", str(stats))
        logger.info(f"[校园索引] {mode}完成：{stats}")
        conn.close()
        return stats
    finally:
        _lock.release()


def start_scheduler() -> None:
    """后台线程：启动后稍候开始抓取，之后按间隔增量更新。CAMPUS_INDEX=0 可关闭。"""
    global _started
    if _started or os.getenv("CAMPUS_INDEX", "1") == "0":
        return
    _started = True

    def loop():
        time.sleep(60)
        while True:
            try:
                crawl()
            except Exception as exc:
                logger.warning(f"[校园索引] 抓取异常：{exc}")
            time.sleep(INTERVAL_HOURS * 3600)

    threading.Thread(target=loop, name="campus-index", daemon=True).start()


# ---------------------------------------------------------------- 检索
def keywords(query: str, limit: int = 6) -> List[str]:
    try:
        import jieba

        tokens = jieba.lcut(query)
    except Exception:
        tokens = re.findall(r"[一-鿿]{2,}|[A-Za-z0-9]{2,}", query)
    out: List[str] = []
    for tok in tokens:
        tok = tok.strip().lower()
        if len(tok) < 2 or tok in STOP_WORDS or tok in SCHOOL_WORDS or re.fullmatch(r"\d{1,3}", tok):
            continue
        if tok not in out:
            out.append(tok)
    # 具体关键词（如“清真”“改名”）优先，泛词（“校区”“食堂”）排后，避免被截断丢掉关键信息
    out.sort(key=lambda t: t in GENERIC_TERMS)
    return out[:limit]


def search(query: str, limit: int = 8) -> List[Dict[str, object]]:
    """按关键词覆盖率 + 标题命中打分；只返回覆盖多数关键词的文章。"""
    if not DB_PATH.exists():
        return []
    terms = keywords(query)
    if not terms:
        return []
    need = max(1, -(-len(terms) * 6 // 10)) if len(terms) > 1 else 1
    hit_exprs = [f"((title LIKE ?) OR (text LIKE ?))" for _ in terms]
    score_exprs = [f"(title LIKE ?)*3 + (text LIKE ?)" for _ in terms]
    params: List[str] = []
    for t in terms:
        params += [f"%{t}%", f"%{t}%"]
    sql = (f"SELECT url, site, title, published, source, text, ({' + '.join(hit_exprs)}) AS cover, "
           f"({' + '.join(score_exprs)}) AS score FROM pages "
           f"WHERE ({' OR '.join(hit_exprs)}) ORDER BY cover DESC, score DESC, published DESC LIMIT ?")
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
        rows = conn.execute(sql, params + params + params + [limit * 3]).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        logger.warning(f"[校园索引] 检索失败：{exc}")
        return []
    results = []
    for url, site, title, published, source, text, cover, score in rows:
        if cover < need:
            continue
        results.append({
            "url": url, "site": site, "title": title, "published": published, "source": source,
            "snippet": _snippet(text, terms), "coverage": cover / len(terms), "score": score,
        })
        if len(results) >= limit:
            break
    return results


def _snippet(text: str, terms: Iterable[str], width: int = 260) -> str:
    text = text or ""
    pos = min([p for p in (text.find(t) for t in terms) if p >= 0] or [0])
    start = max(0, pos - 60)
    return text[start:start + width]


def stats() -> Dict[str, object]:
    if not DB_PATH.exists():
        return {"pages": 0}
    conn = _connect()
    try:
        pages = conn.execute("SELECT COUNT(*), MIN(published), MAX(published) FROM pages").fetchone()
        by_site = dict(conn.execute("SELECT site, COUNT(*) FROM pages GROUP BY site").fetchall())
        return {"pages": pages[0], "earliest": pages[1], "latest": pages[2], "by_site": by_site,
                "backfill_done": _kv_get(conn, "backfill_done") == "1",
                "last_crawl": _kv_get(conn, "last_crawl"), "last_stats": _kv_get(conn, "last_stats")}
    finally:
        conn.close()
