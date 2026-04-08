"""
RED: Tests for PATCH /campaigns/{uuid} — update campaign mutable fields.

This endpoint is completely untested. It updates hitl_enabled, owner_email,
and hitl_threshold on a campaign.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def make_campaign_row(campaign_id: str | None = None) -> dict:
    cid = campaign_id or str(uuid.uuid4())
    return {
        "id": cid,
        "campaign_id": "cmp_001",
        "customer_id": "cust_001",
        "name": "Test Campaign",
        "status": "active",
        "campaign_type": "search",
        "owner_tag": None,
        "api_key_token": "token",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "last_synced_at": None,
        "last_reviewed_at": None,
        "hitl_enabled": False,
        "owner_email": None,
        "hitl_threshold": "budget>20pct,keyword_add>5",
    }


@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    # Use monkeypatch to patch _adapter directly — this is tracked and restored
    monkeypatch.setattr("src.api.routes.campaigns._adapter", lambda: mock)
    return mock


class TestUpdateCampaign:
    """PATCH /campaigns/{campaign_id} — update mutable campaign fields."""

    def test_update_hitl_enabled_to_true(self, mock_adapter):
        """
        PATCH with hitl_enabled=true should update the campaign.
        The endpoint executes an UPDATE query and returns the updated row.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row(str(campaign_uuid))
        updated_row = {**campaign_row, "hitl_enabled": True}

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.execute.return_value = None
        mock_adapter.get_campaign.return_value = updated_row  # second call returns updated

        app = FastAPI()
        app.include_router(
            __import__("src.api.routes.campaigns", fromlist=["router"]).router
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.patch(
            f"/campaigns/{campaign_uuid}",
            json={"hitl_enabled": True},
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["hitl_enabled"] is True

    def test_update_owner_email(self, mock_adapter):
        """
        PATCH with owner_email should update the campaign's owner email.
        This is how operators configure HITL email delivery.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row(str(campaign_uuid))
        updated_row = {**campaign_row, "owner_email": "owner@example.com"}

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.execute.return_value = None
        mock_adapter.get_campaign.return_value = updated_row

        app = FastAPI()
        app.include_router(
            __import__("src.api.routes.campaigns", fromlist=["router"]).router
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.patch(
            f"/campaigns/{campaign_uuid}",
            json={"owner_email": "owner@example.com"},
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["owner_email"] == "owner@example.com"

    def test_update_hitl_threshold(self, mock_adapter):
        """
        PATCH with hitl_threshold should update the threshold string.
        This is the only test that exercises the hitl_threshold field in PATCH.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row(str(campaign_uuid))
        updated_row = {**campaign_row, "hitl_threshold": "budget>10pct,keyword_add>3"}

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.execute.return_value = None
        mock_adapter.get_campaign.return_value = updated_row

        app = FastAPI()
        app.include_router(
            __import__("src.api.routes.campaigns", fromlist=["router"]).router
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.patch(
            f"/campaigns/{campaign_uuid}",
            json={"hitl_threshold": "budget>10pct,keyword_add>3"},
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["hitl_threshold"] == "budget>10pct,keyword_add>3"

    def test_update_campaign_not_found_returns_404(self, mock_adapter):
        """
        PATCH to a non-existent campaign UUID must return 404.
        """
        campaign_uuid = uuid.uuid4()
        mock_adapter.get_campaign.return_value = None

        app = FastAPI()
        app.include_router(
            __import__("src.api.routes.campaigns", fromlist=["router"]).router
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.patch(
            f"/campaigns/{campaign_uuid}",
            json={"hitl_enabled": True},
        )

        assert response.status_code == 404

    def test_update_with_no_fields_returns_current(self, mock_adapter):
        """
        PATCH with an empty body ({}) should return the current campaign
        without executing any DB update.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row(str(campaign_uuid))

        mock_adapter.get_campaign.return_value = campaign_row

        app = FastAPI()
        app.include_router(
            __import__("src.api.routes.campaigns", fromlist=["router"]).router
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.patch(
            f"/campaigns/{campaign_uuid}",
            json={},
        )

        assert response.status_code == 200
        # execute() should NOT have been called since there were no updates
        mock_adapter.execute.assert_not_called()

    def test_update_requires_auth(self, mock_adapter):
        """
        Without X-API-Key header, PATCH must return 401.
        """
        from src.main import create_app

        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row(str(campaign_uuid))
        mock_adapter.get_campaign.return_value = campaign_row

        with patch("src.api.middleware.get_admin_api_key", return_value="test-key"):
            app = create_app()
            client = TestClient(app, raise_server_exceptions=False)
            # No X-API-Key header
            response = client.patch(
                f"/campaigns/{campaign_uuid}",
                json={"hitl_enabled": True},
            )
            assert response.status_code == 401
