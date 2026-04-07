"""
Wiki Writer — creates and invalidates wiki entries from consensus decisions.

After the adversarial loop reaches consensus, the WikiWriter records the
validated research as a wiki entry for future reference.
"""
import hashlib
import logging
import re
from typing import Any, Optional

from src.db.base import DatabaseAdapter

logger = logging.getLogger(__name__)


class WikiWriter:
    """
    Writes consensus decisions to the wiki and manages entry lifecycle.

    Args:
        db: DatabaseAdapter instance (creates PostgresAdapter if None)
    """

    def __init__(self, db: Optional[DatabaseAdapter] = None) -> None:
        if db is None:
            from src.db.postgres_adapter import PostgresAdapter
            db = PostgresAdapter()
        self._db = db

    def write_consensus_entry(
        self,
        title: str,
        content: str,
        green_rationale: str,
        red_objections: list[dict[str, Any]],
        consensus_note: str,
        sources: list[dict[str, Any]],
        tags: list[str],
    ) -> Optional[dict[str, Any]]:
        """
        Write a new wiki entry from a consensus decision.

        Args:
            title: Wiki entry title
            content: Full content body
            green_rationale: Green Team's reasoning
            red_objections: Red Team's objections (for transparency)
            consensus_note: Coordinator's summary of the agreed decision
            sources: List of source dicts (url, title, etc.)
            tags: List of tag strings

        Returns:
            The created wiki entry dict from the database, or None if the DB write fails.
        """
        slug = self._generate_slug(title)
        try:
            entry = self._db.create_wiki_entry({
                "title": title,
                "slug": slug,
                "content": content,
                "green_rationale": green_rationale,
                "red_objections": red_objections,
                "consensus_note": consensus_note,
                "sources": sources,
                "tags": tags,
            })
            return entry
        except Exception as exc:
            logger.warning(
                "wiki_entry_write_failed",
                extra={"title": title, "error": str(exc)},
            )
            return None

    def invalidate_entry(self, entry_id: str, reason: str) -> None:
        """
        Mark a wiki entry as invalidated.

        Args:
            entry_id: UUID of the wiki entry
            reason: Why the entry is being invalidated
        """
        try:
            self._db.execute(
                "UPDATE wiki_entries SET invalidated_at = NOW(), invalidation_reason = %s WHERE id = %s",
                (reason, str(entry_id)),
            )
        except Exception as exc:
            logger.warning(
                "wiki_entry_invalidate_failed",
                extra={"entry_id": entry_id, "error": str(exc)},
            )

    def _generate_slug(self, title: str) -> str:
        """
        Generate a URL-safe slug from a title with a collision-prevention hash suffix.

        Example: "Broad Match vs Exact Match" → "broad-match-vs-exact-match-a3f2b1"
        """
        # Remove special characters, keep alphanumeric and spaces/hyphens
        slug_base = re.sub(r'[^a-zA-Z0-9\s-]', '', title)
        slug_base = re.sub(r'[\s-]+', '-', slug_base.strip()).strip('-').lower()
        hash_suffix = hashlib.md5(title.encode()).hexdigest()[:6]
        return f"{slug_base}-{hash_suffix}"
