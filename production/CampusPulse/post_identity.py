"""Forum post identity, independent of display text and tracking parameters."""
import re
from urllib.parse import parse_qs,urlsplit


def identifier(row):
    ex=row.get('extra') or {}
    source=row.get('source')
    link=ex.get('link') or row.get('url') or ''
    if source=='huyou-school' or source=='huyou-national':
        feed=str(ex.get('feed_id') or '')
        if feed.isdigit():
            return feed
        try:
            parsed=urlsplit(link)
            feed=(parse_qs(parsed.query).get('feedDetail') or [''])[0]
            if parsed.hostname=='hy.sns.sohu.com' and feed.isdigit():
                return feed
        except ValueError:
            pass
    if source in ('xiaohongshu-school','douyin-school'):
        try:
            parsed=urlsplit(link)
            host=(parsed.hostname or '').removeprefix('www.')
            pattern = r'^/(?:explore|discovery/item)/([a-zA-Z0-9]+)' if source=='xiaohongshu-school' else r'^/(?:video|note)/(\d+)'
            expected = 'xiaohongshu.com' if source=='xiaohongshu-school' else 'douyin.com'
            match=re.match(pattern,parsed.path)
            if parsed.scheme=='https' and host==expected and match:
                return expected+':'+match[1]
        except ValueError:
            pass
    if source=='tieba-school':
        try:
            parsed=urlsplit(link)
            match=re.match(r'^/p/(\d+)(?:/|$)',parsed.path)
            if parsed.hostname=='tieba.baidu.com' and match:
                return 'https://tieba.baidu.com/p/'+match[1]
        except ValueError:
            pass
    return None


def stable_value(row):
    ex=row.get('extra') or {}
    return identifier(row) or str(ex.get('link') or ex.get('feed_id') or ex.get('content') or row.get('title') or '')


def resolved_values(rows):
    """Recover a legacy missing URL only with exact text + published time + one ID.

    Two genuine IDs with the same text stay distinct. Missing publication times,
    similar text, or ambiguous matches never merge. Input observations stay intact.
    """
    from collections import defaultdict
    identities=defaultdict(set)
    def signature(row):
        ex=row.get('extra') or {}
        try:published=int(ex.get('published') or 0)
        except (TypeError,ValueError):return None
        text=ex.get('content') or row.get('title') or ''
        return (row['source'],published,text) if published>=946684800 and text else None
    for row in rows:
        key=signature(row);value=identifier(row)
        if key and value:identities[key].add(value)
    values=[]
    for row in rows:
        known=identifier(row);candidates=identities.get(signature(row),set())
        values.append(known or (next(iter(candidates)) if len(candidates)==1 else stable_value(row)))
    return values
