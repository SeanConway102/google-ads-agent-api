"""
RED: SqliteAdapter must implement every method in DatabaseAdapter.
Tests that the interface is fully implemented, basic CRUD works,
and PostgreSQL-specific SQL is translated to SQLite-compatible equivalents.
"""
from uuid import uuid4

import pytest

from src.db.base import DatabaseAdapter


class TestSqliteAdapterInterface:
    """SqliteAdapter must provide every method declared in DatabaseAdapter."""

    def test_class_exists(self):
        """SqliteAdapter must be importable from src.db.sqlite_adapter."""
        from src.db.sqlite_adapter import SqliteAdapter

        assert SqliteAdapter is not None

    def test_inherits_from_database_adapter(self):
        """SqliteAdapter must be a subclass of DatabaseAdapter."""
        from src.db.sqlite_adapter import SqliteAdapter

        assert issubclass(SqliteAdapter, DatabaseAdapter)

    def test_all_interface_methods_present(self):
        """SqliteAdapter must declare all methods from DatabaseAdapter."""
        from src.db.sqlite_adapter import SqliteAdapter

        required_methods = [
            # Base operations
            "fetch_one", "fetch_all", "execute", "execute_returning",
            # Campaign operations
            "create_campaign", "get_campaign", "get_campaign_by_owner_email",
            "list_campaigns", "delete_campaign",
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
        ]
        for method in required_methods:
            assert hasattr(SqliteAdapter, method), \
                f"SqliteAdapter must define method: {method}"

    def test_is_abstract_free(self):
        """SqliteAdapter must NOT be abstract — it is a concrete implementation."""
        from src.db.sqlite_adapter import SqliteAdapter

        # Should be instantiable without TypeError
        adapter = SqliteAdapter(":memory:")
        assert adapter is not None


class TestSqliteAdapterCannotBeInstantiated:
    """SqliteAdapter must implement ALL DatabaseAdapter methods before it is considered complete."""

    def test_fetch_one_is_implemented(self):
        """fetch_one must have a body, not just 'pass'."""
        from src.db.sqlite_adapter import SqliteAdapter
        import inspect

        method = getattr(SqliteAdapter, "fetch_one", None)
        assert method is not None
        src = inspect.getsource(method)
        assert "pass" not in src or "NotImplementedError" in src or len(src.splitlines()) > 4, \
            "fetch_one appears to be a stub (only 'pass')"


# ─── Functional tests — use a real temp SQLite file ──────────────────────

class TestSqliteAdapterFunctional:
    """Functional tests against a real in-memory SQLite database."""

    @pytest.fixture
    def adapter(self):
        """Create an adapter backed by an in-memory SQLite database."""
        from src.db.sqlite_adapter import SqliteAdapter

        # Use :memory: — each fixture gets its own in-memory DB
        adapter = SqliteAdapter(":memory:")
        adapter.init_schema()
        return adapter

    # ─── Campaign CRUD ───────────────────────────────────────────────────────

    def test_create_campaign_returns_dict(self, adapter):
        """create_campaign must return a campaign dict with all expected fields."""
        result = adapter.create_campaign({
            "campaign_id": "cmp_test_001",
            "customer_id": "cust_001",
            "name": "Test Campaign",
            "api_key_token": "token_abc",
            "campaign_type": "search",
            "owner_tag": "marketing",
        })
        assert isinstance(result, dict)
        assert result["campaign_id"] == "cmp_test_001"
        assert result["name"] == "Test Campaign"
        assert result["status"] == "active"

    def test_get_campaign_returns_campaign(self, adapter):
        """get_campaign must return a campaign dict when found."""
        created = adapter.create_campaign({
            "campaign_id": "cmp_get_001",
            "customer_id": "cust_001",
            "name": "Get Test",
            "api_key_token": "token_xyz",
            "campaign_type": "search",
            "owner_tag": "marketing",
        })
        result = adapter.get_campaign(created["id"])
        assert result is not None
        assert result["campaign_id"] == "cmp_get_001"

    def test_get_campaign_returns_none_when_not_found(self, adapter):
        """get_campaign must return None when no campaign exists."""
        result = adapter.get_campaign(uuid4())
        assert result is None

    def test_list_campaigns_returns_list(self, adapter):
        """list_campaigns must return a list of campaign dicts."""
        adapter.create_campaign({
            "campaign_id": "cmp_list_001",
            "customer_id": "cust_001",
            "name": "List Test 1",
            "api_key_token": "token_abc",
            "campaign_type": "search",
            "owner_tag": "marketing",
        })
        result = adapter.list_campaigns()
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_delete_campaign_succeeds(self, adapter):
        """delete_campaign must not raise when given a valid UUID."""
        created = adapter.create_campaign({
            "campaign_id": "cmp_del_001",
            "customer_id": "cust_001",
            "name": "Delete Test",
            "api_key_token": "token_del",
            "campaign_type": "search",
            "owner_tag": "marketing",
        })
        adapter.delete_campaign(created["id"])
        # No exception = pass

    # ─── Wiki operations ─────────────────────────────────────────────────────

    def test_create_wiki_entry_returns_entry(self, adapter):
        """create_wiki_entry must store all fields and return the entry."""
        result = adapter.create_wiki_entry({
            "title": "CTR Optimization",
            "slug": "ctr-optimization-abc123",
            "content": "Full research content...",
            "sources": [{"url": "https://example.com", "title": "Example"}],
            "green_rationale": "Green reasoning here",
            "red_objections": [{"objection": "Risk X", "resolution": "Mitigate Y"}],
            "consensus_note": "All agents agreed",
            "tags": ["optimization", "ctr"],
        })
        assert result["title"] == "CTR Optimization"
        assert result["green_rationale"] == "Green reasoning here"
        assert result["slug"] == "ctr-optimization-abc123"

    def test_get_wiki_entry_returns_entry(self, adapter):
        """get_wiki_entry must return a wiki entry dict when found."""
        created = adapter.create_wiki_entry({
            "title": "Ad Copy Best Practices",
            "slug": "ad-copy-best-practices-def456",
            "content": "Content here...",
            "sources": [],
            "tags": ["ad-copy"],
        })
        result = adapter.get_wiki_entry(created["id"])
        assert result is not None
        assert result["title"] == "Ad Copy Best Practices"

    def test_invalidate_wiki_entry_sets_invalidated_at(self, adapter):
        """invalidate_wiki_entry must set invalidated_at, not delete the row."""
        created = adapter.create_wiki_entry({
            "title": "To Be Invalidated",
            "slug": "to-be-invalidated-ghi789",
            "content": "Content...",
            "sources": [],
            "tags": [],
        })
        adapter.invalidate_wiki_entry(created["id"], reason="Outdated research")
        result = adapter.get_wiki_entry(created["id"])
        assert result is not None
        assert result["invalidated_at"] is not None

    def test_search_wiki_returns_relevant_entries(self, adapter):
        """search_wiki must return wiki entries (uses LIKE on SQLite since tsvector is PostgreSQL-only)."""
        adapter.create_wiki_entry({
            "title": "Keyword Bidding Strategy",
            "slug": "keyword-bidding-strategy-jkl012",
            "content": "Content about keyword bidding...",
            "sources": [],
            "tags": ["bidding"],
        })
        results = adapter.search_wiki("keyword bidding")
        assert isinstance(results, list)
        assert len(results) >= 1

    # ─── Debate state ───────────────────────────────────────────────────────

    def test_save_debate_state_returns_state(self, adapter):
        """save_debate_state must persist state and return the row."""
        cid = uuid4()
        result = adapter.save_debate_state({
            "cycle_date": "2026-04-07",
            "campaign_id": cid,
            "phase": "green_proposes",
            "round_number": 1,
            "green_proposals": [{"type": "keyword_add", "keyword": "shoes"}],
            "red_objections": [],
            "consensus_reached": False,
        })
        assert result["phase"] == "green_proposes"
        assert result["round_number"] == 1

    def test_get_latest_debate_state_returns_state(self, adapter):
        """get_latest_debate_state must return debate state for a cycle."""
        cid = uuid4()
        adapter.save_debate_state({
            "cycle_date": "2026-04-07",
            "campaign_id": cid,
            "phase": "red_challenges",
            "round_number": 2,
            "green_proposals": [],
            "red_objections": [],
            "consensus_reached": False,
        })
        result = adapter.get_latest_debate_state("2026-04-07", cid)
        assert result is not None
        assert result["phase"] == "red_challenges"

    def test_save_debate_state_is_upsert(self, adapter):
        """save_debate_state must use INSERT ... ON CONFLICT DO UPDATE (upsert)."""
        cid = uuid4()
        adapter.save_debate_state({
            "cycle_date": "2026-04-07",
            "campaign_id": cid,
            "phase": "idle",
            "round_number": 1,
            "green_proposals": [],
            "red_objections": [],
            "consensus_reached": False,
        })
        # Update it
        adapter.save_debate_state({
            "cycle_date": "2026-04-07",
            "campaign_id": cid,
            "phase": "green_proposes",
            "round_number": 2,
            "green_proposals": [],
            "red_objections": [],
            "consensus_reached": False,
        })
        # Should still be ONE row (upsert, not duplicate)
        result = adapter.get_latest_debate_state("2026-04-07", cid)
        assert result["round_number"] == 2
        # Verify no duplicate rows were created
        all_rows = adapter.fetch_all(
            "SELECT * FROM debate_state WHERE cycle_date = ? AND campaign_id = ?",
            ("2026-04-07", str(cid)),
        )
        assert len(all_rows) == 1, "Upsert created duplicate rows instead of updating"

    # ─── Audit log ──────────────────────────────────────────────────────────

    def test_write_audit_log_returns_row(self, adapter):
        """write_audit_log must persist and return the audit row."""
        cid = uuid4()
        result = adapter.write_audit_log({
            "cycle_date": "2026-04-07",
            "campaign_id": cid,
            "action_type": "test_action",
            "target": {"foo": "bar"},
        })
        assert result["action_type"] == "test_action"
        assert result["id"] is not None

    def test_query_audit_log_returns_rows(self, adapter):
        """query_audit_log must return matching audit log rows."""
        cid = uuid4()
        adapter.write_audit_log({
            "cycle_date": "2026-04-07",
            "campaign_id": cid,
            "action_type": "test_query",
            "target": {},
        })
        results = adapter.query_audit_log(campaign_id=cid)
        assert isinstance(results, list)
        assert len(results) >= 1

    # ─── Webhooks ───────────────────────────────────────────────────────────

    def test_register_webhook_returns_webhook(self, adapter):
        """register_webhook must persist URL, events, secret and return the row."""
        result = adapter.register_webhook({
            "url": "https://example.com/hook",
            "events": ["consensus_reached"],
            "secret": "secret_abc",
        })
        assert result["url"] == "https://example.com/hook"
        assert "consensus_reached" in result["events"]

    def test_list_webhooks_returns_list(self, adapter):
        """list_webhooks must return all registered webhooks."""
        adapter.register_webhook({
            "url": "https://example.com/hook1",
            "events": ["consensus_reached"],
            "secret": "secret1",
        })
        results = adapter.list_webhooks()
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_delete_webhook_succeeds(self, adapter):
        """delete_webhook must not raise when given a valid UUID."""
        created = adapter.register_webhook({
            "url": "https://example.com/to_delete",
            "events": ["consensus_reached"],
            "secret": "secret_del",
        })
        adapter.delete_webhook(created["id"])
        # No exception = pass

    def test_write_webhook_delivery_log_returns_row(self, adapter):
        """write_webhook_delivery_log must persist and return the delivery log row."""
        webhook = adapter.register_webhook({
            "url": "https://example.com/hook",
            "events": ["consensus_reached"],
            "secret": "secret_xyz",
        })
        result = adapter.write_webhook_delivery_log({
            "subscription_id": webhook["id"],
            "event": "consensus_reached",
            "payload": {"test": "data"},
            "status": "pending",
        })
        assert result["event"] == "consensus_reached"
        assert result["status"] == "pending"

    # ─── HITL proposals ─────────────────────────────────────────────────────

    def test_create_hitl_proposal_returns_proposal(self, adapter):
        """create_hitl_proposal must persist and return the proposal row."""
        cid = uuid4()
        result = adapter.create_hitl_proposal({
            "campaign_id": cid,
            "proposal_type": "keyword_add",
            "impact_summary": "Add 3 keywords",
            "reasoning": "Low CPC, high volume",
        })
        assert result["proposal_type"] == "keyword_add"
        assert result["status"] == "pending"

    def test_list_hitl_proposals_returns_list(self, adapter):
        """list_hitl_proposals must return proposals for a campaign."""
        cid = uuid4()
        adapter.create_hitl_proposal({
            "campaign_id": cid,
            "proposal_type": "bid_update",
            "impact_summary": "Increase CPC",
            "reasoning": "Top impression share",
        })
        results = adapter.list_hitl_proposals(cid)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_update_hitl_proposal_status_updates_status(self, adapter):
        """update_hitl_proposal_status must update the proposal status."""
        cid = uuid4()
        proposal = adapter.create_hitl_proposal({
            "campaign_id": cid,
            "proposal_type": "keyword_add",
            "impact_summary": "Add keywords",
            "reasoning": "Good volume",
        })
        adapter.update_hitl_proposal_status(
            proposal_id=proposal["id"],
            status="approved",
        )
        updated = adapter.get_hitl_proposal(proposal["id"])
        assert updated["status"] == "approved"

    def test_get_hitl_proposal_returns_proposal(self, adapter):
        """get_hitl_proposal must return a proposal dict when found."""
        cid = uuid4()
        created = adapter.create_hitl_proposal({
            "campaign_id": cid,
            "proposal_type": "keyword_remove",
            "impact_summary": "Remove low performer",
            "reasoning": "High CPA",
        })
        result = adapter.get_hitl_proposal(created["id"])
        assert result is not None
        assert result["proposal_type"] == "keyword_remove"

    def test_get_hitl_proposal_returns_none_when_not_found(self, adapter):
        """get_hitl_proposal must return None when proposal does not exist."""
        result = adapter.get_hitl_proposal(uuid4())
        assert result is None
