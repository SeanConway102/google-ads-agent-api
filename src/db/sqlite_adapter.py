"""
SQLite adapter — implements DatabaseAdapter for local/portable development.

This adapter provides a full SQLite implementation of the DatabaseAdapter
interface. It translates PostgreSQL-specific constructs to SQLite:

- UUIDs stored as text strings
- JSONB → TEXT (application-level JSON serialization)
- tsvector full-text search → LIKE-based search (SQLite has no tsvector)
- Arrays → stored as JSON text
- TIMESTAMPTZ → TEXT ISO 8601 timestamps
- SERIAL PRIMARY KEY → INTEGER PRIMARY KEY (AUTOINCREMENT)
- Upsert via INSERT ... ON CONFLICT DO UPDATE (SQLite ≥ 3.24)
"""
import json
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

import sqlite3

from src.db.base import DatabaseAdapter


class SqliteAdapter(DatabaseAdapter):
    """
    SQLite implementation of DatabaseAdapter.

    Uses a single-file database (path provided to constructor).
    Use ':memory:' for an ephemeral in-memory database.
    """

    def __init__(self, database_url: str = ":memory:"):
        if database_url == ":memory:":
            # Use a file-based temp DB instead of :memory: so all connections
            # share the same database (avoids SQLite connection isolation issues)
            import tempfile
            fd, self._database_path = tempfile.mkstemp(suffix=".db")
            import os
            os.close(fd)
            self._conn = sqlite3.connect(self._database_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        else:
            self._database_path = database_url
            self._conn = sqlite3.connect(self._database_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        """Create all tables if they don't exist. Call after construction."""
        cur = self._conn.cursor()
        cur.executescript(_SCHEMA)
        self._conn.commit()

    # ─── Base operations ─────────────────────────────────────────────────────

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        cur = self._conn.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            return None
        columns = [d[0] for d in cur.description]
        return dict(zip(columns, row))

    def fetch_all(self, query: str, params: tuple = ()) -> List[dict]:
        cur = self._conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(columns, row)) for row in rows]

    def execute(self, query: str, params: tuple = ()) -> None:
        cur = self._conn.cursor()
        cur.execute(query, params)
        self._conn.commit()

    def execute_returning(self, query: str, params: tuple = ()) -> dict:
        cur = self._conn.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        self._conn.commit()
        if row is None:
            return {}
        columns = [d[0] for d in cur.description]
        return dict(zip(columns, row))

    # ─── Campaign operations ─────────────────────────────────────────────────

    def create_campaign(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO campaigns
               (id, campaign_id, customer_id, name, api_key_token,
                status, campaign_type, owner_tag,
                hitl_enabled, owner_email, hitl_threshold,
                created_at, last_synced_at, last_reviewed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING *""",
            (
                str(uuid4()),
                data["campaign_id"],
                data["customer_id"],
                data["name"],
                data["api_key_token"],
                "active",
                data.get("campaign_type"),
                data.get("owner_tag"),
                data.get("hitl_enabled", False),
                data.get("owner_email"),
                data.get("hitl_threshold", "budget>20pct,keyword_add>5"),
                _now(),
                None,
                None,
            ),
        )

    def get_campaign(self, id: UUID) -> Optional[dict]:
        return self.fetch_one(
            "SELECT * FROM campaigns WHERE id = ?",
            (str(id),)
        )

    def get_campaign_by_owner_email(self, owner_email: str) -> Optional[dict]:
        return self.fetch_one(
            "SELECT * FROM campaigns WHERE owner_email = ? LIMIT 1",
            (owner_email,)
        )

    def list_campaigns(self) -> List[dict]:
        return self.fetch_all(
            "SELECT * FROM campaigns ORDER BY created_at DESC"
        )

    def delete_campaign(self, id: UUID) -> None:
        self.execute("DELETE FROM campaigns WHERE id = ?", (str(id),))

    # ─── Wiki operations ──────────────────────────────────────────────────────

    def search_wiki(self, query: str, limit: int = 10) -> List[dict]:
        """
        Full-text search using SQLite LIKE (no tsvector).
        Searches title and content for each word in the query.
        Returns active (non-invalidated) entries ordered by creation date.
        """
        terms = " ".join(query.split()).split()
        conditions = " AND ".join("(title LIKE ? OR content LIKE ?)" for _ in terms)
        params: list[Any] = sum([[f"%{t}%", f"%{t}%"] for t in terms], [])
        params.extend([limit])
        return self.fetch_all(
            f"""SELECT *,
                        0.0 AS rank
                 FROM wiki_entries
                 WHERE ({conditions})
                   AND invalidated_at IS NULL
                 ORDER BY created_at DESC
                 LIMIT ?""",
            tuple(params)
        )

    def create_wiki_entry(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO wiki_entries
               (id, title, slug, content, sources, green_rationale,
                red_objections, consensus_note, tags,
                created_at, updated_at, verified_at, invalidated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING *""",
            (
                str(uuid4()),
                data["title"],
                data["slug"],
                data["content"],
                _json(data.get("sources", [])),
                data.get("green_rationale"),
                _json(data.get("red_objections", [])),
                data.get("consensus_note"),
                _json(data.get("tags", [])),
                _now(),
                _now(),
                None,
                None,
            ),
        )

    def get_wiki_entry(self, id: UUID) -> Optional[dict]:
        return self.fetch_one(
            "SELECT * FROM wiki_entries WHERE id = ?",
            (str(id),)
        )

    def invalidate_wiki_entry(self, id: UUID, reason: str) -> None:
        self.execute(
            "UPDATE wiki_entries SET invalidated_at = ?, invalidation_reason = ? WHERE id = ?",
            (_now(), reason, str(id))
        )

    # ─── Debate state ─────────────────────────────────────────────────────────

    def save_debate_state(self, data: dict) -> dict:
        """
        Upsert debate state for a campaign + cycle.
        Uses INSERT ... ON CONFLICT DO UPDATE (SQLite ≥ 3.24).
        """
        return self.execute_returning(
            """INSERT INTO debate_state
               (cycle_date, campaign_id, phase, round_number,
                green_proposals, red_objections, coordinator_decision,
                consensus_reached, compromise_accepted_by_green, compromise_accepted_by_red,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (cycle_date, campaign_id) DO UPDATE SET
                 phase                      = excluded.phase,
                 round_number               = excluded.round_number,
                 green_proposals           = excluded.green_proposals,
                 red_objections            = excluded.red_objections,
                 coordinator_decision       = excluded.coordinator_decision,
                 consensus_reached         = excluded.consensus_reached,
                 compromise_accepted_by_green = excluded.compromise_accepted_by_green,
                 compromise_accepted_by_red    = excluded.compromise_accepted_by_red,
                 updated_at                = excluded.updated_at
               RETURNING *""",
            (
                data["cycle_date"],
                str(data["campaign_id"]),
                data["phase"],
                data.get("round_number", 1),
                _json(data.get("green_proposals", [])),
                _json(data.get("red_objections", [])),
                _json(data.get("coordinator_decision")),
                1 if data.get("consensus_reached", False) else 0,
                1 if data.get("compromise_accepted_by_green", False) else 0,
                1 if data.get("compromise_accepted_by_red", False) else 0,
                _now(),
                _now(),
            ),
        )

    def get_latest_debate_state(self, cycle_date: str, campaign_id: UUID) -> Optional[dict]:
        return self.fetch_one(
            """SELECT * FROM debate_state
               WHERE cycle_date = ? AND campaign_id = ?
               ORDER BY id DESC LIMIT 1""",
            (cycle_date, str(campaign_id))
        )

    def get_latest_debate_state_any_cycle(self, campaign_id: UUID) -> Optional[dict]:
        return self.fetch_one(
            """SELECT * FROM debate_state
               WHERE campaign_id = ?
               ORDER BY id DESC LIMIT 1""",
            (str(campaign_id),)
        )

    # ─── Audit log ───────────────────────────────────────────────────────────

    def write_audit_log(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO audit_log
               (id, cycle_date, campaign_id, action_type, target,
                green_proposal, red_objections, coordinator_note, debate_rounds,
                performed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING *""",
            (
                str(uuid4()),
                data["cycle_date"],
                str(data["campaign_id"]) if data.get("campaign_id") else None,
                data["action_type"],
                _json(data.get("target")),
                _json(data.get("green_proposal")),
                _json(data.get("red_objections")),
                data.get("coordinator_note"),
                data.get("debate_rounds"),
                _now(),
            ),
        )

    def query_audit_log(
        self,
        campaign_id: Optional[UUID] = None,
        action_type: Optional[str] = None,
        cycle_date: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        conditions = []
        params: list[Any] = []
        if campaign_id is not None:
            conditions.append("campaign_id = ?")
            params.append(str(campaign_id))
        if action_type is not None:
            conditions.append("action_type = ?")
            params.append(action_type)
        if cycle_date is not None:
            conditions.append("cycle_date = ?")
            params.append(cycle_date)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM audit_log WHERE {where_clause} ORDER BY performed_at DESC LIMIT ?"
        params.append(limit)
        return self.fetch_all(query, tuple(params))

    # ─── Webhooks ─────────────────────────────────────────────────────────────

    def register_webhook(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO webhook_subscriptions
               (id, url, events, secret, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               RETURNING *""",
            (
                str(uuid4()),
                data["url"],
                _json(data.get("events", [])),
                data.get("secret"),
                1,
                _now(),
            ),
        )

    def list_webhooks(self) -> List[dict]:
        return self.fetch_all(
            "SELECT * FROM webhook_subscriptions WHERE active = 1"
        )

    def delete_webhook(self, id: UUID) -> None:
        self.execute("DELETE FROM webhook_subscriptions WHERE id = ?", (str(id),))

    def write_webhook_delivery_log(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO webhook_delivery_log
               (id, subscription_id, event, payload, status,
                attempts, next_retry_at, last_error, delivered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING *""",
            (
                str(uuid4()),
                str(data["subscription_id"]),
                data["event"],
                _json(data.get("payload", {})),
                data.get("status", "pending"),
                data.get("attempts", 0),
                data.get("next_retry_at"),
                data.get("last_error"),
                data.get("delivered_at"),
            ),
        )

    # ─── HITL Proposals ─────────────────────────────────────────────────────

    def create_hitl_proposal(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO hitl_proposals
               (id, campaign_id, proposal_type, impact_summary, reasoning,
                status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING *""",
            (
                str(uuid4()),
                str(data["campaign_id"]),
                data["proposal_type"],
                data["impact_summary"],
                data["reasoning"],
                data.get("status", "pending"),
                _now(),
                _now(),
            ),
        )

    def list_hitl_proposals(
        self,
        campaign_id: str,
        status: Optional[str] = None,
    ) -> List[dict]:
        cid = str(campaign_id)
        if status is not None:
            return self.fetch_all(
                """SELECT * FROM hitl_proposals
                   WHERE campaign_id = ? AND status = ?
                   ORDER BY created_at DESC""",
                (cid, status)
            )
        return self.fetch_all(
            """SELECT * FROM hitl_proposals
               WHERE campaign_id = ?
               ORDER BY created_at DESC""",
            (cid,)
        )

    def update_hitl_proposal_status(
        self,
        proposal_id: str,
        status: str,
    ) -> None:
        self.execute(
            """UPDATE hitl_proposals
               SET status = ?,
                   decided_at = CASE WHEN ? IN ('approved','rejected','expired')
                                    THEN ? ELSE decided_at END,
                   updated_at = ?
               WHERE id = ?""",
            (status, status, _now(), _now(), proposal_id)
        )

    def get_hitl_proposal(self, proposal_id: UUID) -> Optional[dict]:
        return self.fetch_one(
            "SELECT * FROM hitl_proposals WHERE id = ?",
            (str(proposal_id),)
        )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def uuid4() -> str:
    """Generate a new UUID string."""
    import uuid
    return str(uuid.uuid4())


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    """Serialize a value to JSON string."""
    return json.dumps(value)

# ─── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id              TEXT PRIMARY KEY,
    campaign_id     TEXT NOT NULL,
    customer_id     TEXT NOT NULL,
    name            TEXT NOT NULL,
    api_key_token   TEXT NOT NULL,
    status          TEXT DEFAULT 'active',
    campaign_type   TEXT,
    owner_tag       TEXT,
    created_at      TEXT,
    last_synced_at  TEXT,
    last_reviewed_at TEXT,
    -- HITL settings
    hitl_enabled    INTEGER DEFAULT 0,
    owner_email     TEXT,
    hitl_threshold  TEXT DEFAULT 'budget>20pct,keyword_add>5'
);

CREATE TABLE IF NOT EXISTS wiki_entries (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    slug            TEXT UNIQUE NOT NULL,
    content         TEXT NOT NULL,
    sources         TEXT DEFAULT '[]',
    green_rationale TEXT,
    red_objections  TEXT DEFAULT '[]',
    consensus_note  TEXT,
    tags            TEXT DEFAULT '[]',
    created_at      TEXT,
    updated_at      TEXT,
    verified_at     TEXT,
    invalidated_at   TEXT,
    invalidation_reason TEXT
);

CREATE TABLE IF NOT EXISTS debate_state (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date              TEXT NOT NULL,
    campaign_id             TEXT,
    phase                   TEXT NOT NULL DEFAULT 'idle',
    round_number            INTEGER DEFAULT 1,
    green_proposals         TEXT DEFAULT '[]',
    red_objections          TEXT DEFAULT '[]',
    coordinator_decision   TEXT,
    consensus_reached       INTEGER DEFAULT 0,
    compromise_accepted_by_green INTEGER DEFAULT 0,
    compromise_accepted_by_red   INTEGER DEFAULT 0,
    created_at              TEXT,
    updated_at              TEXT,
    UNIQUE (cycle_date, campaign_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              TEXT PRIMARY KEY,
    cycle_date      TEXT NOT NULL,
    campaign_id     TEXT,
    action_type     TEXT NOT NULL,
    target          TEXT,
    green_proposal  TEXT,
    red_objections  TEXT,
    coordinator_note TEXT,
    debate_rounds   INTEGER,
    performed_at    TEXT
);

CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id          TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    events      TEXT DEFAULT '[]',
    secret      TEXT,
    active      INTEGER DEFAULT 1,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS webhook_delivery_log (
    id              TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL,
    event           TEXT NOT NULL,
    payload         TEXT,
    status          TEXT DEFAULT 'pending',
    attempts        INTEGER DEFAULT 0,
    next_retry_at   TEXT,
    last_error      TEXT,
    delivered_at   TEXT
);

CREATE TABLE IF NOT EXISTS hitl_proposals (
    id                TEXT PRIMARY KEY,
    campaign_id       TEXT NOT NULL,
    proposal_type    TEXT NOT NULL,
    impact_summary   TEXT NOT NULL,
    reasoning        TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    decided_at       TEXT,
    replier_response  TEXT
);
"""
