"""
RED: Tests for campaign lifecycle webhook events.
Campaigns should fire campaign_created and campaign_deleted webhooks
when those events occur.

This is a known gap: POST /campaigns and DELETE /campaigns do NOT dispatch
webhooks, even though the event types exist in AuditAction and are documented
in the README.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def mock_settings(monkeypatch):
    """Override Settings so get_admin_api_key() returns a test value."""
    mock = MagicMock()
    mock.ADMIN_API_KEY = "test-secret"
    monkeypatch.setattr("src.config.Settings", lambda: mock)


@pytest.fixture
def client(mock_settings):
    """Test client with Settings patched."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-secret"}


class TestCampaignLifecycleWebhooks:
    """Campaign lifecycle events should dispatch webhooks to registered consumers."""

    def _make_campaign_row(self) -> dict:
        return {
            "id": uuid.uuid4(),
            "campaign_id": "cmp_new_001",
            "customer_id": "cust_new",
            "name": "New Test Campaign",
            "status": "active",
            "campaign_type": "search",
            "owner_tag": "marketing",
            "api_key_token": "tok_abc123",
            "created_at": datetime.now(),
            "last_synced_at": None,
            "last_reviewed_at": None,
            "hitl_enabled": False,
            "owner_email": None,
            "hitl_threshold": None,
        }

    def test_post_campaign_dispatches_campaign_created_webhook(self, client, auth_headers):
        """
        POST /campaigns should dispatch campaign_created webhook.
        The webhook should fire after the campaign is successfully created,
        so registered consumers know a new campaign is under management.
        """
        mock_adapter = MagicMock()
        created_row = self._make_campaign_row()
        mock_adapter.create_campaign.return_value = created_row

        with patch("src.api.routes.campaigns._adapter", return_value=mock_adapter), \
             patch("src.services.webhook_service.WebhookService.dispatch") as mock_dispatch:

            response = client.post(
                "/campaigns",
                json={
                    "campaign_id": "cmp_new_001",
                    "customer_id": "cust_new",
                    "name": "New Test Campaign",
                    "api_key_token": "tok_abc123",
                    "campaign_type": "search",
                    "owner_tag": "marketing",
                },
                headers=auth_headers,
            )

            assert response.status_code == 201

            # Verify campaign_created webhook was dispatched
            dispatch_calls = mock_dispatch.call_args_list
            campaign_created_calls = [
                c for c in dispatch_calls
                if c[0][0] == "campaign_created"
            ]
            assert len(campaign_created_calls) == 1, (
                f"Expected campaign_created webhook to be dispatched once, "
                f"but got {[c[0][0] for c in dispatch_calls]}. "
                f"POST /campaigns should fire campaign_created event."
            )

            payload = campaign_created_calls[0][0][1]
            assert "campaign_id" in payload or "id" in payload

    def test_delete_campaign_dispatches_campaign_deleted_webhook(self, client, auth_headers):
        """
        DELETE /campaigns/{id} should dispatch campaign_deleted webhook.
        The webhook should fire after the campaign is deleted from management.
        """
        campaign_id = uuid.uuid4()
        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = self._make_campaign_row()
        mock_adapter.get_campaign.return_value["id"] = campaign_id

        with patch("src.api.routes.campaigns._adapter", return_value=mock_adapter), \
             patch("src.services.webhook_service.WebhookService.dispatch") as mock_dispatch:

            response = client.delete(
                f"/campaigns/{campaign_id}",
                headers=auth_headers,
            )

            assert response.status_code == 204

            # Verify campaign_deleted webhook was dispatched
            dispatch_calls = mock_dispatch.call_args_list
            campaign_deleted_calls = [
                c for c in dispatch_calls
                if c[0][0] == "campaign_deleted"
            ]
            assert len(campaign_deleted_calls) == 1, (
                f"Expected campaign_deleted webhook to be dispatched once, "
                f"but got {[c[0][0] for c in dispatch_calls]}. "
                f"DELETE /campaigns should fire campaign_deleted event."
            )