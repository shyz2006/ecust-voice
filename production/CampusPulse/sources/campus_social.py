"""公开搜索索引的华理讨论。只保存检索摘要，不宣称完整正文或平台计数。"""
import json
import re
import time
from urllib.parse import urlsplit
from .. import search, storage

PLATFORMS = {'xiaohongshu-school': ('www.xiaohongshu.com', r'^/(?:explore|discovery/item)/[a-zA-Z0-9]+'),
             'douyin-school': ('www.douyin.com', r'^/(?:video|note)/[0-9]+')}


def parse(source, rows):
    domain, path = PLATFORMS[source]
    output, seen = [], set()
    for row in rows:
        link = str(row.get('url') or '')
        try:
            url = urlsplit(link)
        except ValueError:
            continue
        if url.scheme != 'https' or url.hostname not in (domain, domain.removeprefix('www.')) or not re.match(path, url.path):
            continue
        content = str(row.get('title') or '') + '｜' + str(row.get('snippet') or '')
        if not re.search(r'华东理工|华理|ECUST', content, re.I):
            continue
        if not re.search(r'华东理工|ECUST', content, re.I) and re.search(r'华北理工|东华理工|华南理工|华中科技',content):
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


def collect():
    items, errors = [], {}
    for source, (domain, _) in PLATFORMS.items():
        key = 'social-search:v1:'+source
        blob = storage.kv_get(key)
        try:
            cached = json.loads(blob) if blob else None
            if not isinstance(cached,dict) or not isinstance(cached.get('ts'),(int,float)) or not isinstance(cached.get('items'),list):cached=None
        except (ValueError,TypeError):cached=None
        if cached and time.time()-cached['ts'] < 21600:
            items.extend(cached['items'])
            if cached.get('error'):
                errors[source] = cached['error']
            continue
        try:
            found = parse(source, search.web_search('华东理工大学 华理', count=20, freshness='noLimit', include=domain.removeprefix('www.')))
            if not found:
                platform = '小红书' if source=='xiaohongshu-school' else '抖音'
                found = parse(source, search.web_search('华东理工大学 华理 '+platform, count=20, freshness='noLimit'))
            error = '' if found else '公开搜索索引未返回可核查的华理原帖；不代表平台没有讨论'
        except search.SearchUnavailable:
            found, error = [], '公开检索不可用，请检查搜索配置或调用额度；未取得平台正文与互动数据'
        except Exception:
            found, error = [], '该平台检索响应未完成，其他来源继续采集'
        items.extend(found)
        if error:
            errors[source] = error
        storage.kv_set(key, json.dumps({'ts':int(time.time()),'items':found,'error':error},ensure_ascii=False).encode())
    return {'items':items,'errors':errors}
