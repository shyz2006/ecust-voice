"""Compatibility adapter that lets QueryEngine use Bocha search.

QueryEngine historically expects the TavilyNewsAgency method names and response
shape.  This adapter preserves that interface so the rest of the research
pipeline can use Bocha when no Tavily key is available.
"""

from typing import Optional

from MediaEngine.tools.search import BochaMultimodalSearch, BochaResponse

from .search import ImageResult, SearchResult, TavilyResponse


class BochaNewsAgency:
    """Expose Bocha through QueryEngine's existing news-search interface."""

    def __init__(self, api_key: str):
        self._client = BochaMultimodalSearch(api_key=api_key)

    @staticmethod
    def _convert(response: BochaResponse) -> TavilyResponse:
        results = [
            SearchResult(
                title=item.name or "",
                url=item.url or "",
                content=item.snippet or "",
                # Bocha returns crawl time, not a reliable publication date.
                published_date=None,
            )
            for item in response.webpages
        ]
        images = [
            ImageResult(
                url=item.content_url or item.thumbnail_url or "",
                description=item.name,
            )
            for item in response.images
            if item.content_url or item.thumbnail_url
        ]
        return TavilyResponse(
            query=response.query,
            answer=response.answer,
            results=results,
            images=images,
        )

    def basic_search_news(self, query: str, max_results: int = 7) -> TavilyResponse:
        return self._convert(self._client.web_search_only(query, max_results))

    def deep_search_news(self, query: str) -> TavilyResponse:
        return self._convert(self._client.comprehensive_search(query, 20))

    def search_news_last_24_hours(self, query: str) -> TavilyResponse:
        return self._convert(self._client.search_last_24_hours(query))

    def search_news_last_week(self, query: str) -> TavilyResponse:
        return self._convert(self._client.search_last_week(query))

    def search_images_for_news(self, query: str) -> TavilyResponse:
        return self._convert(self._client.comprehensive_search(query, 5))

    def search_news_by_date(
        self, query: str, start_date: str, end_date: str
    ) -> TavilyResponse:
        # Bocha AI Search has no exact start/end pair in this project's client.
        # Include the range in the query, then let the research prompt validate
        # publication dates from the returned sources.
        dated_query = (
            f"{query}，发布时间限定在 {start_date} 至 {end_date}，"
            "优先返回带明确发布日期的来源"
        )
        return self._convert(self._client.comprehensive_search(dated_query, 15))
