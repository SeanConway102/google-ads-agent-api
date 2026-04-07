"""
RED: Tests for PATCH /campaigns/{campaign_id} — HITL settings update.
Also tests _campaign_to_response edge cases.
"""
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestUpdateCampaign:
    """Test PATCH /campaigns/{campaign_id} for HITL settings."""

    def _make_client(self, mock_adapter):
        """Build a test client with mocked DB."""
        from src.api.middleware import APIKeyAuthMiddleware
        from src.api.routes import campaigns as campaigns_router

        from fastapi import FastAPI
        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)
        app.include_router(campaigns_router.router)

        client = TestClient(app)

        with patch("src.api.routes.campaigns._adapter", return_value=mock_adapter):
            yield client

    def test_patch_updates_hitl_enabled(self):
        """PATCH with hitl_enabled=true updates the campaign."""
        from src.main import create_app

        cid = str(uuid.uuid4())
        mock_adapter = MagicMock()
        mock_adapter.get_campaign.side_effect = [
            # First call: campaign exists
            {
                "id": cid, "campaign_id": "123", "customer_id": "cust",
                "name": "Test", "status": "active", "campaign_type": "search",
                "owner_tag": None, "api_key_token": "token", "created_at": "2026-01-01",
                "last_synced_at": None, "last_reviewed_at": None,
                "hitl_enabled": False, "owner_email": None, "hitl_threshold": None,
            },
            # Second call: after update
            {
                "id": cid, "campaign_id": "123", "customer_id": "cust",
                "name": "Test", "status": "active", "campaign_type": "search",
                "owner_tag": None, "api_key_token": "token", "created_at": "2026-01-01",
                "last_synced_at": None, "last_reviewed_at": None,
                "hitl_enabled": True, "owner_email": "a@b.com", "hitl_threshold": None,
            },
        ]

        with patch("src.api.routes.campaigns._adapter", return_value=mock_adapter), \
             patch("src.api.middleware.get_admin_api_key", return_value="test-key"):

            from fastapi.testclient import TestClient
            from src.main import create_app
            app = create_app()
            client = TestClient(app)

            response = client.patch(
                f"/campaigns/{cid}",
                json={"hitl_enabled": True, "owner_email": "a@b.com"},
                headers={"X-API-Key": "test-key"},
            )

            assert response.status_code == 200
            payload = response.json()
            assert payload["hitl_enabled"] is True
            assert payload["owner_email"] == "a@b.com"

    def test_patch_returns_404_for_nonexistent_campaign(self):
        """PATCH returns 404 when campaign does not exist."""
        from src.main import create_app

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = None

        with patch("src.api.routes.campaigns._adapter", return_value=mock_adapter), \
             patch("src.api.middleware.get_admin_api_key", return_value="test-key"):

            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)

            response = client.patch(
                f"/campaigns/{uuid.uuid4()}",
                json={"hitl_enabled": True},
                headers={"X-API-Key": "test-key"},
            )

            assert response.status_code == 404

    def test_patch_requires_auth(self):
        """PATCH without X-API-Key returns 401."""
        from src.main import create_app

        with patch("src.api.middleware.get_admin_api_key", return_value="test-key"):
            app = create_app()
            client = TestClient(app)

            response = client.patch(
                f"/campaigns/{uuid.uuid4()}",
                json={"hitl_enabled": True},
            )

            assert response.status_code == 401

    def test_patch_with_empty_body_returns_current_values(self):
        """PATCH with no fields updates nothing and returns current campaign."""
        from src.main import create_app

        cid = str(uuid.uuid4())
        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = {
            "id": cid, "campaign_id": "123", "customer_id": "cust",
            "name": "Test", "status": "active", "campaign_type": "search",
            "owner_tag": None, "api_key_token": "token", "created_at": "2026-01-01",
            "last_synced_at": None, "last_reviewed_at": None,
            "hitl_enabled": True, "owner_email": "a@b.com", "hitl_threshold": "budget>20pct",
        }

        with patch("src.api.routes.campaigns._adapter", return_value=mock_adapter), \
             patch("src.api.middleware.get_admin_api_key", return_value="test-key"):

            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)

            response = client.patch(
                f"/campaigns/{cid}",
                json={},
                headers={"X-API-Key": "test-key"},
            )

            assert response.status_code == 200
            # No UPDATE should have been called since no fields changed
            mock_adapter.execute.assert_not_called()


class TestCampaignToResponse:
    """Test _campaign_to_response helper."""

    def test_campaign_to_response_with_all_fields(self):
        """_campaign_to_response converts a full campaign dict."""
        from uuid import uuid4
        from src.api.routes.campaigns import _campaign_to_response

        row = {
            "id": str(uuid4()),
            "campaign_id": "123",
            "customer_id": "cust",
            "name": "Test Campaign",
            "status": "active",
            "campaign_type": "search",
            "owner_tag": "team-a",
            "api_key_token": "token",
            "created_at": "2026-01-01T00:00:00Z",
            "last_synced_at": "2026-04-01T00:00:00Z",
            "last_reviewed_at": None,
            "hitl_enabled": True,
            "owner_email": "a@b.com",
            "hitl_threshold": "budget>20pct",
        }

        result = _campaign_to_response(row)
        assert result.campaign_id == "123"
        assert result.name == "Test Campaign"
        assert result.hitl_enabled is True
        assert result.owner_email == "a@b.com"

    def test_campaign_to_response_with_missing_optional_fields(self):
        """_campaign_to_response handles None optional fields gracefully."""
        from uuid import uuid4
        from src.api.routes.campaigns import _campaign_to_response

        row = {
            "id": str(uuid4()),
            "campaign_id": "123",
            "customer_id": "cust",
            "name": "Test",
            "status": "active",
            "campaign_type": None,
            "owner_tag": None,
            "api_key_token": "token",
            "created_at": "2026-01-01T00:00:00Z",
            "last_synced_at": None,
            "last_reviewed_at": None,
            "hitl_enabled": None,
            "owner_email": None,
            "hitl_threshold": None,
        }

        result = _campaign_to_response(row)
        assert result.campaign_type is None
        assert result.hitl_enabled is None
