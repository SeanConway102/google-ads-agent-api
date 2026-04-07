"""
RED: Write the failing tests first.
Tests for POST /campaigns/{uuid}/approve (CM-006) and POST /campaigns/{uuid}/override (CM-007).
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.campaigns import router


# ──────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.campaigns.PostgresAdapter", lambda: mock)
    return mock


@pytest.fixture
def mock_guard_and_client(monkeypatch):
    """Mock CapabilityGuard.check() and GoogleAdsClient to avoid real API calls."""
    mock_guard = MagicMock()
    mock_guard.check.return_value = None  # allowed
    mock_gads = MagicMock()
    mock_gads.add_keywords.return_value = None

    def patched_guard():
        return mock_guard

    def patched_client(**_kwargs):
        return mock_gads

    monkeypatch.setattr("src.api.routes.campaigns.CapabilityGuard", patched_guard)
    monkeypatch.setattr("src.api.routes.campaigns.GoogleAdsClient", patched_client)
    return mock_guard, mock_gads


@pytest.fixture
def campaign_app(mock_adapter, mock_guard_and_client):
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(campaign_app):
    return TestClient(campaign_app, raise_server_exceptions=False)


# ──────────────────────────────────────────────────────────────────────────────
# Sample data
# ──────────────────────────────────────────────────────────────────────────────

def make_campaign_row(
    campaign_id: str = "12345",
    name: str = "Test Campaign",
    status: str = "active",
) -> dict:
    return {
        "id": uuid.uuid4(),
        "campaign_id": campaign_id,
        "customer_id": "cust_001",
        "name": name,
        "status": status,
        "campaign_type": "search",
        "owner_tag": "marketing",
        "created_at": datetime(2026, 4, 6, 10, 0, 0),
        "last_synced_at": datetime(2026, 4, 6, 8, 0, 0),
        "last_reviewed_at": datetime(2026, 4, 5, 8, 0, 0),
    }


# ──────────────────────────────────────────────────────────────────────────────
# RED: Failing tests for CM-006 — POST /campaigns/{uuid}/approve
# ──────────────────────────────────────────────────────────────────────────────

class TestApproveCampaignAction:
    """Tests for POST /campaigns/{uuid}/approve."""

    def test_approve_returns_404_when_campaign_not_found(self, mock_adapter, client):
        """Returns 404 when no campaign exists with the given UUID."""
        mock_adapter.get_campaign.return_value = None

        response = client.post(f"/campaigns/{uuid.uuid4()}/approve")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_approve_returns_404_when_no_pending_action(self, mock_adapter, client):
        """Returns 404 when the campaign has no pending action to approve."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = None

        response = client.post(f"/campaigns/{campaign_uuid}/approve")

        assert response.status_code == 404
        assert "pending" in response.json()["detail"].lower() or "no action" in response.json()["detail"].lower()

    def test_approve_returns_approved_status_and_campaign_id(self, mock_adapter, client):
        """Returns {status: approved, campaign_id: ...} on success."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-06",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 5,
            "green_proposals": [{"type": "keyword_add", "target": "shoes"}],
            "red_objections": [{"objection": "too risky"}],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        response = client.post(f"/campaigns/{campaign_uuid}/approve")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["campaign_id"] == str(campaign_uuid)
        mock_adapter.save_debate_state.assert_called_once()

    def test_approve_returns_approved_when_guard_denies_all_proposals(self, mock_adapter, client):
        """When CapabilityGuard denies all proposals, still returns approved (proposals skipped)."""
        from src.mcp.capability_guard import CapabilityDenied

        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-06",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 5,
            "green_proposals": [{"type": "keyword_add", "keywords": ["shoes"]}],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        # Guard denies the capability
        guard_mock = MagicMock()
        guard_mock.check.side_effect = CapabilityDenied("google_ads.add_keywords")

        def patched_guard():
            return guard_mock

        import src.api.routes.campaigns as campaigns_module
        original = campaigns_module.CapabilityGuard
        campaigns_module.CapabilityGuard = patched_guard
        try:
            response = client.post(f"/campaigns/{campaign_uuid}/approve")
            # Should still return 200 — denied proposals are skipped
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "approved"
        finally:
            campaigns_module.CapabilityGuard = original


# ──────────────────────────────────────────────────────────────────────────────
# RED: Failing tests for CM-007 — POST /campaigns/{uuid}/override
# ──────────────────────────────────────────────────────────────────────────────

class TestOverrideCampaignAction:
    """Tests for POST /campaigns/{uuid}/override."""

    def test_override_blocked_action_returns_403_via_real_guard(self, monkeypatch):
        """Actions blocked by the capability guard return 403 Forbidden."""
        # Uses the real CapabilityGuard so deny-by-default rules apply.
        # google_ads.campaign_delete matches the deny pattern google_ads.delete_*
        # so CapabilityDenied is raised and returns 403.
        mock = MagicMock()
        monkeypatch.setattr("src.api.routes.campaigns.PostgresAdapter", lambda: mock)

        app = FastAPI()
        app.include_router(router)
        test_client = TestClient(app, raise_server_exceptions=False)

        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        mock.get_campaign.return_value = campaign_row

        response = test_client.post(
            f"/campaigns/{campaign_uuid}/override",
            json={"action_type": "campaign_delete"},
        )

        assert response.status_code == 403
        assert "not allowed" in response.json()["detail"].lower() or "denied" in response.json()["detail"].lower()

    def test_override_returns_404_when_campaign_not_found(self, mock_adapter, client):
        """Returns 404 when no campaign exists with the given UUID."""
        mock_adapter.get_campaign.return_value = None

        response = client.post(
            f"/campaigns/{uuid.uuid4()}/override",
            json={"action_type": "keyword_add", "keywords": ["emergency keyword"]},
        )

        assert response.status_code == 404

    def test_override_requires_action_payload(self, mock_adapter, client):
        """Override requires an action payload in the request body."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        mock_adapter.get_campaign.return_value = campaign_row

        response = client.post(f"/campaigns/{campaign_uuid}/override", json={})

        assert response.status_code == 422  # validation error

    def test_override_logs_audit_with_manual_override_action_type(self, mock_adapter, client):
        """Override writes directly to audit_log with action_type manual_override."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.write_audit_log.return_value = {"id": 999}

        response = client.post(
            f"/campaigns/{campaign_uuid}/override",
            json={"action_type": "keyword_add", "keywords": ["emergency keyword"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "override_applied"
        assert data["audit_id"] == 999
        # Verify it wrote to audit_log (not debate_state)
        mock_adapter.write_audit_log.assert_called_once()
        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["action_type"] == "manual_override"
        # Should NOT invoke green/red debate
        mock_adapter.save_debate_state.assert_not_called()

    def test_override_does_not_invoke_green_red_debate(self, mock_adapter, client):
        """Override must NOT call save_debate_state (no adversarial debate)."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.write_audit_log.return_value = {"id": 1}

        response = client.post(
            f"/campaigns/{campaign_uuid}/override",
            json={"action_type": "keyword_add", "keywords": ["test"]},
        )

        assert response.status_code == 200
        mock_adapter.save_debate_state.assert_not_called()

    def test_override_returns_403_when_guard_denies_action(self, mock_adapter, client):
        """Override returns 403 when CapabilityGuard denies the action."""
        from src.mcp.capability_guard import CapabilityDenied

        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid

        mock_adapter.get_campaign.return_value = campaign_row

        # Make guard.check raise CapabilityDenied for google_ads.keyword_add
        guard_mock = MagicMock()
        guard_mock.check.side_effect = CapabilityDenied("google_ads.keyword_add")

        def patched_guard():
            return guard_mock

        import src.api.routes.campaigns as campaigns_module
        original = campaigns_module.CapabilityGuard
        campaigns_module.CapabilityGuard = patched_guard
        try:
            response = client.post(
                f"/campaigns/{campaign_uuid}/override",
                json={"action_type": "keyword_add", "keywords": ["emergency keyword"]},
            )
            assert response.status_code == 403
            data = response.json()
            assert "not allowed" in data["detail"].lower() or "denied" in data["detail"].lower()
        finally:
            campaigns_module.CapabilityGuard = original
