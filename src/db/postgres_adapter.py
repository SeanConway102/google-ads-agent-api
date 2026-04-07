"""
PostgreSQL adapter — implements DatabaseAdapter.
Uses psycopg2 with RealDictCursor for dict-like row access.
"""
from contextlib import contextmanager
from typing import Any, List, Optional
from uuid import UUID
import psycopg2
from psycopg2.extras import RealDictCursor

from src.config import get_database_url
from src.db.base import DatabaseAdapter


class PostgresAdapter(DatabaseAdapter):
    """
    PostgreSQL implementation of DatabaseAdapter.

    Connection is created per-operation (not pooled at adapter level).
    For high-performance production use, add connection pooling
    or switch to asyncpg with an async adapter.
    """

    def __init__(self, database_url: str = None):
        self.database_url = database_url or get_database_url()

    @contextmanager
    def _connection(self):
        """Context manager for a database connection."""
        conn = psycopg2.connect(self.database_url)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _cursor(self, conn):
        """Context manager for a RealDictCursor."""
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()

    # ─── Base operations ───────────────────────────────────────────────────────

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                return dict(result) if result else None

    def fetch_all(self, query: str, params: tuple = ()) -> List[dict]:
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    def execute(self, query: str, params: tuple = ()) -> None:
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute(query, params)
            conn.commit()

    def execute_returning(self, query: str, params: tuple = ()) -> dict:
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                conn.commit()
                return dict(result) if result else {}

    # ─── Campaign operations ─────────────────────────────────────────────────

    def create_campaign(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO campaigns
               (campaign_id, customer_id, name, api_key_token, campaign_type, owner_tag)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (
                data["campaign_id"],
                data["customer_id"],
                data["name"],
                data["api_key_token"],
                data.get("campaign_type"),
                data.get("owner_tag"),
            ),
        )

    def get_campaign(self, id: UUID) -> Optional[dict]:
        return self.fetch_one(
            "SELECT * FROM campaigns WHERE id = %s",
            (str(id),)
        )

    def get_campaign_by_owner_email(self, owner_email: str) -> Optional[dict]:
        """Find a campaign by the owner's email address."""
        return self.fetch_one(
            "SELECT * FROM campaigns WHERE owner_email = %s LIMIT 1",
            (owner_email,),
        )

    def list_campaigns(self) -> List[dict]:
        return self.fetch_all(
            "SELECT * FROM campaigns ORDER BY created_at DESC"
        )

    def delete_campaign(self, id: UUID) -> None:
        self.execute("DELETE FROM campaigns WHERE id = %s", (str(id),))

    # ─── Wiki operations ──────────────────────────────────────────────────────

    def search_wiki(self, query: str, limit: int = 10) -> List[dict]:
        """
        Full-text search using PostgreSQL tsvector.
        Embeddingless RAG: uses ts_rank for relevance scoring instead of vector similarity.
        """
        # Strip tsquery metacharacters to prevent syntax errors and DoS.
        # Keep only alphanumeric and spaces.
        safe_parts = "".join(c if c.isalnum() or c.isspace() else " " for c in query).split()
        tsquery_parts = " & ".join(p for p in safe_parts if p)
        if not tsquery_parts:
            return []
        return self.fetch_all(
            """SELECT *,
                      ts_rank(search_vector, query) AS rank
               FROM wiki_entries,
                    to_tsquery('english', %s) AS query
               WHERE search_vector @@ query
                 AND invalidated_at IS NULL
               ORDER BY rank DESC
               LIMIT %s""",
            (tsquery_parts, limit)
        )

    def create_wiki_entry(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO wiki_entries
               (title, slug, content, sources, green_rationale,
                red_objections, consensus_note, tags)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (
                data["title"],
                data["slug"],
                data["content"],
                self._jsonb(data.get("sources", [])),
                data.get("green_rationale"),
                self._jsonb(data.get("red_objections", [])),
                data.get("consensus_note"),
                data.get("tags", []),
            ),
        )

    def get_wiki_entry(self, id: UUID) -> Optional[dict]:
        return self.fetch_one(
            "SELECT * FROM wiki_entries WHERE id = %s",
            (str(id),)
        )

    def invalidate_wiki_entry(self, id: UUID, reason: str) -> None:
        self.execute(
            "UPDATE wiki_entries SET invalidated_at = NOW(), invalidation_reason = %s WHERE id = %s",
            (reason, str(id)),
        )

    # ─── Debate state ─────────────────────────────────────────────────────────

    def save_debate_state(self, data: dict) -> dict:
        """
        Upsert debate state — ON CONFLICT DO UPDATE ensures one state per campaign+cycle.
        """
        return self.execute_returning(
            """INSERT INTO debate_state
               (cycle_date, campaign_id, phase, round_number,
                green_proposals, red_objections, coordinator_decision,
                consensus_reached, compromise_accepted_by_green, compromise_accepted_by_red)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (cycle_date, campaign_id) DO UPDATE SET
                 phase                     = EXCLUDED.phase,
                 round_number              = EXCLUDED.round_number,
                 green_proposals          = EXCLUDED.green_proposals,
                 red_objections           = EXCLUDED.red_objections,
                 coordinator_decision     = EXCLUDED.coordinator_decision,
                 consensus_reached        = EXCLUDED.consensus_reached,
                 compromise_accepted_by_green = EXCLUDED.compromise_accepted_by_green,
                 compromise_accepted_by_red   = EXCLUDED.compromise_accepted_by_red,
                 updated_at               = NOW()
               RETURNING *""",
            (
                data["cycle_date"],
                str(data["campaign_id"]),
                data["phase"],
                data.get("round_number", 1),
                self._jsonb(data.get("green_proposals", [])),
                self._jsonb(data.get("red_objections", [])),
                self._jsonb(data.get("coordinator_decision")),
                data.get("consensus_reached", False),
                data.get("compromise_accepted_by_green", False),
                data.get("compromise_accepted_by_red", False),
            ),
        )

    def get_latest_debate_state(self, cycle_date: str, campaign_id: UUID) -> Optional[dict]:
        return self.fetch_one(
            """SELECT * FROM debate_state
               WHERE cycle_date = %s AND campaign_id = %s
               ORDER BY id DESC LIMIT 1""",
            (cycle_date, str(campaign_id))
        )

    def get_latest_debate_state_any_cycle(self, campaign_id: UUID) -> Optional[dict]:
        return self.fetch_one(
            """SELECT * FROM debate_state
               WHERE campaign_id = %s
               ORDER BY id DESC LIMIT 1""",
            (str(campaign_id),)
        )

    # ─── Audit log ───────────────────────────────────────────────────────────

    def write_audit_log(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO audit_log
               (cycle_date, campaign_id, action_type, target,
                green_proposal, red_objections, coordinator_note, debate_rounds)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (
                data["cycle_date"],
                str(data["campaign_id"]) if data.get("campaign_id") else None,
                data["action_type"],
                self._jsonb(data.get("target")),
                self._jsonb(data.get("green_proposal")),
                self._jsonb(data.get("red_objections")),
                data.get("coordinator_note"),
                data.get("debate_rounds"),
            ),
        )

    def query_audit_log(
        self,
        campaign_id: Optional[UUID] = None,
        action_type: Optional[str] = None,
        cycle_date: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """
        Query audit log with optional filters.
        Builds a WHERE clause dynamically to avoid unused parameter binding issues.
        """
        conditions = []
        params: list[Any] = []

        if campaign_id is not None:
            conditions.append("campaign_id = %s")
            params.append(str(campaign_id))
        if action_type is not None:
            conditions.append("action_type = %s")
            params.append(action_type)
        if cycle_date is not None:
            conditions.append("cycle_date = %s")
            params.append(cycle_date)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM audit_log WHERE {where_clause} ORDER BY performed_at DESC LIMIT %s"
        params.append(limit)

        return self.fetch_all(query, tuple(params))

    # ─── Webhooks ─────────────────────────────────────────────────────────────

    def register_webhook(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO webhook_subscriptions (url, events, secret)
               VALUES (%s, %s, %s)
               RETURNING *""",
            (
                data["url"],
                data.get("events", []),
                data.get("secret"),
            ),
        )

    def list_webhooks(self) -> List[dict]:
        return self.fetch_all("SELECT * FROM webhook_subscriptions WHERE active = TRUE")

    def delete_webhook(self, id: UUID) -> None:
        self.execute("DELETE FROM webhook_subscriptions WHERE id = %s", (str(id),))

    def write_webhook_delivery_log(self, data: dict) -> dict:
        """
        Persist a webhook delivery attempt to webhook_delivery_log.
        Handles state transitions: pending -> retrying -> delivered/failed.
        """
        return self.execute_returning(
            """INSERT INTO webhook_delivery_log
               (subscription_id, event, payload, status, attempts,
                next_retry_at, last_error, delivered_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (
                str(data["subscription_id"]),
                data["event"],
                self._jsonb(data.get("payload", {})),
                data["status"],
                data.get("attempts", 0),
                data.get("next_retry_at"),
                data.get("last_error"),
                data.get("delivered_at"),
            ),
        )

    # ─── HITL Proposals ───────────────────────────────────────────────────────

    def create_hitl_proposal(self, data: dict) -> dict:
        """Insert a new hitl_proposal row. Returns the inserted row."""
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute("""
                    INSERT INTO hitl_proposals
                        (campaign_id, proposal_type, impact_summary, reasoning, status)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    str(data["campaign_id"]),
                    data["proposal_type"],
                    data["impact_summary"],
                    data["reasoning"],
                    data.get("status", "pending"),
                ))
                return dict(cur.fetchone())

    def list_hitl_proposals(
        self, campaign_id: UUID, status: str | None = None
    ) -> List[dict]:
        """List hitl_proposals for a campaign, optionally filtered by status."""
        if status:
            return self.fetch_all("""
                SELECT * FROM hitl_proposals
                WHERE campaign_id = %s AND status = %s
                ORDER BY created_at DESC
            """, (str(campaign_id), status))
        return self.fetch_all("""
            SELECT * FROM hitl_proposals
            WHERE campaign_id = %s
            ORDER BY created_at DESC
        """, (str(campaign_id),))

    def update_hitl_proposal_status(
        self,
        proposal_id: UUID,
        status: str,
        replier_response: str | None = None,
    ) -> dict:
        """Update a hitl_proposal's status and optionally the replier response."""
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute("""
                    UPDATE hitl_proposals
                    SET status = %s,
                        replier_response = COALESCE(%s, replier_response),
                        decided_at = CASE
                            WHEN %s IN ('approved', 'rejected', 'expired')
                            THEN NOW() ELSE decided_at END,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                """, (status, replier_response, status, str(proposal_id)))
                row = cur.fetchone()
                return dict(row) if row else {}

    def get_hitl_proposal(self, proposal_id: UUID) -> Optional[dict]:
        """Get a single hitl_proposal by ID."""
        return self.fetch_one(
            "SELECT * FROM hitl_proposals WHERE id = %s",
            (str(proposal_id),)
        )

    # ─── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _jsonb(value: Any) -> str:
        """Serialize a value to JSON string for PostgreSQL JSONB."""
        import json
        return json.dumps(value)
