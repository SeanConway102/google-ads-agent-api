"""
RED: Failing test for POST /research/trigger endpoint.
Tests manual research cycle trigger via API.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import campaigns, wiki


@pytest.fixture
def mock_adapter(monkeypatch):
    """Patch PostgresAdapter so tests don't need a real database."""
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.campaigns.PostgresAdapter", lambda: mock)
    monkeypatch.setattr("src.api.routes.wiki.PostgresAdapter", lambda: mock)
    monkeypatch.setattr("src.api.routes.research.PostgresAdapter", lambda: mock)
    monkeypatch.setattr("src.services.webhook_service.PostgresAdapter", lambda: mock)
    return mock


@pytest.fixture
def mock_settings(monkeypatch):
    """Override Settings so PostgresAdapter doesn't fail during request handling."""
    mock = MagicMock()
    mock.ADMIN_API_KEY = "test-key"
    mock.DATABASE_URL = "postgresql://test:test@localhost/test"
    mock.MAX_DEBATE_ROUNDS = 5
    monkeypatch.setattr("src.config.Settings", lambda: mock)
    monkeypatch.setattr("src.api.middleware.get_admin_api_key", lambda: "test-key")


@pytest.fixture
def client(mock_adapter, mock_settings):
    """Minimal FastAPI app with the routers under test."""
    from src.api.routes import research as research_router

    app = FastAPI()
    app.add_middleware(
        __import__("src.api.middleware", fromlist=["APIKeyAuthMiddleware"]).APIKeyAuthMiddleware
    )
    app.include_router(campaigns.router)
    app.include_router(wiki.router)
    app.include_router(research_router.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-key"}


def test_trigger_runs_all_campaigns(client, mock_adapter, auth_headers):
    """POST /research/trigger with no campaign_id runs all active campaigns."""
    cid = str(uuid.uuid4())
    mock_adapter.list_campaigns.return_value = [
        {
            "id": cid,
            "campaign_id": "123",
            "customer_id": "cust_001",
            "name": "Test Campaign",
            "api_key_token": "token",
            "status": "active",
        }
    ]

    with patch("src.api.routes.research.run_daily_research") as mock_run:
        response = client.post("/research/trigger", headers=auth_headers)
        assert response.status_code == 202
        payload = response.json()
        assert payload["status"] == "triggered"
        assert payload["campaign_id"] is None
        mock_run.assert_called_once()


def test_trigger_runs_single_campaign(client, mock_adapter, auth_headers):
    """POST /research/trigger with campaign_id runs only that campaign."""
    cid = str(uuid.uuid4())
    mock_adapter.list_campaigns.return_value = []
    mock_adapter.get_campaign.return_value = {
        "id": cid,
        "campaign_id": "123",
        "customer_id": "cust_001",
        "name": "Test Campaign",
        "api_key_token": "token",
        "status": "active",
    }

    with patch("src.api.routes.research.run_daily_research") as mock_run:
        response = client.post(
            f"/research/trigger?campaign_id={cid}",
            headers=auth_headers,
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["status"] == "triggered"
        assert payload["campaign_id"] == cid


def test_trigger_requires_auth(client):
    """POST /research/trigger without X-API-Key returns 401."""
    response = client.post("/research/trigger")
    assert response.status_code == 401


def test_trigger_returns_404_for_unknown_campaign(client, mock_adapter, auth_headers):
    """POST /research/trigger with non-existent campaign_id returns 404."""
    cid = str(uuid.uuid4())
    mock_adapter.list_campaigns.return_value = []
    mock_adapter.get_campaign.return_value = None

    response = client.post(
        f"/research/trigger?campaign_id={cid}",
        headers=auth_headers,
    )
    assert response.status_code == 404
