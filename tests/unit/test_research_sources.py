"""
RED: Failing tests for research/sources.py — source definitions and dataclasses.
Tests Source dataclass, ACADEMIC_SEARCH_QUERIES, and fetch functions.
"""
import pytest
from datetime import datetime, timezone

from src.research.sources import Source, ACADEMIC_SEARCH_QUERIES, INDUSTRY_NEWS_QUERIES


class TestSourceDataclass:
    """Test Source dataclass creation and field access."""

    def test_source_creation(self):
        """Source stores all fields correctly."""
        now = datetime.now(timezone.utc).isoformat()
        source = Source(
            name="Keyword Research Best Practices",
            url="https://example.com/keyword-research",
            content="Broad match captures... exact match has highest CTR...",
            fetched_at=now,
            source_type="academic",
        )
        assert source.name == "Keyword Research Best Practices"
        assert source.url == "https://example.com/keyword-research"
        assert "Broad match" in source.content
        assert source.source_type == "academic"
        assert source.fetched_at == now

    def test_source_url_optional(self):
        """Source can be created without a URL."""
        source = Source(
            name="Internal Memo",
            url=None,
            content="Internal analysis...",
            fetched_at=datetime.now(timezone.utc).isoformat(),
            source_type="campaign_data",
        )
        assert source.url is None
        assert source.source_type == "campaign_data"


class TestSourceQueries:
    """Test that source query lists are non-empty and contain strings."""

    def test_academic_queries_non_empty(self):
        """ACADEMIC_SEARCH_QUERIES contains at least one query."""
        assert len(ACADEMIC_SEARCH_QUERIES) > 0

    def test_academic_queries_are_strings(self):
        """All ACADEMIC_SEARCH_QUERIES entries are non-empty strings."""
        for query in ACADEMIC_SEARCH_QUERIES:
            assert isinstance(query, str)
            assert len(query) > 0

    def test_industry_news_queries_non_empty(self):
        """INDUSTRY_NEWS_QUERIES contains at least one query."""
        assert len(INDUSTRY_NEWS_QUERIES) > 0

    def test_industry_news_queries_are_strings(self):
        """All INDUSTRY_NEWS_QUERIES entries are non-empty strings."""
        for query in INDUSTRY_NEWS_QUERIES:
            assert isinstance(query, str)
            assert len(query) > 0

    def test_academic_queries_relevant_to_advertising(self):
        """Academic queries cover advertising-relevant topics."""
        all_queries = " ".join(ACADEMIC_SEARCH_QUERIES).lower()
        assert any(term in all_queries for term in ["keyword", "search", "advertising", "bid", "attribution"])
