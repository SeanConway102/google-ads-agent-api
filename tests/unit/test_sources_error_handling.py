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


@pytest.mark.asyncio
async def test_jina_parallel_search_web_returns_empty_on_httpx_gather_exception(monkeypatch):
    """
    When asyncio.gather itself raises (not a returned exception object),
    jina_parallel_search_web catches it via the outer except Exception
    and returns [].
    """
    from src.research.sources import jina_parallel_search_web

    mock_settings = MagicMock()
    mock_settings.JINA_API_KEY = "test-key"
    monkeypatch.setattr("src.research.sources.get_settings", lambda: mock_settings)

    # Make asyncio.gather itself raise
    monkeypatch.setattr("asyncio.gather", AsyncMock(side_effect=Exception("gather failed")))

    results = await jina_parallel_search_web(["test query"])
    assert results == []


@pytest.mark.asyncio
async def test_jina_read_url_returns_empty_on_httpx_client_exception(monkeypatch):
    """
    When httpx client.get raises an exception (not just non-200 status),
    jina_read_url catches it via the outer except Exception and returns ''.
    """
    from src.research.sources import jina_read_url

    mock_settings = MagicMock()
    mock_settings.JINA_API_KEY = "test-key"
    monkeypatch.setattr("src.research.sources.get_settings", lambda: mock_settings)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=Exception("connection reset"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: mock_client)

    result = await jina_read_url("https://example.com/article")
    assert result == ""


@pytest.mark.asyncio
async def test_fetch_academic_sources_returns_empty_when_search_raises(monkeypatch):
    """
    When jina_parallel_search_web raises an exception (not returns []),
    fetch_academic_sources catches it via the outer try/except and returns [].
    """
    from src.research.sources import fetch_academic_sources

    monkeypatch.setattr(
        "src.research.sources.jina_parallel_search_web",
        AsyncMock(side_effect=Exception("search API down"))
    )

    results = await fetch_academic_sources(["test"])
    assert results == []


@pytest.mark.asyncio
async def test_fetch_industry_news_returns_empty_when_search_raises(monkeypatch):
    """
    When jina_parallel_search_web raises an exception, fetch_industry_news
    catches it via the outer try/except and returns [].
    """
    from src.research.sources import fetch_industry_news

    monkeypatch.setattr(
        "src.research.sources.jina_parallel_search_web",
        AsyncMock(side_effect=Exception("search API down"))
    )

    results = await fetch_industry_news(["test"])
    assert results == []
