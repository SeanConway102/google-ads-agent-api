"""
RED: Failing tests for webhook API end-to-end using full FastAPI app.
"""
import uuid

import pytest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def mock_api_key(monkeypatch):
    monkeypatch.setattr("src.api.middleware.get_admin_api_key", lambda: "test-secret-key")


@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.webhooks._adapter", lambda: mock)
    return mock


@pytest.fixture
def client(mock_api_key, mock_adapter):
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-secret-key"}


def test_register_webhook(client, auth_headers, mock_adapter):
    webhook_id = uuid.uuid4()
    mock_adapter.register_webhook.return_value = {
        "id": webhook_id,
        "url": "https://example.com/hook",
        "events": ["consensus_reached"],
        "active": True,
        "created_at": "2026-04-07T10:00:00Z",
    }

    response = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "events": ["consensus_reached"]},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["url"] == "https://example.com/hook"


def test_register_webhook_requires_auth(client):
    response = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "events": ["consensus_reached"]},
    )
    assert response.status_code == 401


def test_list_webhooks(client, auth_headers, mock_adapter):
    webhook_id = uuid.uuid4()
    mock_adapter.list_webhooks.return_value = [
        {
            "id": webhook_id,
            "url": "https://example.com/hook",
            "events": ["consensus_reached"],
            "active": True,
            "created_at": "2026-04-07T10:00:00Z",
        },
    ]

    response = client.get("/webhooks", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["url"] == "https://example.com/hook"
