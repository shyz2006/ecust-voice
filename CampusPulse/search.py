"""
博查（Bocha）搜索客户端。

与 BettaFish Query/Media Agent 保持一致：SEARCH_TOOL_TYPE=BochaAPI 时使用
BOCHA_WEB_SEARCH_API_KEY + BOCHA_BASE_URL。兼容两种接口返回格式：
- /v1/ai-search：messages 列表，source/webpage 消息里是网页结果；
- /v1/web-search：data.webPages.value。
"""

import json
from typing import Dict, List

import requests
from loguru import logger

from .config import settings


class SearchUnavailable(RuntimeError):
    pass


def _parse_ai_search(payload: Dict) -> List[Dict]:
    pages = []
    for msg in payload.get("messages") or []:
        if msg.get("role") != "assistant" or msg.get("type") != "source":
            continue
        if msg.get("content_type") != "webpage":
            continue
        try:
            content = json.loads(msg.get("content") or "{}")
        except json.JSONDecodeError:
            continue
        pages.extend(content.get("value") or [])
    return pages


def _parse_web_search(payload: Dict) -> List[Dict]:
    data = payload.get("data") or {}
    return ((data.get("webPages") or {}).get("value")) or []


def web_search(query: str, count: int = 8, freshness: str = "oneMonth") -> List[Dict]:
    if not settings.search_ready:
        raise SearchUnavailable("未配置 BOCHA_WEB_SEARCH_API_KEY")
    url = settings.bocha_base_url
    body = {"query": query, "freshness": freshness, "count": count, "answer": False, "stream": False}
    if "web-search" in url:
        body = {"query": query, "freshness": freshness, "count": count, "summary": True}
    try:  # 检索网关：结果缓存 + 每日调用上限（校园脉搏不属于研究任务）
        from utils import search_gateway as gateway
    except Exception:  # pragma: no cover - 独立运行 / 测试环境
        gateway = None
    payload = gateway.cache_get(url, query, freshness, count, False) if gateway else None
    if payload is None:
        scope = gateway.current_scope() if gateway else ""
        if gateway and not gateway.try_consume(scope):
            raise SearchUnavailable("今日博查调用额度已用完（BOCHA_MAX_CALLS_PER_DAY_OTHER）")
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {settings.bocha_api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=40,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            if gateway:
                gateway.refund(scope)
            raise SearchUnavailable(f"博查搜索失败: {exc}") from exc
        if payload.get("code") not in (None, 200):
            if gateway:
                gateway.refund(scope)
            raise SearchUnavailable(f"博查返回错误: {payload.get('msg')}")
        if gateway:
            gateway.cache_put(url, query, freshness, count, False, payload)

    raw = _parse_ai_search(payload) or _parse_web_search(payload)
    results = []
    for page in raw[:count]:
        snippet = page.get("summary") or page.get("snippet") or ""
        results.append(
            {
                "title": page.get("name") or "",
                "url": page.get("url") or "",
                "site": page.get("siteName") or page.get("displayUrl") or "",
                "date": page.get("datePublished") or page.get("dateLastCrawled") or "",
                "snippet": snippet[:600],
            }
        )
    logger.info(f"[CampusPulse] 博查搜索 “{query}” 返回 {len(results)} 条")
    return results
