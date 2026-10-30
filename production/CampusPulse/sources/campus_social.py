"""公开搜索索引的华理讨论。只保存检索摘要，不宣称完整正文或平台计数。"""
import json
import re
import time
from urllib.parse import urlsplit
from .. import search, storage

PLATFORMS = {'douyin-school': ('www.douyin.com', r'^/(?:video|note)/[0-9]+')}
CACHE_SECONDS = 21600

def school_context(text):
    if not re.search(r'华东理工|华理|ECUST', text, re.I):return False
    return bool(re.search(r'华东理工|ECUST', text, re.I) or not re.search(r'华北理工|东华理工|华南理工|华中科技', text))


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
        identity = url.hostname.removeprefix('www.') + url.path
        if identity in seen:
            continue
        seen.add(identity)
        output.append({'source':source,'rank':len(output)+1,'title':content[:80], 'url':link,
                       'extra':{'content':content[:20000],'content_kind':'search_summary','link':link,
                                'published':None,'exposure':None,'comments':None,'likes':None,
                                'collection_method':'public_search_index','circle':'华东理工大学公开讨论'}})
    return output


def search_plan(source):
    return [('华东理工大学 华理','douyin.com',20),('华东理工大学 华理 抖音',None,20)]


def retrieve(source):
    merged={};failed=False
    for query,include,count in search_plan(source):
        try:
            rows=search.web_search(query,count=count,freshness='noLimit',include=include,
                                   plain=False)
            found=parse(source,rows)
        except search.SearchUnavailable:
            failed=True;break
        except Exception:
            failed=True;continue
        for item in found:
            path=urlsplit(item['url']).path.rstrip('/')
            identity=path
            if identity not in merged:
                item['extra']['search_queries']=[query];merged[identity]=item
            elif query not in merged[identity]['extra']['search_queries']:
                merged[identity]['extra']['search_queries'].append(query)
        # The second Douyin query remains a fallback, not a second scheduled call.
        if merged:break
        if len(merged)>=100:break
    found=list(merged.values())[:100]
    for i,item in enumerate(found):item['rank']=i+1
    error=('部分检索未完成，已保留取得的有效结果' if found else '公开检索未完成，请检查搜索配置或调用额度') if failed else ''
    if not found and not error:error='公开搜索索引未返回可核查的华理原帖；不代表平台没有讨论'
    return found,error


def collect():
    items, errors = [], {}
    for source, (domain, _) in PLATFORMS.items():
        key = 'social-search:v1:'+source
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
    return {'items':items,'errors':errors}
