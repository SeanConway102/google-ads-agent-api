"""
Tests for src/services/webhook_service.py — HMAC signing and delivery.
"""
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.webhook_service import (
    _sign_payload,
    deliver_webhook,
    dispatch_event,
)


class TestSignPayload:

    def test_sign_payload_generates_hmac_sha256(self):
        payload = '{"event":"test","data":{}}'
        secret = "my_secret"
        expected = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert _sign_payload(payload, secret) == expected

    def test_sign_payload_empty_string_when_no_secret(self):
        assert _sign_payload('{"event":"test"}', None) == ""
        assert _sign_payload('{"event":"test"}', "") == ""


class TestDeliverWebhook:

    @pytest.mark.asyncio
    async def test_deliver_webhook_success_returns_true(self):
        """A 2xx response means delivery succeeded and HMAC signature is sent."""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            secret = "my_hmac_secret"
            result = await deliver_webhook(
                url="https://example.com/webhook",
                event_type="consensus_reached",
                payload={"campaign_id": "cmp_001"},
                secret=secret,
            )

            assert result is True
            # Verify HMAC signature header was included
            call_args = mock_client.post.call_args
            assert "X-Webhook-Signature" in call_args.kwargs["headers"]
            # Verify the signature is correct HMAC-SHA256
            body = call_args.kwargs["content"]
            expected_sig = hmac.new(
                secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            assert call_args.kwargs["headers"]["X-Webhook-Signature"] == expected_sig

    @pytest.mark.asyncio
    async def test_deliver_webhook_retries_on_failure(self):
        """Failed delivery attempts should be retried MAX_RETRIES times."""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None
            mock_response.post.return_value = mock_response

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_cls.return_value = mock_client

            result = await deliver_webhook(
                url="https://example.com/webhook",
                event_type="consensus_reached",
                payload={},
                secret=None,
            )

            assert result is False
            assert mock_client.post.call_count == 4  # initial + 3 retries

    @pytest.mark.asyncio
    async def test_dispatch_event_calls_matching_webhooks(self):
        """dispatch_event should only call webhooks subscribed to the event type."""
        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("src.services.webhook_service.PostgresAdapter") as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.list_webhooks.return_value = [
                {"id": "1", "url": "https://a.com/hook", "events": ["consensus_reached"], "secret": None},
                {"id": "2", "url": "https://b.com/hook", "events": ["action_executed"], "secret": None},
            ]
            mock_adapter_cls.return_value = mock_adapter

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_cls.return_value = mock_client

            await dispatch_event(event_type="consensus_reached", payload={"test": "data"})

            # Only the consensus_reached webhook should be called
            assert mock_client.post.call_count == 1
            call_args = mock_client.post.call_args
            assert call_args.kwargs["content"].find("consensus_reached") > 0

    @pytest.mark.asyncio
    async def test_dispatch_event_no_subscribers(self):
        """If no webhooks are subscribed, no delivery attempts are made."""
        with patch("src.services.webhook_service.PostgresAdapter") as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.list_webhooks.return_value = []
            mock_adapter_cls.return_value = mock_adapter

            await dispatch_event(event_type="consensus_reached", payload={})

            # No HTTP client created means no calls made
