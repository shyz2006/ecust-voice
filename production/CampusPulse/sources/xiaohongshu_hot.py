"""Public Rednote hot topics, separate from NewsNow's unsupported source id."""
import hashlib,json,time
from urllib.parse import urlsplit,quote
import requests
from .. import storage
from ..config import settings

CACHE_SECONDS=1800
FAILURE_COOLDOWN=300


def normalize(payload,observed_at):
    if not isinstance(payload,dict) or payload.get('code') not in (0,200) or not isinstance(payload.get('data'),list):
        raise ValueError('小红书热点接口返回格式异常')
    items=[];seen=set()
    for raw in payload['data'][:100]:
        if not isinstance(raw,dict) or not isinstance(raw.get('title'),str):continue
        title=raw['title'].strip()
        if not title or title in seen:continue
        seen.add(title)
        # Hot topics have a platform search entrance, not a specific original post.
        link='https://www.xiaohongshu.com/search_result?keyword='+quote(title,safe='')+'&type=51'
        items.append({'source':'xiaohongshu','rank':len(items)+1,'title':title,'url':link,
            'extra':{'link':link,'link_kind':'platform_search','content_kind':'hotlist_title',
                     'collection_method':'public_hotlist_api','provider':'60s API',
                     'provider_host':urlsplit(settings.xiaohongshu_hot_url).hostname,
                     'provider_observed_at':observed_at,'source_heat':str(raw.get('score') or '')[:40]}})
    if not items:raise ValueError('小红书热点接口暂无有效条目')
    return items


def fetch():
    url=settings.xiaohongshu_hot_url
    key='xiaohongshu-hot:v1:'+hashlib.sha256(url.encode()).hexdigest()[:16]
    now=int(time.time())
    try:
        blob=storage.kv_get(key);cached=json.loads(blob) if blob else None
        if not isinstance(cached,dict):cached=None
        if cached and isinstance(cached.get('ts'),(int,float)):
            items=cached.get('items')
            if now-cached['ts']<CACHE_SECONDS and isinstance(items,list) and items and all(isinstance(x,dict) and x.get('source')=='xiaohongshu' for x in items):
                return 'xiaohongshu',items,''
            if cached.get('error') and now-cached['ts']<FAILURE_COOLDOWN:
                return 'xiaohongshu',[],cached['error']
    except (ValueError,TypeError):cached=None
    for attempt in range(2):
        retryable=False
        try:
            response=requests.get(url,headers={'User-Agent':'ECUST-CampusPulse/1.0','Accept':'application/json'},timeout=20)
            response.raise_for_status()
            items=normalize(response.json(),now)
            storage.kv_set(key,json.dumps({'ts':now,'items':items},ensure_ascii=False).encode())
            return 'xiaohongshu',items,''
        except requests.HTTPError as exc:
            code=getattr(getattr(exc,'response',None),'status_code',None)
            error='小红书热点服务HTTP '+str(code or '错误')
            retryable=code in (500,502,503,504)
        except requests.Timeout:
            error='小红书热点服务请求超时';retryable=True
        except requests.RequestException:error='小红书热点服务连接未完成'
        except (ValueError,TypeError):error='小红书热点响应未通过检查'
        if attempt or not retryable:break
        time.sleep(1)
    storage.kv_set(key,json.dumps({'ts':now,'items':[],'error':error},ensure_ascii=False).encode())
    return 'xiaohongshu',[],error
