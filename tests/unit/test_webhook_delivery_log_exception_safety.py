"""
RED: Write the failing test first.
Tests that DB write failures in webhook_delivery_log do not break webhook delivery.

The gap: db.write_webhook_delivery_log() calls in deliver_webhook are not
wrapped in try/except. If the DB is down, the exception propagates and
interrupts the retry loop, preventing webhook delivery entirely.
"""
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
import httpx


class TestWebhookDeliveryLogExceptionSafety:
    """
    DB write failures in write_webhook_delivery_log must be caught and logged,
    not propagated — webhook delivery must succeed even if DB logging fails.
    """

    def test_db_write_failure_does_not_interrupt_successful_delivery(self):
        """
        When the DB write for 'delivered' status raises an exception,
        deliver_webhook must still return True (delivery succeeded).
        The DB failure should be logged, not propagated.
        """
        from src.services.webhook_service import deliver_webhook

        def db_write_that_fails(data: dict) -> dict:
            raise Exception("Database connection refused")

        mock_adapter = MagicMock()
        mock_adapter.write_webhook_delivery_log.side_effect = db_write_that_fails
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
                    subscription_id=str(subscription_id),
                )
            )

        # Delivery succeeded — DB failure must not interrupt this
        assert result is True, (
            "deliver_webhook returned False because DB exception propagated. "
            "Webhook delivery should succeed even when DB logging fails."
        )

    def test_db_write_failure_does_not_interrupt_retry_loop(self):
        """
        When a DB write for 'retrying' status raises, the retry loop must
        continue — delivery attempts must not be halted by DB failures.
        """
        from src.services.webhook_service import deliver_webhook, MAX_RETRIES

        call_count = 0

        def db_write_that_fails_after_first(data: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise Exception("Database connection refused")
            return {"id": uuid.uuid4(), **data}

        mock_adapter = MagicMock()
        mock_adapter.write_webhook_delivery_log.side_effect = db_write_that_fails_after_first

        subscription_id = uuid.uuid4()

        # First attempt: 500 error (triggers retrying log write)
        # Second attempt: 200 success (triggers delivered log write)
        responses = [MagicMock(status_code=500), MagicMock(status_code=200)]
        response_iter = iter(responses)

        async def mock_post(*_args, **_kwargs):
            return next(response_iter)

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
                    db=mock_adapter,
                    subscription_id=str(subscription_id),
                )
            )

        # Delivery should succeed despite the DB write failure on retry #1
        assert result is True, (
            "deliver_webhook returned False because DB exception during retry "
            "loop interrupted delivery. Retries must continue even if DB writes fail."
        )
        # Should have retried (first attempt was 500)
        assert call_count >= 2, f"Expected at least 2 DB write attempts, got {call_count}"

    def test_final_failed_db_write_does_not_prevent_false_return(self):
        """
        When the final 'failed' log write raises, deliver_webhook must still
        return False — the delivery failure outcome must not be lost.
        """
        from src.services.webhook_service import deliver_webhook, MAX_RETRIES

        write_count = 0

        def db_write_that_fails_on_final(data: dict) -> dict:
            nonlocal write_count
            write_count += 1
            # Fail only on the final 'failed' write (after all retries exhausted)
            if write_count > MAX_RETRIES:
                raise Exception("Database connection refused")
            return {"id": uuid.uuid4(), **data}

        mock_adapter = MagicMock()
        mock_adapter.write_webhook_delivery_log.side_effect = db_write_that_fails_on_final

        subscription_id = uuid.uuid4()

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
                    subscription_id=str(subscription_id),
                )
            )

        # Delivery failed — final False return must not be prevented by DB error
        assert result is False, (
            "deliver_webhook should return False after exhausting retries, "
            "even if the final 'failed' log write raises."
        )
