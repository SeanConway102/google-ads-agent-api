"""
RED: Write the failing test first.
Tests for src/api/routes/webhooks.py — Webhook registration and management.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.webhooks import router


@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.webhooks.PostgresAdapter", lambda: mock)
    return mock


@pytest.fixture
def webhooks_app(mock_adapter):
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(webhooks_app):
    return TestClient(webhooks_app, raise_server_exceptions=False)


def make_webhook_row(url: str = "https://example.com/webhook") -> dict:
    return {
        "id": uuid.uuid4(),
        "url": url,
        "events": ["consensus_reached"],
        "active": True,
        "created_at": datetime(2026, 4, 6, 10, 0, 0),
    }


class TestRegisterWebhook:

    def test_register_returns_201(self, client, mock_adapter):
        row = make_webhook_row()
        mock_adapter.register_webhook.return_value = row

        response = client.post(
            "/webhooks",
            json={
                "url": "https://example.com/webhook",
                "events": ["consensus_reached"],
                "secret": "hmac_secret",
            },
        )

        assert response.status_code == 201
        assert response.json()["url"] == "https://example.com/webhook"

    def test_register_requires_https_url(self, client):
        response = client.post(
            "/webhooks",
            json={"url": "http://example.com/webhook", "events": ["consensus_reached"]},
        )
        assert response.status_code == 422

    def test_register_accepts_empty_events(self, client, mock_adapter):
        row = make_webhook_row()
        row["events"] = []
        mock_adapter.register_webhook.return_value = row

        response = client.post(
            "/webhooks",
            json={"url": "https://example.com/webhook", "events": []},
        )

        assert response.status_code == 201


class TestListWebhooks:

    def test_list_returns_webhooks(self, client, mock_adapter):
        rows = [make_webhook_row(), make_webhook_row("https://other.com/hook")]
        mock_adapter.list_webhooks.return_value = rows

        response = client.get("/webhooks")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_returns_empty_list(self, client, mock_adapter):
        mock_adapter.list_webhooks.return_value = []

        response = client.get("/webhooks")

        assert response.status_code == 200
        assert response.json() == []


class TestDeleteWebhook:

    def test_delete_returns_204(self, client, mock_adapter):
        webhook_id = uuid.uuid4()
        row = make_webhook_row()
        row["id"] = webhook_id
        mock_adapter.list_webhooks.return_value = [row]

        response = client.delete(f"/webhooks/{webhook_id}")

        assert response.status_code == 204
        mock_adapter.delete_webhook.assert_called_once_with(webhook_id)

    def test_delete_not_found_returns_404(self, client, mock_adapter):
        mock_adapter.list_webhooks.return_value = []

        response = client.delete(f"/webhooks/{uuid.uuid4()}")

        assert response.status_code == 404
