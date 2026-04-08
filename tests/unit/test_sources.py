"""
RED: Failing tests for research source fetchers.
RL-003: Research sources fetched from Jina MCP.
Tests that async fetcher functions exist and return Source objects.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.research.sources import Source, ACADEMIC_SEARCH_QUERIES, INDUSTRY_NEWS_QUERIES


def test_source_dataclass():
    """Source should have name, url, content, fetched_at, source_type."""
    s = Source(name="Test", url="https://example.com", content="content", fetched_at="2026-04-07", source_type="academic")
    assert s.name == "Test"
    assert s.url == "https://example.com"
    assert s.content == "content"
    assert s.fetched_at == "2026-04-07"
    assert s.source_type == "academic"


def test_academic_search_queries_defined():
    """ACADEMIC_SEARCH_QUERIES should be a non-empty list."""
    assert isinstance(ACADEMIC_SEARCH_QUERIES, list)
    assert len(ACADEMIC_SEARCH_QUERIES) > 0


def test_industry_news_queries_defined():
    """INDUSTRY_NEWS_QUERIES should be a non-empty list."""
    assert isinstance(INDUSTRY_NEWS_QUERIES, list)
    assert len(INDUSTRY_NEWS_QUERIES) > 0


@pytest.mark.asyncio
async def test_fetch_academic_sources_returns_list():
    """fetch_academic_sources should return a list of Source objects."""
    from src.research.sources import fetch_academic_sources

    with patch("src.research.sources.jina_parallel_search_web") as mock_search:
        mock_search.return_value = [
            {
                "title": "Multi-touch Attribution Models",
                "url": "https://example.com/attribution",
                "description": "Study on attribution models",
            }
        ]

        with patch("src.research.sources.jina_read_url") as mock_read:
            mock_read.return_value = "Full article text about attribution models"
            results = await fetch_academic_sources(ACADEMIC_SEARCH_QUERIES[:1])

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], Source)
        assert results[0].name == "Multi-touch Attribution Models"
        assert results[0].url == "https://example.com/attribution"
        assert results[0].source_type == "academic"


@pytest.mark.asyncio
async def test_fetch_industry_news_returns_list():
    """fetch_industry_news should return a list of Source objects."""
    from src.research.sources import fetch_industry_news

    with patch("src.research.sources.jina_parallel_search_web") as mock_search:
        mock_search.return_value = [
            {
                "title": "Google Ads Best Practices 2026",
                "url": "https://example.com/best-practices",
                "description": "Guide to Google Ads optimization",
            }
        ]

        with patch("src.research.sources.jina_read_url") as mock_read:
            mock_read.return_value = "Full article text about Google Ads optimization"
            results = await fetch_industry_news(INDUSTRY_NEWS_QUERIES[:1])

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], Source)
        assert results[0].name == "Google Ads Best Practices 2026"
        assert results[0].source_type == "industry_news"


@pytest.mark.asyncio
async def test_fetch_academic_sources_empty_on_error():
    """fetch_academic_sources should return empty list when search fails."""
    from src.research.sources import fetch_academic_sources

    with patch("src.research.sources.jina_parallel_search_web", side_effect=Exception("network error")):
        results = await fetch_academic_sources(ACADEMIC_SEARCH_QUERIES[:1])
        assert results == []


@pytest.mark.asyncio
async def test_jina_parallel_search_web_returns_empty_when_no_api_key(monkeypatch):
    """jina_parallel_search_web returns [] immediately when JINA_API_KEY is not set."""
    from src.research.sources import jina_parallel_search_web

    mock_settings = MagicMock()
    mock_settings.JINA_API_KEY = None
    monkeypatch.setattr("src.research.sources.get_settings", lambda: mock_settings)

    results = await jina_parallel_search_web(["test query"])
    assert results == []


@pytest.mark.asyncio
async def test_jina_read_url_returns_empty_when_no_api_key(monkeypatch):
    """jina_read_url returns '' immediately when JINA_API_KEY is not set."""
    from src.research.sources import jina_read_url

    mock_settings = MagicMock()
    mock_settings.JINA_API_KEY = None
    monkeypatch.setattr("src.research.sources.get_settings", lambda: mock_settings)

    result = await jina_read_url("https://example.com/article")
    assert result == ""


@pytest.mark.asyncio
async def test_jina_read_url_returns_empty_on_http_error(monkeypatch):
    """jina_read_url returns '' when httpx request fails (non-200 status)."""
    from src.research.sources import jina_read_url

    mock_settings = MagicMock()
    mock_settings.JINA_API_KEY = "test-key"
    monkeypatch.setattr("src.research.sources.get_settings", lambda: mock_settings)

    mock_response = MagicMock()
    mock_response.status_code = 404

    async def mock_get(*args, **kwargs):
        return mock_response

    mock_client = MagicMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: mock_client)

    result = await jina_read_url("https://example.com/not-found")
    assert result == ""
