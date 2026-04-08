"""
RED: Test error handling in research sources.

Lines 124-125, 146-147, 152-153 are exception handlers for jina_read_url
failure — these are currently untested. If jina_read_url raises, we should
fall back to the description and still return a valid Source.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.research.sources import Source, fetch_academic_sources, fetch_industry_news


@pytest.mark.asyncio
async def test_fetch_academic_sources_falls_back_to_description_on_read_error():
    """
    When jina_read_url raises an exception, fetch_academic_sources should
    fall back to the search result description and still return a valid Source.
    """
    with patch("src.research.sources.jina_parallel_search_web") as mock_search:
        mock_search.return_value = [
            {
                "title": "Attribution Models",
                "url": "https://example.com/attribution",
                "description": "Study on attribution models",
            }
        ]

        with patch("src.research.sources.jina_read_url") as mock_read:
            # jina_read_url fails but description should be used as fallback
            mock_read.side_effect = Exception("connection timeout")

            results = await fetch_academic_sources(["attribution"])

        assert len(results) == 1
        assert isinstance(results[0], Source)
        assert results[0].name == "Attribution Models"
        assert results[0].url == "https://example.com/attribution"
        assert results[0].content == "Study on attribution models"  # description as fallback
        assert results[0].source_type == "academic"


@pytest.mark.asyncio
async def test_fetch_industry_news_falls_back_to_description_on_read_error():
    """
    When jina_read_url raises an exception, fetch_industry_news should
    fall back to the search result description.
    """
    with patch("src.research.sources.jina_parallel_search_web") as mock_search:
        mock_search.return_value = [
            {
                "title": "Google Ads Best Practices",
                "url": "https://example.com/best-practices",
                "description": "Guide to optimization",
            }
        ]

        with patch("src.research.sources.jina_read_url") as mock_read:
            mock_read.side_effect = Exception("read failed")

            results = await fetch_industry_news(["google ads"])

        assert len(results) == 1
        assert results[0].content == "Guide to optimization"
        assert results[0].source_type == "industry_news"


@pytest.mark.asyncio
async def test_fetch_academic_sources_returns_empty_when_queries_empty():
    """
    When queries list is empty, fetch_academic_sources returns [] immediately
    without calling jina_parallel_search_web.
    """
    with patch("src.research.sources.jina_parallel_search_web") as mock_search:
        results = await fetch_academic_sources([])
        assert results == []
        mock_search.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_industry_news_returns_empty_when_queries_empty():
    """
    When queries list is empty, fetch_industry_news returns [] immediately.
    """
    with patch("src.research.sources.jina_parallel_search_web") as mock_search:
        results = await fetch_industry_news([])
        assert results == []
        mock_search.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_academic_sources_truncates_long_content():
    """
    Content from jina_read_url should be truncated to 2000 characters.
    """
    long_content = "A" * 5000

    with patch("src.research.sources.jina_parallel_search_web") as mock_search:
        mock_search.return_value = [
            {
                "title": "Long Article",
                "url": "https://example.com/long",
                "description": "Short desc",
            }
        ]

        with patch("src.research.sources.jina_read_url") as mock_read:
            mock_read.return_value = long_content

            results = await fetch_academic_sources(["test"])

        assert len(results) == 1
        assert len(results[0].content) == 2000
        assert results[0].content == "A" * 2000


@pytest.mark.asyncio
async def test_fetch_academic_sources_handles_missing_title():
    """
    When search result has no title, use empty string as name.
    """
    with patch("src.research.sources.jina_parallel_search_web") as mock_search:
        mock_search.return_value = [
            {
                "url": "https://example.com/no-title",
                "description": "Some description",
            }
        ]

        with patch("src.research.sources.jina_read_url") as mock_read:
            mock_read.return_value = "Content"

            results = await fetch_academic_sources(["test"])

        assert len(results) == 1
        assert results[0].name == ""


@pytest.mark.asyncio
async def test_fetch_academic_sources_handles_missing_url():
    """
    When search result has no url, Source.url should be None.
    """
    with patch("src.research.sources.jina_parallel_search_web") as mock_search:
        mock_search.return_value = [
            {
                "title": "Test Source",
                "description": "Some description",
            }
        ]

        with patch("src.research.sources.jina_read_url") as mock_read:
            mock_read.return_value = "Content"

            results = await fetch_academic_sources(["test"])

        assert len(results) == 1
        assert results[0].url is None
