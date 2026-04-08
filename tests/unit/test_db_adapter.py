"""
RED: Write the failing test first.
Tests for src/db/base.py (DatabaseAdapter interface) and src/db/postgres_adapter.py.

Since we cannot connect to a real DB in unit tests, we mock psycopg2.connect.
Mock strategy: temporarily swap psycopg2.connect in the psycopg2 module itself
before importing, then restore after all tests in the class finish.
"""
import pytest
import importlib
from unittest.mock import MagicMock


# ──────────────────────────────────────────────────────────────────────────────
# Mock helpers — build a realistic psycopg2 connection mock
# ──────────────────────────────────────────────────────────────────────────────

def make_mock_cursor(fetchone_result=None, fetchall_result=None):
    """Build a cursor mock that dict(cursor.fetchone()) returns the right data."""
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    return cursor


def make_mock_connection(cursor_mock):
    """Build a connection mock that returns our cursor mock."""
    cursor_mock.__enter__ = MagicMock(return_value=cursor_mock)
    cursor_mock.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cursor_mock
    return conn


CAMPAIGN_ROW = {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "campaign_id": "cmp_001",
    "customer_id": "cust_001",
    "name": "Summer Sale",
    "api_key_token": "token_abc",
    "status": "active",
    "campaign_type": "search",
    "owner_tag": "marketing",
    "created_at": "2026-04-06T10:00:00Z",
    "last_synced_at": None,
    "last_reviewed_at": None,
}


# ──────────────────────────────────────────────────────────────────────────────
# Interface tests — no DB needed
# ──────────────────────────────────────────────────────────────────────────────

class TestDatabaseAdapterInterface:
    """Tests that DatabaseAdapter defines the complete interface."""

    def test_base_class_exists(self):
        """DatabaseAdapter base class must exist in src.db.base."""
        from src.db.base import DatabaseAdapter
        assert DatabaseAdapter is not None

    def test_interface_has_all_required_methods(self):
        """The interface must define all required database operations."""
        from src.db.base import DatabaseAdapter
        required_methods = [
            # Campaign operations
            "create_campaign", "get_campaign", "list_campaigns", "delete_campaign",
            "get_campaign_by_owner_email",
            # Wiki operations
            "search_wiki", "create_wiki_entry", "get_wiki_entry", "invalidate_wiki_entry",
            # Debate state
            "save_debate_state", "get_latest_debate_state", "get_latest_debate_state_any_cycle",
            # Audit
            "write_audit_log", "query_audit_log",
            # Webhooks
            "register_webhook", "list_webhooks", "delete_webhook",
            "write_webhook_delivery_log",
            # HITL proposals
            "create_hitl_proposal", "list_hitl_proposals",
            "update_hitl_proposal_status", "get_hitl_proposal",
            # Base
            "fetch_one", "fetch_all", "execute", "execute_returning",
        ]
        for method in required_methods:
            assert hasattr(DatabaseAdapter, method), \
                f"DatabaseAdapter must define method: {method}"

    def test_interface_is_abstract(self):
        """DatabaseAdapter must be abstract (cannot be instantiated directly)."""
        from src.db.base import DatabaseAdapter
        with pytest.raises(TypeError):
            DatabaseAdapter()


# ──────────────────────────────────────────────────────────────────────────────
# Test class base — handles psycopg2.connect swap for all subclasses
# ──────────────────────────────────────────────────────────────────────────────

class TestAdapterWithMock:
    """
    Base class that swaps psycopg2.connect before tests run and restores after.
    Subclasses set self.cursor in their setup.
    """

    # Store original connect and mock cursor at class level
    _original_connect = None
    _mock_cursor = None

    @classmethod
    def setup_class(cls):
        """Swap psycopg2.connect before any test runs."""
        import psycopg2
        cls._original_connect = psycopg2.connect
        mock_conn = make_mock_connection(cls._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn)
        # Reload so adapter picks up swapped psycopg2.connect
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        cls._adapter_class = pa_module.PostgresAdapter

    @classmethod
    def teardown_class(cls):
        """Restore original psycopg2.connect after all tests finish."""
        import psycopg2
        if cls._original_connect is not None:
            psycopg2.connect = cls._original_connect
            cls._original_connect = None

    def make_adapter(self) -> "PostgresAdapter":
        """Create a new adapter instance using the mocked psycopg2."""
        return self._adapter_class("postgresql://fake")


# ──────────────────────────────────────────────────────────────────────────────
# Campaign operation tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPostgresAdapterCampaigns(TestAdapterWithMock):

    @classmethod
    def setup_class(cls):
        cls._mock_cursor = make_mock_cursor(fetchone_result=CAMPAIGN_ROW)
        super().setup_class()

    def test_create_campaign_returns_dict(self):
        """create_campaign must return a campaign dict and execute the INSERT."""
        adapter = self.make_adapter()
        result = adapter.create_campaign({
            "campaign_id": "cmp_001",
            "customer_id": "cust_001",
            "name": "Summer Sale",
            "api_key_token": "token_abc",
            "campaign_type": "search",
            "owner_tag": "marketing",
        })
        assert isinstance(result, dict)
        assert result["campaign_id"] == "cmp_001"
        assert result["name"] == "Summer Sale"
        self._mock_cursor.execute.assert_called()
        mock_call = self._mock_cursor.execute.call_args
        assert "INSERT INTO campaigns" in mock_call[0][0]

    def test_get_campaign_returns_campaign(self):
        """get_campaign must return a campaign dict when found."""
        adapter = self.make_adapter()
        from uuid import UUID
        result = adapter.get_campaign(UUID("123e4567-e89b-12d3-a456-426614174000"))
        assert result is not None
        assert result["campaign_id"] == "cmp_001"

    def test_get_campaign_returns_none_when_not_found(self):
        """get_campaign returns None when no campaign exists."""
        cursor = make_mock_cursor(fetchone_result=None)
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.get_campaign(UUID("00000000-0000-0000-0000-000000000000"))
        assert result is None
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_list_campaigns_returns_list_ordered(self):
        """list_campaigns must return a list ordered by created_at DESC."""
        cursor = make_mock_cursor(fetchall_result=[CAMPAIGN_ROW])
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        result = adapter.list_campaigns()
        assert isinstance(result, list)
        assert len(result) == 1
        call_args = cursor.execute.call_args
        assert "ORDER BY created_at DESC" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_delete_campaign_calls_execute(self):
        """delete_campaign must execute the DELETE statement."""
        cursor = make_mock_cursor()
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        adapter.delete_campaign(UUID("123e4567-e89b-12d3-a456-426614174000"))
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "DELETE FROM campaigns" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_get_campaign_by_owner_email_returns_campaign(self):
        """get_campaign_by_owner_email returns a campaign when found by email."""
        cursor = make_mock_cursor(fetchone_result=CAMPAIGN_ROW)
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        result = adapter.get_campaign_by_owner_email("owner@example.com")
        assert result is not None
        assert result["campaign_id"] == "cmp_001"
        call_args = cursor.execute.call_args
        assert "owner_email" in call_args[0][0]
        assert "LIMIT 1" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)


# ──────────────────────────────────────────────────────────────────────────────
# Wiki operation tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPostgresAdapterWiki(TestAdapterWithMock):

    @classmethod
    def setup_class(cls):
        cls._mock_cursor = make_mock_cursor(fetchall_result=[
            {"id": "1", "title": "Keyword Optimization", "slug": "keyword-opt", "rank": 0.5}
        ])
        super().setup_class()

    def test_search_wiki_uses_full_text_search_tsvector(self):
        """search_wiki must use PostgreSQL tsvector for embeddingless RAG."""
        adapter = self.make_adapter()
        result = adapter.search_wiki("keyword optimization", limit=5)
        call_args = self._mock_cursor.execute.call_args
        sql_query = call_args[0][0]
        assert "search_vector" in sql_query, "Must use tsvector search_vector column"
        assert "@@" in sql_query, "Must use @@ tsvector match operator"
        assert "ts_rank" in sql_query.lower(), "Must use ts_rank for relevance"

    def test_search_wiki_only_returns_active_entries(self):
        """search_wiki must exclude invalidated entries."""
        cursor = make_mock_cursor(fetchall_result=[])
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        adapter.search_wiki("test", limit=10)
        call_args = cursor.execute.call_args
        sql_query = call_args[0][0]
        assert "invalidated_at IS NULL" in sql_query, \
            "Must filter out invalidated wiki entries"
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_search_wiki_strips_metacharacters(self):
        """search_wiki strips tsquery metacharacters to prevent syntax errors."""
        cursor = make_mock_cursor(fetchall_result=[])
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        adapter.search_wiki("keyword:exact")  # colon is a tsquery metacharacter
        call_args = cursor.execute.call_args
        # Should strip colon, resulting in "keyword exact" query parts
        bound_params = call_args[0][1]
        assert ":" not in bound_params[0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_search_wiki_returns_empty_for_query_with_only_metacharacters(self):
        """search_wiki returns [] when query becomes empty after stripping metacharacters."""
        cursor = make_mock_cursor(fetchall_result=[])
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        result = adapter.search_wiki(":::")
        assert result == []
        cursor.execute.assert_not_called()
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_create_wiki_entry_returns_entry_with_all_fields(self):
        """create_wiki_entry must store all research fields and return the entry."""
        wiki_row = {
            "id": "wiki_001",
            "title": "Ad CTR Optimization",
            "slug": "ad-ctr-optimization-abc123",
            "content": "Full content...",
            "sources": [{"url": "https://example.com", "title": "Example"}],
            "green_rationale": "Green reasoning",
            "red_objections": [{"objection": "Risk X", "resolution": "Mitigate Y"}],
            "consensus_note": "All three agents agreed",
            "tags": ["optimization", "ctr"],
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:00:00Z",
            "verified_at": None,
            "invalidated_at": None,
        }
        cursor = make_mock_cursor(fetchone_result=wiki_row)
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        result = adapter.create_wiki_entry({
            "title": "Ad CTR Optimization",
            "slug": "ad-ctr-optimization-abc123",
            "content": "Full content...",
            "sources": [{"url": "https://example.com", "title": "Example"}],
            "green_rationale": "Green reasoning",
            "red_objections": [{"objection": "Risk X", "resolution": "Mitigate Y"}],
            "consensus_note": "All three agents agreed",
            "tags": ["optimization", "ctr"],
        })
        assert result["title"] == "Ad CTR Optimization"
        assert result["green_rationale"] == "Green reasoning"
        cursor.execute.assert_called()
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)


# ──────────────────────────────────────────────────────────────────────────────
# Debate state tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPostgresAdapterDebate(TestAdapterWithMock):

    @classmethod
    def setup_class(cls):
        state_row = {
            "id": 1,
            "cycle_date": "2026-04-06",
            "campaign_id": "123e4567-e89b-12d3-a456-426614174000",
            "phase": "green_proposes",
            "round_number": 2,
            "green_proposals": [{"type": "keyword_add", "keyword": "shoes"}],
            "red_objections": [],
            "coordinator_decision": None,
            "consensus_reached": False,
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:00:00Z",
        }
        cls._mock_cursor = make_mock_cursor(fetchone_result=state_row)
        super().setup_class()

    def test_save_debate_state_saves_all_fields(self):
        """save_debate_state must persist phase, round, proposals, objections."""
        adapter = self.make_adapter()
        from uuid import UUID
        result = adapter.save_debate_state({
            "cycle_date": "2026-04-06",
            "campaign_id": UUID("123e4567-e89b-12d3-a456-426614174000"),
            "phase": "green_proposes",
            "round_number": 2,
            "green_proposals": [{"type": "keyword_add", "keyword": "shoes"}],
            "red_objections": [],
            "consensus_reached": False,
        })
        assert result["round_number"] == 2
        assert result["phase"] == "green_proposes"

    def test_save_debate_state_uses_upsert(self):
        """save_debate_state must use ON CONFLICT DO UPDATE (upsert) to avoid duplicates."""
        cursor = make_mock_cursor(fetchone_result={})
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        adapter.save_debate_state({
            "cycle_date": "2026-04-06",
            "campaign_id": UUID("123e4567-e89b-12d3-a456-426614174000"),
            "phase": "idle",
            "round_number": 1,
            "green_proposals": [],
            "red_objections": [],
            "consensus_reached": False,
        })
        call_args = cursor.execute.call_args
        sql_query = call_args[0][0]
        assert "ON CONFLICT" in sql_query, \
            "save_debate_state must use ON CONFLICT for upsert"
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)


# ──────────────────────────────────────────────────────────────────────────────
# Webhook tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPostgresAdapterWebhooks(TestAdapterWithMock):

    @classmethod
    def setup_class(cls):
        webhook_row = {
            "id": "webhook_001",
            "url": "https://example.com/hook",
            "events": ["consensus_reached", "action_executed"],
            "secret": "hmac_secret_123",
            "active": True,
            "created_at": "2026-04-06T10:00:00Z",
        }
        cls._mock_cursor = make_mock_cursor(fetchone_result=webhook_row)
        super().setup_class()

    def test_register_webhook_returns_webhook(self):
        """register_webhook must persist URL, events, and secret."""
        adapter = self.make_adapter()
        result = adapter.register_webhook({
            "url": "https://example.com/hook",
            "events": ["consensus_reached", "action_executed"],
            "secret": "hmac_secret_123",
        })
        assert result["url"] == "https://example.com/hook"
        assert "consensus_reached" in result["events"]


# ──────────────────────────────────────────────────────────────────────────────
# HITL proposal operation tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPostgresAdapterHitlProposals(TestAdapterWithMock):

    @classmethod
    def setup_class(cls):
        proposal_row = {
            "id": "proposal_001",
            "campaign_id": "123e4567-e89b-12d3-a456-426614174000",
            "proposal_type": "keyword_add",
            "impact_summary": "Add 10 keywords",
            "reasoning": "Green analysis shows opportunity",
            "status": "pending",
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T10:00:00Z",
            "decided_at": None,
            "replier_response": None,
        }
        cls._mock_cursor = make_mock_cursor(fetchone_result=proposal_row, fetchall_result=[proposal_row])
        super().setup_class()

    def test_list_hitl_proposals_returns_proposals(self):
        """list_hitl_proposals returns proposals for a campaign ordered by created_at DESC."""
        adapter = self.make_adapter()
        from uuid import UUID
        result = adapter.list_hitl_proposals(UUID("123e4567-e89b-12d3-a456-426614174000"))
        assert isinstance(result, list)
        assert len(result) == 1
        call_args = self._mock_cursor.execute.call_args
        assert "ORDER BY created_at DESC" in call_args[0][0]

    def test_list_hitl_proposals_filters_by_status(self):
        """list_hitl_proposals with status filter includes status in WHERE clause."""
        cursor = make_mock_cursor(fetchall_result=[])
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        adapter.list_hitl_proposals(UUID("123e4567-e89b-12d3-a456-426614174000"), status="pending")
        call_args = cursor.execute.call_args
        sql_query = call_args[0][0]
        assert "status = %s" in sql_query, "Must filter by status when provided"
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_update_hitl_proposal_status_returns_updated_row(self):
        """update_hitl_proposal_status updates status, replier_response, decided_at and returns row."""
        cursor = make_mock_cursor(fetchone_result={
            "id": "proposal_001",
            "status": "approved",
            "replier_response": "LGTM",
            "decided_at": "2026-04-06T12:00:00Z",
        })
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.update_hitl_proposal_status(
            UUID("00000000-0000-0000-0000-000000000001"),
            status="approved",
            replier_response="LGTM",
        )
        assert result["status"] == "approved"
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "UPDATE hitl_proposals" in call_args[0][0] and "status = %s" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_update_hitl_proposal_status_returns_empty_dict_when_not_found(self):
        """update_hitl_proposal_status returns empty dict when no row matches."""
        cursor = make_mock_cursor(fetchone_result=None)
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.update_hitl_proposal_status(
            UUID("00000000-0000-0000-0000-000000000999"),
            status="approved",
        )
        assert result == {}
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_create_hitl_proposal_inserts_and_returns(self):
        """create_hitl_proposal inserts a row and returns it."""
        cursor = make_mock_cursor(fetchone_result={
            "id": "proposal_new",
            "campaign_id": "123e4567-e89b-12d3-a456-426614174000",
            "proposal_type": "keyword_add",
            "impact_summary": "Add keywords",
            "reasoning": "Test reasoning",
            "status": "pending",
        })
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.create_hitl_proposal({
            "campaign_id": UUID("123e4567-e89b-12d3-a456-426614174000"),
            "proposal_type": "keyword_add",
            "impact_summary": "Add keywords",
            "reasoning": "Test reasoning",
        })
        assert result is not None
        assert result["proposal_type"] == "keyword_add"
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "INSERT INTO hitl_proposals" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_get_hitl_proposal_returns_proposal(self):
        """get_hitl_proposal returns a proposal dict when found."""
        adapter = self.make_adapter()
        from uuid import UUID
        result = adapter.get_hitl_proposal(UUID("00000000-0000-0000-0000-000000000001"))
        assert result is not None
        assert result["proposal_type"] == "keyword_add"
        self._mock_cursor.execute.assert_called()
        call_args = self._mock_cursor.execute.call_args
        assert "SELECT * FROM hitl_proposals WHERE id = %s" in call_args[0][0]

    def test_get_hitl_proposal_returns_none_when_not_found(self):
        """get_hitl_proposal returns None when no proposal exists."""
        cursor = make_mock_cursor(fetchone_result=None)
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.get_hitl_proposal(UUID("00000000-0000-0000-0000-000000000999"))
        assert result is None
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)


class TestPostgresAdapterWikiEntryOps(TestAdapterWithMock):
    """Tests for wiki entry read/invalidate operations."""

    @classmethod
    def setup_class(cls):
        cls._mock_cursor = make_mock_cursor(fetchone_result={"id": "e1", "title": "Test"})
        super().setup_class()

    def test_get_wiki_entry_returns_entry(self):
        """get_wiki_entry fetches a specific wiki entry by ID."""
        cursor = make_mock_cursor(fetchone_result={"id": "e1", "title": "Test"})
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.get_wiki_entry(UUID("123e4567-e89b-12d3-a456-426614174000"))
        assert result is not None
        assert result["title"] == "Test"
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "wiki_entries" in call_args[0][0]
        assert "WHERE id = %s" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_invalidate_wiki_entry_calls_execute(self):
        """invalidate_wiki_entry executes UPDATE with invalidated_at and reason."""
        cursor = make_mock_cursor()
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        adapter.invalidate_wiki_entry(UUID("123e4567-e89b-12d3-a456-426614174000"), "outdated")
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "UPDATE wiki_entries" in call_args[0][0]
        assert "invalidated_at" in call_args[0][0]
        assert "invalidation_reason" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)


class TestPostgresAdapterDebateReadOps(TestAdapterWithMock):
    """Tests for debate state read operations."""

    @classmethod
    def setup_class(cls):
        cls._mock_cursor = make_mock_cursor(fetchone_result={"id": "d1", "phase": "green_proposals"})
        super().setup_class()

    def test_get_latest_debate_state_returns_state(self):
        """get_latest_debate_state fetches state for a specific cycle."""
        cursor = make_mock_cursor(fetchone_result={"id": "d1", "phase": "green_proposals"})
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.get_latest_debate_state("2026-04-08", UUID("123e4567-e89b-12d3-a456-426614174000"))
        assert result is not None
        assert result["phase"] == "green_proposals"
        call_args = cursor.execute.call_args
        assert "cycle_date" in call_args[0][0]
        assert "ORDER BY id DESC LIMIT 1" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_get_latest_debate_state_any_cycle_returns_state(self):
        """get_latest_debate_state_any_cycle fetches most recent state regardless of cycle."""
        cursor = make_mock_cursor(fetchone_result={"id": "d2", "phase": "red_review"})
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.get_latest_debate_state_any_cycle(UUID("123e4567-e89b-12d3-a456-426614174000"))
        assert result is not None
        assert result["phase"] == "red_review"
        call_args = cursor.execute.call_args
        assert "campaign_id" in call_args[0][0]
        assert "ORDER BY id DESC LIMIT 1" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)


class TestPostgresAdapterAuditLog(TestAdapterWithMock):
    """Tests for audit log operations."""

    @classmethod
    def setup_class(cls):
        cls._mock_cursor = make_mock_cursor(fetchone_result={"id": "a1", "action_type": "proposal_approved"})
        super().setup_class()

    def test_write_audit_log_inserts_and_returns(self):
        """write_audit_log executes INSERT RETURNING and returns the row."""
        cursor = make_mock_cursor(fetchone_result={"id": "a1", "action_type": "proposal_approved"})
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.write_audit_log({
            "cycle_date": "2026-04-08",
            "campaign_id": UUID("123e4567-e89b-12d3-a456-426614174000"),
            "action_type": "proposal_approved",
        })
        assert result is not None
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "INSERT INTO audit_log" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_query_audit_log_filters_by_all_params(self):
        """query_audit_log builds a dynamic WHERE clause from provided filters."""
        cursor = make_mock_cursor(fetchall_result=[])
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        adapter.query_audit_log(
            campaign_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            action_type="proposal_approved",
            cycle_date="2026-04-08",
            limit=50,
        )
        call_args = cursor.execute.call_args
        sql_query = call_args[0][0]
        assert "campaign_id = %s" in sql_query
        assert "action_type = %s" in sql_query
        assert "cycle_date = %s" in sql_query
        assert "AND" in sql_query
        assert call_args[0][1] == ("123e4567-e89b-12d3-a456-426614174000", "proposal_approved", "2026-04-08", 50)
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_query_audit_log_falls_back_to_no_conditions(self):
        """query_audit_log uses '1=1' when no filters are provided."""
        cursor = make_mock_cursor(fetchall_result=[])
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        adapter.query_audit_log()
        call_args = cursor.execute.call_args
        sql_query = call_args[0][0]
        assert "1=1" in sql_query
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)


class TestPostgresAdapterWebhookOps(TestAdapterWithMock):
    """Tests for additional webhook operations."""

    @classmethod
    def setup_class(cls):
        cls._mock_cursor = make_mock_cursor(fetchone_result={"id": "w1", "url": "https://example.com/webhook"})
        super().setup_class()

    def test_register_webhook_inserts_and_returns(self):
        """register_webhook executes INSERT RETURNING and returns the webhook."""
        cursor = make_mock_cursor(fetchone_result={"id": "w1", "url": "https://example.com/webhook"})
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        result = adapter.register_webhook({
            "url": "https://example.com/webhook",
            "events": ["hitl_proposal_approved"],
            "secret": "secret123",
        })
        assert result is not None
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "INSERT INTO webhook_subscriptions" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_list_webhooks_returns_active_only(self):
        """list_webhooks only returns active webhook subscriptions."""
        cursor = make_mock_cursor(fetchall_result=[{"id": "w1", "active": True}])
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        result = adapter.list_webhooks()
        assert isinstance(result, list)
        call_args = cursor.execute.call_args
        assert "webhook_subscriptions" in call_args[0][0]
        assert "active = TRUE" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_delete_webhook_calls_execute(self):
        """delete_webhook executes DELETE FROM webhook_subscriptions."""
        cursor = make_mock_cursor()
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        adapter.delete_webhook(UUID("123e4567-e89b-12d3-a456-426614174000"))
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "DELETE FROM webhook_subscriptions" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)

    def test_write_webhook_delivery_log_inserts_and_returns(self):
        """write_webhook_delivery_log persists delivery attempt to webhook_delivery_log."""
        cursor = make_mock_cursor(fetchone_result={
            "id": "log_1",
            "subscription_id": "sub_1",
            "event": "hitl_proposal_approved",
            "status": "delivered",
        })
        mock_conn = make_mock_connection(cursor)
        import psycopg2
        psycopg2.connect = MagicMock(return_value=mock_conn)
        import src.db.postgres_adapter as pa_module
        importlib.reload(pa_module)
        adapter = pa_module.PostgresAdapter("postgresql://fake")
        from uuid import UUID
        result = adapter.write_webhook_delivery_log({
            "subscription_id": UUID("123e4567-e89b-12d3-a456-426614174000"),
            "event": "hitl_proposal_approved",
            "payload": {"proposal_id": "p1"},
            "status": "delivered",
            "attempts": 1,
        })
        assert result is not None
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "INSERT INTO webhook_delivery_log" in call_args[0][0]
        # Restore class mock
        mock_conn_class = make_mock_connection(self._mock_cursor)
        psycopg2.connect = MagicMock(return_value=mock_conn_class)
        importlib.reload(pa_module)
