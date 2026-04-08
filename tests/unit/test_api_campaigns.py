"""
RED: Write the failing test first.
Tests for src/api/routes/campaigns.py — Campaign CRUD endpoints.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.campaigns import router


# ──────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_adapter(monkeypatch):
    """Patch PostgresAdapter so tests don't need a real database."""
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.campaigns.PostgresAdapter", lambda: mock)
    return mock


@pytest.fixture
def campaign_app(mock_adapter):
    """Minimal FastAPI app with just the campaigns router."""
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
    campaign_id: str = "cmp_001",
    name: str = "Test Campaign",
    status: str = "active",
) -> dict:
    return {
        "id": uuid.uuid4(),
        "campaign_id": campaign_id,
        "customer_id": "123-456-7890",
        "name": name,
        "status": status,
        "campaign_type": "search",
        "owner_tag": "marketing",
        "created_at": datetime(2026, 4, 6, 10, 0, 0),
        "last_synced_at": None,
        "last_reviewed_at": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# GET /campaigns tests
# ──────────────────────────────────────────────────────────────────────────────

class TestListCampaigns:

    def test_list_campaigns_returns_empty_list(self, client, mock_adapter):
        """GET /campaigns with no campaigns returns empty array."""
        mock_adapter.list_campaigns.return_value = []

        response = client.get("/campaigns")

        assert response.status_code == 200
        data = response.json()
        assert data["campaigns"] == []
        assert data["total"] == 0

    def test_list_campaigns_returns_campaigns(self, client, mock_adapter):
        """GET /campaigns returns all campaigns with correct total."""
        rows = [make_campaign_row("cmp_1"), make_campaign_row("cmp_2")]
        mock_adapter.list_campaigns.return_value = rows

        response = client.get("/campaigns")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["campaigns"]) == 2
        assert data["campaigns"][0]["campaign_id"] == "cmp_1"
        assert data["campaigns"][1]["campaign_id"] == "cmp_2"


# ──────────────────────────────────────────────────────────────────────────────
# POST /campaigns tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCreateCampaign:

    def test_create_campaign_returns_201(self, client, mock_adapter):
        """POST /campaigns with valid data returns 201 and the created campaign."""
        row = make_campaign_row()
        mock_adapter.create_campaign.return_value = row

        response = client.post(
            "/campaigns",
            json={
                "campaign_id": "cmp_new",
                "customer_id": "123-456-7890",
                "name": "New Campaign",
                "api_key_token": "tok_abc",
                "campaign_type": "search",
                "owner_tag": "marketing",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["campaign_id"] == "cmp_001"
        assert data["name"] == "Test Campaign"

    def test_create_campaign_conflict_returns_409(self, client, mock_adapter):
        """POST /campaigns with duplicate campaign_id returns 409."""
        mock_adapter.create_campaign.side_effect = Exception("UNIQUE constraint")

        response = client.post(
            "/campaigns",
            json={
                "campaign_id": "cmp_existing",
                "customer_id": "123-456-7890",
                "name": "Duplicate",
                "api_key_token": "tok_abc",
            },
        )

        assert response.status_code == 409
        assert "cmp_existing" in response.json()["detail"]

    def test_create_campaign_db_error_returns_500(self, client, mock_adapter):
        """POST /campaigns returns 500 on non-constraint DB errors."""
        mock_adapter.create_campaign.side_effect = Exception("connection timeout")

        response = client.post(
            "/campaigns",
            json={
                "campaign_id": "cmp_new",
                "customer_id": "123-456-7890",
                "name": "New Campaign",
                "api_key_token": "tok_abc",
            },
        )

        assert response.status_code == 500
        assert "Database error" in response.json()["detail"]

    def test_create_campaign_requires_fields(self, client):
        """POST /campaigns with missing required fields returns 422."""
        response = client.post("/campaigns", json={})
        assert response.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# GET /campaigns/{id} tests
# ──────────────────────────────────────────────────────────────────────────────

class TestGetCampaign:

    def test_get_campaign_returns_200(self, client, mock_adapter):
        """GET /campaigns/{id} with valid UUID returns the campaign."""
        campaign_id = uuid.uuid4()
        row = make_campaign_row()
        row["id"] = campaign_id
        mock_adapter.get_campaign.return_value = row

        response = client.get(f"/campaigns/{campaign_id}")

        assert response.status_code == 200
        assert response.json()["id"] == str(campaign_id)

    def test_get_campaign_not_found_returns_404(self, client, mock_adapter):
        """GET /campaigns/{id} with unknown UUID returns 404."""
        mock_adapter.get_campaign.return_value = None
        unknown_id = uuid.uuid4()

        response = client.get(f"/campaigns/{unknown_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Campaign not found"


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /campaigns/{id} tests
# ──────────────────────────────────────────────────────────────────────────────

class TestDeleteCampaign:

    def test_delete_campaign_returns_204(self, client, mock_adapter):
        """DELETE /campaigns/{id} returns 204 when campaign exists."""
        campaign_id = uuid.uuid4()
        row = make_campaign_row()
        row["id"] = campaign_id
        mock_adapter.get_campaign.return_value = row

        response = client.delete(f"/campaigns/{campaign_id}")

        assert response.status_code == 204
        mock_adapter.delete_campaign.assert_called_once()

    def test_get_campaign_returns_422_when_db_status_unknown(self, client, mock_adapter):
        """DB row with unknown status value raises 422 via _campaign_to_response."""
        campaign_id = uuid.uuid4()
        row = make_campaign_row()
        row["id"] = campaign_id
        row["status"] = "deleted"  # not a valid CampaignStatus value
        mock_adapter.get_campaign.return_value = row

        response = client.get(f"/campaigns/{campaign_id}")

        assert response.status_code == 422
        assert "unknown status" in response.json()["detail"]

    def test_get_campaign_returns_422_when_db_campaign_type_unknown(self, client, mock_adapter):
        """DB row with unknown campaign_type value raises 422 via _campaign_to_response."""
        campaign_id = uuid.uuid4()
        row = make_campaign_row()
        row["id"] = campaign_id
        row["status"] = "active"
        row["campaign_type"] = "disabled"  # not a valid CampaignType value
        mock_adapter.get_campaign.return_value = row

        response = client.get(f"/campaigns/{campaign_id}")

        assert response.status_code == 422
        assert "unknown campaign_type" in response.json()["detail"]

    def test_delete_campaign_not_found_returns_404(self, client, mock_adapter):
        """DELETE /campaigns/{id} returns 404 when campaign does not exist."""
        mock_adapter.get_campaign.return_value = None
        unknown_id = uuid.uuid4()

        response = client.delete(f"/campaigns/{unknown_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Campaign not found"
        mock_adapter.delete_campaign.assert_not_called()
