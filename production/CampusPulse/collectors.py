"""
热榜采集器：从 newsnow 聚合接口拉取各平台热榜，形成一个时间批次（batch）。
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

import requests
from loguru import logger

from .config import settings

SOURCE_NAMES = {
    "weibo": "微博热搜",
    "douyin": "抖音热榜",
    "bilibili-hot-search": "B站热搜",
    "zhihu": "知乎热榜",
    "tieba": "百度贴吧",
    "toutiao": "今日头条",
    "baidu": "百度热搜",
    "thepaper": "澎湃新闻",
    "kuaishou": "快手热榜",
    "xiaohongshu": "小红书",
}

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _fetch_source(source: str) -> Tuple[str, List[Dict[str, Any]], str]:
    if source == 'xiaohongshu':
        try:
            from .sources.xiaohongshu_hot import fetch
            return fetch()
        except Exception:return source,[],"小红书热点读取暂未完成"
    url = f"{settings.newsnow_base_url}/api/s?id={source}&latest"
    for attempt in range(2):
        try:
            resp = requests.get(url,headers={**_HEADERS,"Referer":settings.newsnow_base_url},timeout=20)
            resp.raise_for_status()
            data=resp.json()
            if not isinstance(data,dict) or not isinstance(data.get('items'),list):
                return source,[],"上游返回格式异常"
            items=[]
            for idx,raw in enumerate(data['items'],start=1):
                if not isinstance(raw,dict) or not isinstance(raw.get('title'),str):continue
                title=raw['title'].strip()
                if not title:continue
                items.append({'source':source,'rank':idx,'title':title,'url':raw.get('url') or raw.get('mobileUrl'),
                              'extra':raw.get('extra') if isinstance(raw.get('extra'),dict) else {}})
            return source,items,"" if items else "来源暂无有效条目"
        except requests.HTTPError as exc:
            code=getattr(getattr(exc,'response',None),'status_code',None)
            if attempt==0 and code in (500,502,503,504):
                time.sleep(1);continue
            return source,[],"上游接口HTTP "+str(code or '错误')
        except requests.Timeout:
            if attempt==0:time.sleep(1);continue
            return source,[],"来源请求超时"
        except requests.ConnectionError:
            if attempt==0:time.sleep(1);continue
            return source,[],"来源网络连接失败"
        except (ValueError,TypeError,AttributeError):return source,[],"上游返回格式异常"
        except Exception:return source,[],"来源请求暂未完成"


def collect_hotlists(sources: List[str] = None) -> Dict[str, Any]:
    """并发拉取所有热榜源，返回 {batch_ts, items, errors}。"""
    sources = list(dict.fromkeys([*(sources if sources is not None else settings.sources), "xiaohongshu"]))
    batch_ts = int(time.time())
    all_items: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(3, len(sources) or 1)) as pool:
        for source, items, err in pool.map(_fetch_source, sources):
            if err:
                errors[source] = err
                logger.warning(f"[CampusPulse] 热榜 {source} 获取失败: {err}")
            all_items.extend(items)
    logger.info(
        f"[CampusPulse] 采集批次 {batch_ts}: {len(all_items)} 条, "
        f"{len(sources) - len(errors)}/{len(sources)} 个源成功"
    )
    return {"batch_ts": batch_ts, "items": all_items, "errors": errors}
