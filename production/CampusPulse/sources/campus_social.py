"""公开搜索索引的华理讨论。只保存检索摘要，不宣称完整正文或平台计数。"""
import json
import html
import re
import time
from urllib.parse import urlsplit, urljoin
import requests
from .. import search, storage

PLATFORMS = {'xiaohongshu-school': ('www.xiaohongshu.com', r'^/(?:explore|discovery/item)/[a-zA-Z0-9]+'),
             'douyin-school': ('www.douyin.com', r'^/(?:video|note)/[0-9]+')}
CACHE_SECONDS = 21600
SHORT_HOSTS = {'xhslink.com', 'www.xhslink.com', 'xhslink.cn', 'www.xhslink.cn'}
NOTE_HOSTS = {'xiaohongshu.com', 'www.xiaohongshu.com'}


def school_context(text):
    if not re.search(r'华东理工|华理|ECUST', text, re.I):return False
    return bool(re.search(r'华东理工|ECUST', text, re.I) or not re.search(r'华北理工|东华理工|华南理工|华中科技', text))


def public_share_url(value):
    """Only platform-owned public share hosts; never follow arbitrary search-result URLs."""
    try:
        u=urlsplit(html.unescape(value).rstrip('.,;，。；、）)]}》'))
        if u.scheme not in ('http','https') or u.username or u.password or u.port not in (None,80,443):return ''
        if u.hostname in NOTE_HOSTS and re.fullmatch(PLATFORMS['xiaohongshu-school'][1],u.path.rstrip('/')):
            return u._replace(scheme='https',fragment='').geturl()
        if u.hostname in SHORT_HOSTS and re.fullmatch(r'/(?:[amo]/)?[A-Za-z0-9]+/?',u.path):
            return u._replace(scheme='https',fragment='').geturl()
    except (ValueError,TypeError):pass
    return ''


def resolve_public_share(link, deadline):
    """Follow ordinary public redirects only, with no login credentials or retries."""
    for _ in range(3):
        link=public_share_url(link)
        if not link:return ''
        if urlsplit(link).hostname in NOTE_HOSTS:return link
        remaining=deadline-time.monotonic()
        if remaining<=0:return ''
        try:
            response=requests.get(link,headers={'User-Agent':'ECUST-CampusPulse/1.0'},
                allow_redirects=False,stream=True,timeout=(3,min(5,remaining)))
            try:
                if response.status_code not in (301,302,303,307,308):return ''
                location=response.headers.get('Location')
                if not location:return ''
                link=public_share_url(urljoin(link,location))
            finally:response.close()
        except requests.RequestException:return ''
    return link if link and urlsplit(link).hostname in NOTE_HOSTS else ''


def expand_shared_notes(rows, seen_links, budget):
    found=[]
    for row in rows:
        text=str(row.get('title') or '')+'｜'+str(row.get('snippet') or '')
        if not school_context(text):continue
        links=[str(row.get('url') or ''),*re.findall(r'https?://[^\s<>"\'\u3000]+',html.unescape(text))]
        for value in links:
            link=public_share_url(value)
            if not link:continue
            # Direct notes already pass through parse; here recover links inside shared excerpts.
            if link==row.get('url') and urlsplit(link).hostname in NOTE_HOSTS:continue
            if link in seen_links:continue
            if urlsplit(link).hostname in SHORT_HOSTS:
                if len(seen_links)>=4:continue
                seen_links.add(link)
            if budget[0]<=0:continue
            started=time.monotonic()
            resolved=resolve_public_share(link,started+budget[0])
            budget[0]=max(0,budget[0]-(time.monotonic()-started))
            if not resolved:continue
            note=parse('xiaohongshu-school',[dict(row,url=resolved)])
            for item in note:
                item['extra'].update(discovered_via='public_share_link',supporting_url=row.get('url') or '',share_url=link)
            found.extend(note)
    return found


def parse(source, rows):
    domain, path = PLATFORMS[source]
    output, seen = [], set()
    for row in rows:
        link = str(row.get('url') or '')
        try:
            url = urlsplit(link)
        except ValueError:
            continue
        if url.scheme not in ('https','http') or url.hostname not in (domain, domain.removeprefix('www.')) or not re.fullmatch(path, url.path.rstrip('/')):
            continue
        if url.scheme=='http':link=url._replace(scheme='https').geturl()
        content = str(row.get('title') or '') + '｜' + str(row.get('snippet') or '')
        if not school_context(content):
            continue
        identity = url.path.rstrip('/').rsplit('/',1)[-1] if source=='xiaohongshu-school' else url.hostname.removeprefix('www.') + url.path
        if identity in seen:
            continue
        seen.add(identity)
        output.append({'source':source,'rank':len(output)+1,'title':content[:80], 'url':link,
                       'extra':{'content':content[:20000],'content_kind':'search_summary','link':link,
                                'published':None,'exposure':None,'comments':None,'likes':None,
                                'collection_method':'public_search_index','circle':'华东理工大学公开讨论'}})
    return output


def search_plan(source):
    if source=='xiaohongshu-school':
        return [('"华东理工大学" site:www.xiaohongshu.com/explore','www.xiaohongshu.com',50),
                ('"华理" "奉贤" site:www.xiaohongshu.com','www.xiaohongshu.com',50),
                ('"华理" "徐汇" site:www.xiaohongshu.com','www.xiaohongshu.com',50),
                ('"华理" "小红书" 笔记',None,50)]
    return [('华东理工大学 华理','douyin.com',20),('华东理工大学 华理 抖音',None,20)]


def retrieve(source):
    merged={};failed=False;seen_links=set();share_budget=[25.0]
    for query,include,count in search_plan(source):
        try:
            options={'cache_max_age_seconds':CACHE_SECONDS} if source=='xiaohongshu-school' else {}
            rows=search.web_search(query,count=count,freshness='noLimit',include=include,
                                   plain=source=='xiaohongshu-school',**options)
            found=parse(source,rows)
            if source=='xiaohongshu-school':found+=expand_shared_notes(rows,seen_links,share_budget)
        except search.SearchUnavailable:
            failed=True;break
        except Exception:
            failed=True;continue
        for item in found:
            path=urlsplit(item['url']).path.rstrip('/')
            identity=path.rsplit('/',1)[-1] if source=='xiaohongshu-school' else path
            if identity not in merged:
                item['extra']['search_queries']=[query];merged[identity]=item
            elif query not in merged[identity]['extra']['search_queries']:
                merged[identity]['extra']['search_queries'].append(query)
        # The second Douyin query remains a fallback, not a second scheduled call.
        if source!='xiaohongshu-school' and merged:break
        if len(merged)>=100:break
    found=list(merged.values())[:100]
    for i,item in enumerate(found):item['rank']=i+1
    error=('部分检索未完成，已保留取得的有效结果' if found else '公开检索未完成，请检查搜索配置或调用额度') if failed else ''
    if not found and not error:error='公开搜索索引未返回可核查的华理原帖；不代表平台没有讨论'
    return found,error


def collect():
    items, errors = [], {}
    for source, (domain, _) in PLATFORMS.items():
        key = ('social-search:v3:' if source=='xiaohongshu-school' else 'social-search:v1:')+source
        blob = storage.kv_get(key)
        try:
            cached = json.loads(blob) if blob else None
            if not isinstance(cached,dict) or not isinstance(cached.get('ts'),(int,float)) or not isinstance(cached.get('items'),list):cached=None
        except (ValueError,TypeError):cached=None
        if cached and time.time()-cached['ts'] < CACHE_SECONDS:
            items.extend(cached['items'])
            if cached.get('error'):
                errors[source] = cached['error']
            continue
        try:
            found,error=retrieve(source)
        except search.SearchUnavailable:
            found, error = [], '公开检索不可用，请检查搜索配置或调用额度；未取得平台正文与互动数据'
        except Exception:
            found, error = [], '该平台检索响应未完成，其他来源继续采集'
        items.extend(found)
        if error:
            errors[source] = error
        storage.kv_set(key, json.dumps({'ts':int(time.time()),'items':found,'error':error},ensure_ascii=False).encode())
    from .. import xhs_browser_import
    browser_items = xhs_browser_import.items()
    if browser_items:
        combined = {urlsplit(item['url']).path.rstrip('/').rsplit('/',1)[-1]:item for item in items if item['source']=='xiaohongshu-school'}
        for item in browser_items:
            identity = urlsplit(item['url']).path.rsplit('/',1)[-1]
            previous = combined.get(identity)
            if previous:item['extra']['search_queries']=(previous.get('extra') or {}).get('search_queries',[])
            combined[identity]=item
        items = [item for item in items if item['source']!='xiaohongshu-school']+list(combined.values())
        if errors.get('xiaohongshu-school','').startswith('公开搜索索引未返回可核查'):
            errors.pop('xiaohongshu-school',None)
    return {'items':items,'errors':errors}
