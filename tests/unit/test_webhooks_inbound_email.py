"""
RED: Write the failing test first.
Tests for POST /webhooks/inbound-email — Resend inbound email webhook.

BUG: The HITL plan calls for POST /webhooks/inbound-email to receive
inbound replies from Resend, but this route does not exist.
The reply_handler exists but is not wired to a webhook route.
"""
import uuid
from unittest.mock import MagicMock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.webhooks import router


@pytest.fixture
def mock_reply_handler(monkeypatch):
    mock = MagicMock()
    # Must patch where it's imported, not where it's defined
    monkeypatch.setattr("src.api.routes.webhooks.handle_inbound_reply", mock)
    return mock


@pytest.fixture
def mock_settings(monkeypatch):
    mock = MagicMock()
    mock.RESEND_INBOUND_SECRET = "test-secret"
    # get_settings is called at runtime in the route handler
    monkeypatch.setattr("src.api.routes.webhooks.get_settings", lambda: mock)
    return mock


@pytest.fixture
def webhooks_app(mock_settings, mock_reply_handler):
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(webhooks_app):
    return TestClient(webhooks_app, raise_server_exceptions=False)


class TestInboundEmailWebhook:
    """POST /webhooks/inbound-email receives and processes Resend inbound emails."""

    def test_returns_401_when_secret_invalid(self, client):
        """Invalid or missing X-Resend-Webhook-Secret returns 401."""
        response = client.post(
            "/webhooks/inbound-email",
            json={
                "from": "owner@example.com",
                "to": "reply@adsagent.ai",
                "subject": "Re: Action needed",
                "body": "yes",
            },
            headers={"X-Resend-Webhook-Secret": "wrong-secret"},
        )
        assert response.status_code == 401

    def test_returns_401_when_secret_missing(self, client):
        """Missing X-Resend-Webhook-Secret header returns 401."""
        response = client.post(
            "/webhooks/inbound-email",
            json={
                "from": "owner@example.com",
                "to": "reply@adsagent.ai",
                "subject": "Re: Action needed",
                "body": "yes",
            },
        )
        assert response.status_code == 401

    def test_calls_handle_inbound_reply_on_valid_request(self, client, mock_reply_handler):
        """Valid request with correct secret calls handle_inbound_reply."""
        mock_reply_handler.return_value = None
        response = client.post(
            "/webhooks/inbound-email",
            json={
                "from": "owner@example.com",
                "to": "reply@adsagent.ai",
                "subject": "Re: Action required on campaign [#abc]",
                "body": "yes, go ahead",
            },
            headers={"X-Resend-Webhook-Secret": "test-secret"},
        )

        assert response.status_code == 200
        mock_reply_handler.assert_called_once()
        call_kwargs = mock_reply_handler.call_args.kwargs
        assert call_kwargs["from_email"] == "owner@example.com"
        assert call_kwargs["body"] == "yes, go ahead"
        assert call_kwargs["subject"] == "Re: Action required on campaign [#abc]"

    def test_returns_200_even_if_handler_raises(self, client, mock_reply_handler):
        """Handler exceptions should not cause 500 — return 200 to avoid Resend retries."""
        mock_reply_handler.side_effect = Exception("DB error")
        response = client.post(
            "/webhooks/inbound-email",
            json={
                "from": "owner@example.com",
                "to": "reply@adsagent.ai",
                "subject": "Re: Action required",
                "body": "yes",
            },
            headers={"X-Resend-Webhook-Secret": "test-secret"},
        )

        assert response.status_code == 200
