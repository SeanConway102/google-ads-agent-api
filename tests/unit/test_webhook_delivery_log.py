"""
RED: Write the failing tests first.
Tests that webhook delivery attempts are persisted to webhook_delivery_log.

The gap: deliver_webhook retries in-memory but never writes to webhook_delivery_log.
Operators cannot audit what webhooks were fired or retry failed ones from the DB.
"""
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
import httpx

import pytest


class TestWebhookDeliveryLogPersisted:
    """
    Every webhook delivery attempt (success or failure) must be written to
    webhook_delivery_log so operators can audit delivery history.
    """

    def test_successful_delivery_writes_delivered_log(self):
        """
        When a webhook delivers successfully (response < 400), a row with
        status='delivered' must be written to webhook_delivery_log.
        """
        from src.services.webhook_service import deliver_webhook

        log_entries = []

        mock_adapter = MagicMock()

        def track_write_delivery_log(data: dict) -> dict:
            log_entries.append(data)
            return {"id": uuid.uuid4(), **data}

        mock_adapter.write_webhook_delivery_log.side_effect = track_write_delivery_log
        mock_adapter.list_webhooks.return_value = []

        subscription_id = uuid.uuid4()
        mock_adapter.list_webhooks.return_value = [
            {
                "id": subscription_id,
                "url": "https://example.com/webhook",
                "events": ["consensus_reached"],
                "secret": "test-secret",
                "active": True,
            }
        ]

        # Mock the HTTP client to return success
        mock_response = MagicMock()
        mock_response.status_code = 200

        async def mock_post(*_args, **_kwargs):
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client_class.return_value.__aenter__.return_value = mock_client

            import asyncio
            result = asyncio.run(
                deliver_webhook(
                    url="https://example.com/webhook",
                    event_type="consensus_reached",
                    payload={"campaign_id": "123"},
                    secret="test-secret",
                    db=mock_adapter,
                    subscription_id=subscription_id,
                )
            )

        assert result is True
        assert len(log_entries) == 1, (
            f"Expected exactly 1 webhook_delivery_log entry, got {len(log_entries)}. "
            "deliver_webhook never writes to webhook_delivery_log — operators cannot "
            "audit delivery history or retry failed webhooks from the DB."
        )
        assert log_entries[0]["status"] == "delivered"
        assert str(log_entries[0]["subscription_id"]) == str(subscription_id)
        assert log_entries[0]["event"] == "consensus_reached"

    def test_failed_delivery_after_retries_writes_failed_log(self):
        """
        When all retry attempts fail, a row with status='failed' must be written.
        """
        from src.services.webhook_service import deliver_webhook

        log_entries = []

        def track_write_delivery_log(data: dict) -> dict:
            log_entries.append(data)
            return {"id": uuid.uuid4(), **data}

        mock_adapter = MagicMock()
        mock_adapter.write_webhook_delivery_log.side_effect = track_write_delivery_log

        subscription_id = uuid.uuid4()

        # Mock the HTTP client to always return error
        async def mock_post_fail(*_args, **_kwargs):
            raise httpx.RequestError("Connection refused")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = mock_post_fail
            mock_client_class.return_value.__aenter__.return_value = mock_client

            import asyncio
            result = asyncio.run(
                deliver_webhook(
                    url="https://example.com/webhook",
                    event_type="consensus_reached",
                    payload={"campaign_id": "123"},
                    db=mock_adapter,
                    subscription_id=subscription_id,
                )
            )

        assert result is False
        # All 4 attempts (3 retries + final failure) produce a log entry
        assert len(log_entries) == 4
        # Last entry is the final failed state
        final_entry = log_entries[-1]
        assert final_entry["status"] == "failed"
        assert str(final_entry["subscription_id"]) == str(subscription_id)

    def test_each_retry_attempt_writes_retrying_log(self):
        """
        On each failed attempt (before max retries are exhausted), a row with
        status='retrying' must be written so operators can see retry progress.
        """
        from src.services.webhook_service import deliver_webhook, MAX_RETRIES

        log_entries = []

        def track_write_delivery_log(data: dict) -> dict:
            log_entries.append(data)
            return {"id": uuid.uuid4(), **data}

        mock_adapter = MagicMock()
        mock_adapter.write_webhook_delivery_log.side_effect = track_write_delivery_log

        subscription_id = uuid.uuid4()

        # Mock the HTTP client to always return error
        async def mock_post_fail(*_args, **_kwargs):
            raise httpx.RequestError("Connection refused")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = mock_post_fail
            mock_client_class.return_value.__aenter__.return_value = mock_client

            import asyncio
            result = asyncio.run(
                deliver_webhook(
                    url="https://example.com/webhook",
                    event_type="consensus_reached",
                    payload={"campaign_id": "123"},
                    db=mock_adapter,
                    subscription_id=subscription_id,
                )
            )

        assert result is False
        # Should have one 'retrying' entry per failed attempt (MAX_RETRIES attempts)
        # and one final 'failed' entry
        retrying_entries = [e for e in log_entries if e["status"] == "retrying"]
        assert len(retrying_entries) == MAX_RETRIES, (
            f"Expected {MAX_RETRIES} retrying entries (one per attempt), "
            f"got {len(retrying_entries)}"
        )
        failed_entries = [e for e in log_entries if e["status"] == "failed"]
        assert len(failed_entries) == 1
