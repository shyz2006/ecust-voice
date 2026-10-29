"""华理新闻网的公开文字报道；独立于论坛样本、热榜和情绪统计。"""
import json
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .. import storage

SOURCE = 'ecust-news'
BASE = 'https://news.ecust.edu.cn'
LISTS = ((BASE+'/', '校园新闻'), (BASE+'/33/list.htm', '党建'))
CACHE_KEY = 'official-news:ecust:v1'
CACHE_SECONDS = 6*3600
WINDOW_DAYS = 180
MAX_ARTICLES = 24
DAY = 86400
CHINA = timezone(timedelta(hours=8))
TOPICS = {
    '党建思政': ('党建', '思政', '党日', '党课', '党史', '党员教育', '理论学习', '全会精神',
             '马克思主义', '廉政', '廉洁', '八项规定', '党代会', '理想信念', '政绩观'),
    '家国情怀': ('爱国', '报国', '强国', '家国', '红色', '长征', '国家使命', '教育家精神'),
    '志愿公益': ('志愿服务', '志愿者', '支教', '公益', '慈善', '助学', '献血'),
    '社会实践': ('社会实践', '三下乡', '乡村振兴', '实践育人', '研学活动', '文明校园', '劳动教育'),
    '校园育人': ('立德树人', '就业动员', '就业指导', '择业观', '三全育人', '五育并举', '开学第一课'),
}


def article_url(value):
    """Only the supplied school's article routes; no arbitrary redirects or URLs."""
    try:
        p = urlsplit(urljoin(BASE+'/', value or ''))
        if (p.scheme not in ('http', 'https') or p.hostname != 'news.ecust.edu.cn'
                or p.username or p.password or p.port not in (None, 80, 443)
                or not re.fullmatch(r'/20\d{2}/\d{4}/c\d+a\d+/page.htm', p.path)):
            return None
        return BASE+p.path
    except (TypeError, ValueError):
        return None


def categories(title, text, listed_as=''):
    found = []
    for category, terms in TOPICS.items():
        if any(term in title for term in terms) or sum(term in text for term in terms) >= 2:
            found.append(category)
    if listed_as == '党建' and '党建思政' not in found:
        found.insert(0, '党建思政')
    return found


def discover(html, listed_as, now):
    soup = BeautifulSoup(html, 'html.parser')
    found = {}
    for a in soup.select('a[href]'):
        if listed_as == '党建':
            # Sidebar "hot news" is not part of the party-building column.
            container = a.find_parent('div', class_='news_con')
            if not container or not any(x.get_text(strip=True) == '党建' for x in container.select('.news_pre a')):
                continue
        link = article_url(a.get('href'))
        title = a.get('title') or a.get_text(' ', strip=True)
        if not link or not title:
            continue
        # URL dates only limit discovery age. The article's explicit publication
        # date remains mandatory and is the only date stored as "published".
        try:
            path_date = datetime.strptime(urlsplit(link).path[1:10], '%Y/%m%d').replace(tzinfo=CHINA).timestamp()
        except ValueError:
            continue
        if path_date < now-(WINDOW_DAYS+7)*DAY or path_date > now+DAY:
            continue
        found.setdefault(link, {'url': link, 'title': title, 'listed_as': listed_as, 'path_date': path_date})
    return list(found.values())


def parse_article(html, link, listed_as='', now=None):
    now = int(time.time()) if now is None else now
    link = article_url(link)
    if not link:
        return None
    soup = BeautifulSoup(html, 'html.parser')
    heading = soup.select_one('h1.arti_title') or soup.select_one('h1')
    body = soup.select_one('.wp_articlecontent')
    if not heading or not body:
        return None
    title = heading.get_text(' ', strip=True)
    for node in body.select('script, style, iframe, noscript'):
        node.decompose()
    paragraphs = [p.get_text(' ', strip=True).replace('\u200d', '') for p in body.select('p')]
    text = '\n\n'.join(p for p in paragraphs if p) or body.get_text('\n', strip=True)
    stamp = re.search(r'发布时间\s*[：:]\s*(20\d{2}-\d{2}-\d{2})', soup.get_text(' ', strip=True))
    if not title or len(text.strip()) < 40 or not stamp:
        return None
    try:
        published = int(datetime.strptime(stamp[1], '%Y-%m-%d').replace(tzinfo=CHINA).timestamp())
    except ValueError:
        return None
    if not now-WINDOW_DAYS*DAY <= published <= now:
        return None
    topics = categories(title, text, listed_as)
    if not topics:
        return None
    origin = soup.select_one('.arti_publisher')
    origin = re.sub(r'^稿件来源\s*[：:]\s*', '', origin.get_text(' ', strip=True)).strip(' |\xa0') if origin else ''
    return {'source': SOURCE, 'rank': 1, 'title': title, 'url': link,
            'extra': {'link': link, 'content': text[:20000], 'summary': text[:240],
                      'content_kind': 'official_news_text', 'content_truncated': len(text) > 20000,
                      'published': published, 'published_precision': 'date', 'publisher': '华理新闻网',
                      'department': origin, 'categories': topics, 'listed_as': listed_as,
                      'collection_method': 'official_public_html', 'fetched_at': int(now),
                      'exposure': None, 'comments': None, 'likes': None}}


def _fetch_html(session, url, deadline):
    for _ in range(3):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('news collection budget reached')
        with session.get(url, allow_redirects=False, stream=True, timeout=(3, min(8, remaining))) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                target = urljoin(url, response.headers.get('Location', ''))
                p = urlsplit(target)
                if p.scheme != 'https' or p.hostname != 'news.ecust.edu.cn' or p.username or p.password or p.port not in (None, 443):
                    raise ValueError('unexpected news redirect')
                url = target
                continue
            response.raise_for_status()
            if 'text/html' not in response.headers.get('Content-Type', '').lower():
                raise ValueError('expected news HTML')
            data = bytearray()
            for chunk in response.iter_content(16384):
                data.extend(chunk)
                if len(data) > 2_000_000 or time.monotonic() >= deadline:
                    raise ValueError('news response limit reached')
            return bytes(data).decode('utf-8', 'replace')
    raise ValueError('too many news redirects')


def _cached():
    try:
        value = json.loads(storage.kv_get(CACHE_KEY) or b'{}')
        return value if isinstance(value, dict) and isinstance(value.get('items', []), list) else {}
    except (ValueError, TypeError):
        return {}


def collect(now=None):
    now = int(time.time()) if now is None else int(now)
    cached = _cached()
    ttl = 900 if cached.get('error') else CACHE_SECONDS
    if now-cached.get('last_attempt', 0) < ttl:
        return {'items': cached.get('items', []), 'errors': {SOURCE: cached['error']} if cached.get('error') else {}}
    deadline = time.monotonic()+60
    links = {}
    errors = 0
    with requests.Session() as session:
        session.headers['User-Agent'] = 'ECUST-CampusPulse/1.0 (+https://smydashuaige.2026515.xyz/)'
        for url, label in LISTS:
            try:
                for row in discover(_fetch_html(session, url, deadline), label, now):
                    if row['url'] not in links or label == '党建':
                        links[row['url']] = row
            except (requests.RequestException, ValueError, TimeoutError):
                errors += 1
        # Relevant titles first, then recency; every candidate still needs a real
        # article body and explicit publication date before it can be saved.
        candidates = sorted(links.values(), key=lambda r: (bool(categories(r['title'], '', r['listed_as'])), r['path_date']), reverse=True)
        found = {}
        for row in candidates[:MAX_ARTICLES]:
            try:
                item = parse_article(_fetch_html(session, row['url'], deadline), row['url'], row['listed_as'], now)
                if item:
                    found[item['url']] = item
            except (requests.RequestException, ValueError, TimeoutError):
                errors += 1
                if time.monotonic() >= deadline:
                    break
    error = '部分新闻网内容未完成采集，已保留可用报道' if errors else ''
    if not found:
        error = '新闻网暂未取得可核查的育人报道，已保留此前记录' if cached.get('items') else '新闻网暂未取得可核查的育人报道'
    # A partial fetch cannot erase last successful articles. Expire by actual
    # publication date, never recast an old article as a new discussion.
    merged = {item['url']: item for item in cached.get('items', [])
              if now-WINDOW_DAYS*DAY <= (item.get('extra') or {}).get('published', 0) <= now}
    merged.update(found)
    items = sorted(merged.values(), key=lambda x: -x['extra']['published'])[:120]
    for rank, item in enumerate(items, 1):
        item['rank'] = rank
    value = {'last_attempt': now, 'last_success': now if found else cached.get('last_success'),
             'error': error, 'items': items}
    storage.kv_set(CACHE_KEY, json.dumps(value, ensure_ascii=False).encode())
    return {'items': items, 'errors': {SOURCE: error} if error else {}}


def feed(now=None):
    """Read only. Page views never initiate network scraping or model calls."""
    now = int(time.time()) if now is None else int(now)
    rows = storage.recent_items([SOURCE], now-WINDOW_DAYS*DAY)
    seen = {}
    for row in rows:
        ex = row.get('extra') or {}
        link = article_url(ex.get('link') or row.get('url'))
        published = ex.get('published')
        if (not link or not isinstance(published, (int, float))
                or not now-WINDOW_DAYS*DAY <= published <= now or not ex.get('categories')):
            continue
        if link not in seen or row['batch_ts'] > seen[link]['last_observed']:
            seen[link] = {'id': link, 'source': SOURCE, 'title': row['title'], 'link': link,
                          'published': published, 'published_precision': 'date',
                          'summary': ex.get('summary') or ex.get('content', '')[:240],
                          'publisher': '华理新闻网', 'department': ex.get('department', ''),
                          'categories': ex['categories'], 'content_kind': 'official_news_text',
                          'last_observed': row['batch_ts']}
    items = sorted(seen.values(), key=lambda x: (-x['published'], x['link']))
    cache = _cached()
    last_success = cache.get('last_success')
    status = ('partial' if cache.get('error') else 'fresh') if last_success and now-last_success <= 2*CACHE_SECONDS else ('stale' if items else 'error' if cache.get('error') else 'waiting')
    return {'items': items, 'total': len(items), 'window_days': WINDOW_DAYS, 'generated_at': now,
            'last_success_at': last_success, 'status': status, 'message': cache.get('error') or '',
            'source_name': '华理新闻网', 'source_url': BASE+'/',
            'method': '官方报道按原文发布日期展示，按原文链接去重；单独计数，不进入论坛讨论、情绪、词云和热度统计。'}
