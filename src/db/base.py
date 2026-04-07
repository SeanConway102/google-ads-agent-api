"""
Database adapter interface.
Mirrors ClientApp's repository pattern — interface in package, implementation separate.
All database operations go through this interface for swappability.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID


class DatabaseAdapter(ABC):
    """
    Abstract database interface.

    Implementations:
    - PostgresAdapter (src/db/postgres_adapter.py) — PostgreSQL 16
    - SqliteAdapter (future: src/db/sqlite_adapter.py) — SQLite

    All campaign and wiki operations go through this interface.
    To swap databases, implement this interface and set DB_PROVIDER env var.
    """

    # ─── Base operations ───────────────────────────────────────────────────────

    @abstractmethod
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        """Execute a query and return one row as dict, or None."""
        pass

    @abstractmethod
    def fetch_all(self, query: str, params: tuple = ()) -> List[dict]:
        """Execute a query and return all rows as list of dicts."""
        pass

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> None:
        """Execute a query that doesn't return rows (INSERT/UPDATE/DELETE)."""
        pass

    @abstractmethod
    def execute_returning(self, query: str, params: tuple = ()) -> dict:
        """Execute a query with RETURNING clause and return the row as dict."""
        pass

    # ─── Campaign operations ─────────────────────────────────────────────────

    @abstractmethod
    def create_campaign(self, data: dict) -> dict:
        """
        Insert a new campaign. Returns the created campaign row.
        Raises: Exception if campaign_id already exists (UNIQUE constraint).
        """
        pass

    @abstractmethod
    def get_campaign(self, id: UUID) -> Optional[dict]:
        """Get a campaign by UUID. Returns None if not found."""
        pass

    @abstractmethod
    def list_campaigns(self) -> List[dict]:
        """List all campaigns, ordered by created_at DESC."""
        pass

    @abstractmethod
    def delete_campaign(self, id: UUID) -> None:
        """Delete a campaign by UUID. No-op if not found."""
        pass

    # ─── Wiki operations ──────────────────────────────────────────────────────

    @abstractmethod
    def search_wiki(self, query: str, limit: int = 10) -> List[dict]:
        """
        Full-text search the wiki using PostgreSQL tsvector.
        Returns active (non-invalidated) entries matching the query,
        ordered by relevance (ts_rank).
        """
        pass

    @abstractmethod
    def create_wiki_entry(self, data: dict) -> dict:
        """
        Create a new wiki entry from validated research.
        Returns the created entry.
        """
        pass

    @abstractmethod
    def get_wiki_entry(self, id: UUID) -> Optional[dict]:
        """Get a wiki entry by UUID. Returns None if not found."""
        pass

    @abstractmethod
    def invalidate_wiki_entry(self, id: UUID, reason: str) -> None:
        """Mark a wiki entry as invalidated (not deleted — preserves audit trail)."""
        pass

    # ─── Debate state ─────────────────────────────────────────────────────────

    @abstractmethod
    def save_debate_state(self, data: dict) -> dict:
        """
        Save (upsert) debate state for a campaign + cycle.
        Uses ON CONFLICT DO UPDATE so state is updated, not duplicated.
        """
        pass

    @abstractmethod
    def get_latest_debate_state(self, cycle_date: str, campaign_id: UUID) -> Optional[dict]:
        """Get the most recent debate state for a campaign's cycle. Returns None if none."""
        pass

    @abstractmethod
    def get_latest_debate_state_any_cycle(self, campaign_id: UUID) -> Optional[dict]:
        """Get the most recent debate state for a campaign across any cycle date. Returns None if none."""
        pass

    # ─── Audit log ───────────────────────────────────────────────────────────

    @abstractmethod
    def write_audit_log(self, data: dict) -> dict:
        """
        Write an immutable audit log entry.
        Returns the created audit log row.
        """
        pass

    @abstractmethod
    def query_audit_log(
        self,
        campaign_id: Optional[UUID] = None,
        action_type: Optional[str] = None,
        cycle_date: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """
        Query audit log entries with optional filters.
        Returns entries ordered by performed_at DESC.
        """
        pass

    # ─── Webhooks ─────────────────────────────────────────────────────────────

    @abstractmethod
    def register_webhook(self, data: dict) -> dict:
        """Register a new webhook subscription. Returns the created row."""
        pass

    @abstractmethod
    def list_webhooks(self) -> List[dict]:
        """List all webhook subscriptions."""
        pass

    @abstractmethod
    def delete_webhook(self, id: UUID) -> None:
        """Delete a webhook subscription by UUID."""
        pass
