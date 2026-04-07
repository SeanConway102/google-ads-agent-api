"""
RED: Failing tests for campaign API end-to-end using full FastAPI app.
Uses TestClient with src.main:app, testing the full request stack.
"""
import uuid
import pytest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def mock_api_key(monkeypatch):
    """Patch get_admin_api_key to return test key, bypassing settings caching."""
    monkeypatch.setattr("src.api.middleware.get_admin_api_key", lambda: "test-secret-key")


@pytest.fixture
def mock_adapter(monkeypatch):
    """Patch _adapter in campaigns router to return a mock database."""
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.campaigns._adapter", lambda: mock)
    return mock


@pytest.fixture
def client(mock_api_key, mock_adapter):
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-secret-key"}


def test_create_campaign(client, auth_headers, mock_adapter):
    mock_adapter.create_campaign.return_value = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "campaign_id": "123",
        "customer_id": "456-789-0000",
        "name": "Test Campaign",
        "status": "active",
        "campaign_type": "search",
        "owner_tag": "marketing",
        "created_at": "2026-04-07T00:00:00Z",
        "last_synced_at": None,
        "last_reviewed_at": None,
    }

    response = client.post(
        "/campaigns",
        json={
            "campaign_id": "123",
            "customer_id": "456-789-0000",
            "name": "Test Campaign",
            "api_key_token": "token123",
            "campaign_type": "search",
            "owner_tag": "marketing",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["campaign_id"] == "123"


def test_create_campaign_missing_api_key(client):
    response = client.post(
        "/campaigns",
        json={"campaign_id": "123", "customer_id": "456-789-0000", "name": "Test"},
    )
    assert response.status_code == 401


def test_list_campaigns(client, auth_headers, mock_adapter):
    mock_adapter.list_campaigns.return_value = [
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "campaign_id": "1",
            "customer_id": "456-789-0000",
            "name": "Campaign One",
            "status": "active",
            "campaign_type": "search",
            "owner_tag": "marketing",
            "created_at": "2026-04-07T00:00:00Z",
            "last_synced_at": None,
            "last_reviewed_at": None,
        },
    ]

    response = client.get("/campaigns", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["campaigns"]) == 1


def test_delete_campaign(client, auth_headers, mock_adapter):
    campaign_uuid = "123e4567-e89b-12d3-a456-426614174000"

    response = client.delete(f"/campaigns/{campaign_uuid}", headers=auth_headers)

    assert response.status_code == 204
    mock_adapter.delete_campaign.assert_called_once_with(uuid.UUID(campaign_uuid))
