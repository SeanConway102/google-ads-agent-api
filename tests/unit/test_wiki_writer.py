"""
RED: Failing tests for WikiWriter.
Tests consensus entry creation, slug generation, and entry invalidation.
"""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from src.research.wiki_writer import WikiWriter


class TestWikiWriterGenerateSlug:
    """Test slug generation for wiki entry titles."""

    def test_generate_slug_lowercases(self):
        """Slug converts title to lowercase."""
        writer = WikiWriter(db=MagicMock())
        slug = writer._generate_slug("Keyword Optimization Strategies")
        assert slug == slug.lower()

    def test_generate_slug_replaces_spaces_with_hyphens(self):
        """Spaces in title become hyphens in slug."""
        writer = WikiWriter(db=MagicMock())
        slug = writer._generate_slug("Keyword Optimization")
        assert " " not in slug
        assert "-" in slug

    def test_generate_slug_removes_special_chars(self):
        """Special characters are stripped from slug."""
        writer = WikiWriter(db=MagicMock())
        slug = writer._generate_slug("Bid Strategy: 2026! What's New?")
        assert ":" not in slug
        assert "!" not in slug
        assert "?" not in slug

    def test_generate_slug_has_hash_suffix(self):
        """Slug ends with a 6-character hash suffix for uniqueness."""
        writer = WikiWriter(db=MagicMock())
        slug = writer._generate_slug("Exact Match Keywords")
        parts = slug.rsplit("-", 1)
        assert len(parts) >= 2
        assert len(parts[-1]) == 6

    def test_generate_slug_unique_per_title(self):
        """Different titles produce different slugs."""
        writer = WikiWriter(db=MagicMock())
        slug1 = writer._generate_slug("Quality Score")
        slug2 = writer._generate_slug("Quality Scores")
        assert slug1 != slug2


class TestWikiWriterWriteConsensusEntry:
    """Test WikiWriter.write_consensus_entry()."""

    def test_write_consensus_entry_calls_db_create_wiki_entry(self):
        """write_consensus_entry calls db.create_wiki_entry with correct data."""
        mock_db = MagicMock()
        mock_db.create_wiki_entry.return_value = {
            "id": str(uuid4()),
            "title": "Broad Match vs Exact Match",
            "slug": "broad-match-abc123",
            "content": "Broad match captures... exact match has highest CTR...",
            "sources": [{"url": "https://example.com"}],
            "tags": ["keyword", "match-type"],
        }
        writer = WikiWriter(db=mock_db)
        result = writer.write_consensus_entry(
            title="Broad Match vs Exact Match",
            content="Broad match captures... exact match has highest CTR...",
            green_rationale="Broad match increases reach",
            red_objections=[{"objection": "lower CTR"}],
            consensus_note="Use exact for high-intent, broad for discovery",
            sources=[{"url": "https://example.com"}],
            tags=["keyword", "match-type"],
        )
        mock_db.create_wiki_entry.assert_called_once()
        call_args = mock_db.create_wiki_entry.call_args
        assert call_args[0][0]["title"] == "Broad Match vs Exact Match"
        assert "slug" in call_args[0][0]
        assert call_args[0][0]["green_rationale"] == "Broad match increases reach"

    def test_write_consensus_entry_returns_db_result(self):
        """write_consensus_entry returns the created entry from DB."""
        mock_db = MagicMock()
        expected = {"id": str(uuid4()), "title": "Test", "slug": "test-abc123"}
        mock_db.create_wiki_entry.return_value = expected
        writer = WikiWriter(db=mock_db)
        result = writer.write_consensus_entry(
            title="Test",
            content="Content",
            green_rationale="",
            red_objections=[],
            consensus_note="",
            sources=[],
            tags=[],
        )
        assert result == expected


class TestWikiWriterInvalidateEntry:
    """Test WikiWriter.invalidate_entry()."""

    def test_invalidate_entry_calls_db_execute(self):
        """invalidate_entry calls db.execute with reason."""
        mock_db = MagicMock()
        entry_id = str(uuid4())
        reason = "Outdated — new research contradicts this"
        writer = WikiWriter(db=mock_db)
        writer.invalidate_entry(entry_id, reason)
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert reason in call_args[0][1]  # reason is a parameter
        assert entry_id in str(call_args[0][1])  # entry_id is a parameter
