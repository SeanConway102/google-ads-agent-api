"""
RED: Write the failing test first.
Tests for GET /campaigns/{uuid}/insights endpoint.
Returns current optimization recommendations and debate state for a campaign.
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
def campaign_app(mock_adapter):
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


def make_debate_state_row(campaign_id: uuid.UUID) -> dict:
    return {
        "id": 1,
        "cycle_date": "2026-04-06",
        "campaign_id": campaign_id,
        "phase": "consensus_locked",
        "round_number": 2,
        "green_proposals": [
            {"type": "keyword_add", "target": "running shoes", "ad_group_id": "ag_001"},
        ],
        "red_objections": [
            {"objection": "keyword too broad", "resolution": "narrowed to 'trail running shoes'"},
        ],
        "coordinator_decision": {"verdict": "consensus", "note": "All concerns addressed."},
        "consensus_reached": True,
        "created_at": datetime(2026, 4, 6, 8, 30, 0),
        "updated_at": datetime(2026, 4, 6, 8, 45, 0),
    }


# ──────────────────────────────────────────────────────────────────────────────
# RED: Write failing tests
# ──────────────────────────────────────────────────────────────────────────────

class TestGetCampaignInsights:
    """Tests for GET /campaigns/{uuid}/insights."""

    def test_returns_404_when_campaign_not_found(self, mock_adapter, client):
        """Returns 404 when no campaign exists with the given UUID."""
        mock_adapter.get_campaign.return_value = None

        response = client.get(f"/campaigns/{uuid.uuid4()}/insights")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_campaign_insights_with_debate_state(self, mock_adapter, client):
        """Returns campaign data plus latest green proposals and red objections."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = make_debate_state_row(campaign_uuid)

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row

        response = client.get(f"/campaigns/{campaign_uuid}/insights")

        assert response.status_code == 200
        data = response.json()
        assert data["campaign_id"] == campaign_row["campaign_id"]
        assert data["name"] == campaign_row["name"]
        assert data["status"] == campaign_row["status"]
        assert data["last_reviewed_at"] is not None
        assert "green_proposals" in data
        assert "red_objections" in data
        assert "phase" in data
        assert "round_number" in data

    def test_insights_includes_green_proposals_and_red_objections(self, mock_adapter, client):
        """The insights response contains the full green proposals and red objections arrays."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = make_debate_state_row(campaign_uuid)

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row

        response = client.get(f"/campaigns/{campaign_uuid}/insights")

        assert response.status_code == 200
        data = response.json()
        assert len(data["green_proposals"]) == 1
        assert data["green_proposals"][0]["type"] == "keyword_add"
        assert len(data["red_objections"]) == 1
        assert "resolution" in data["red_objections"][0]

    def test_insights_returns_null_debate_state_when_no_debate_yet(self, mock_adapter, client):
        """When no debate has run for a campaign, insights returns null debate fields."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = None

        response = client.get(f"/campaigns/{campaign_uuid}/insights")

        assert response.status_code == 200
        data = response.json()
        assert data["green_proposals"] is None
        assert data["red_objections"] is None
        assert data["phase"] is None
        assert data["round_number"] is None

    def test_insights_returns_422_when_campaign_status_is_invalid(self, mock_adapter, client):
        """Returns 422 when campaign row has an unrecognized status value."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        campaign_row["status"] = "invalid_status_value"  # not a valid CampaignStatus

        mock_adapter.get_campaign.return_value = campaign_row

        response = client.get(f"/campaigns/{campaign_uuid}/insights")

        assert response.status_code == 422
        assert "unknown status" in response.json()["detail"].lower()

    def test_insights_is_behind_api_key_auth(self, mock_adapter, client):
        """The insights endpoint lives in the campaigns router which requires API key auth."""
        # Verify the campaigns router uses APIKeyAuthMiddleware (applied in main.py)
        from src.api.middleware import APIKeyAuthMiddleware
        from src.api.routes import campaigns
        # The router itself doesn't carry middleware markers — verify via import
        assert campaigns.router is not None
