"""
Webhook delivery service — sends HMAC-signed event payloads to subscriber endpoints.
Handles retry logic with exponential backoff.
"""
import asyncio
import hashlib
import hmac
import logging
from typing import Any

import httpx

from src.db.postgres_adapter import PostgresAdapter

logger = logging.getLogger(__name__)

# Number of retry attempts after a failed delivery
MAX_RETRIES = 3
# Initial delay between retries in seconds
RETRY_BASE_DELAY = 1.0


class WebhookDeliveryError(Exception):
    """Raised when a webhook fails to deliver after all retries."""
    pass


def _sign_payload(payload: str, secret: str | None) -> str:
    """
    Generate HMAC-SHA256 signature for a payload.
    If no secret is set, returns an empty string (no signature).
    """
    if not secret:
        return ""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def deliver_webhook(
    url: str,
    event_type: str,
    payload: dict[str, Any],
    secret: str | None = None,
) -> bool:
    """
    Deliver a single webhook event to a subscriber URL.
    Retries up to MAX_RETRIES times with exponential backoff on failure.
    Returns True if delivery succeeded, False otherwise.
    """
    body = __import__("json").dumps({"event": event_type, "data": payload})
    signature = _sign_payload(body, secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event_type,
    }
    if signature:
        headers["X-Webhook-Signature"] = signature

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await client.post(url, content=body, headers=headers)
                if response.status_code < 400:
                    logger.info(
                        "webhook_delivered",
                        extra={"url": url, "event": event_type, "status": response.status_code},
                    )
                    return True
                logger.warning(
                    "webhook_delivery_failed",
                    extra={
                        "url": url,
                        "event": event_type,
                        "status": response.status_code,
                        "attempt": attempt + 1,
                    },
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "webhook_request_error",
                    extra={"url": url, "event": event_type, "error": str(exc), "attempt": attempt + 1},
                )

            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                await asyncio.sleep(delay)

    logger.error(
        "webhook_delivery_exhausted",
        extra={"url": url, "event": event_type, "max_retries": MAX_RETRIES},
    )
    return False


class WebhookService:
    """
    Synchronous webhook dispatch service wrapping async delivery.
    Used by the daily research cron to fire webhooks without async context.
    """

    def __init__(self, db: PostgresAdapter | None = None) -> None:
        self._db = db or PostgresAdapter()

    def dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        """
        Dispatch a webhook event synchronously.
        Wraps the async deliver_webhook infrastructure for sync contexts.
        Failures are logged but do not raise.
        """
        try:
            webhooks = self._db.list_webhooks()
            subscribed = [
                wh for wh in webhooks
                if event_type in wh.get("events", [])
            ]
            for wh in subscribed:
                try:
                    import asyncio
                    asyncio.run(
                        deliver_webhook(
                            url=wh["url"],
                            event_type=event_type,
                            payload=payload,
                            secret=wh.get("secret"),
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "webhook_delivery_failed",
                        extra={"url": wh.get("url", ""), "event": event_type, "error": str(exc)},
                    )
        except Exception as exc:
            logger.error("webhook_dispatch_error", extra={"event": event_type, "error": str(exc)})


async def dispatch_event(
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """
    Find all webhooks subscribed to event_type and deliver the event to each.
    Failures are logged but do not raise — delivery is best-effort.
    """
    adapter = PostgresAdapter()
    webhooks = adapter.list_webhooks()

    subscribed = [
        wh for wh in webhooks
        if event_type in wh.get("events", [])
    ]

    if not subscribed:
        logger.debug("no_webhooks_subscribed", extra={"event": event_type})
        return

    tasks = [
        deliver_webhook(
            url=wh["url"],
            event_type=event_type,
            payload=payload,
            secret=wh.get("secret"),
        )
        for wh in subscribed
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    failures = sum(1 for r in results if r is not True)
    if failures:
        logger.warning(
            "webhook_dispatch_complete_with_failures",
            extra={"event": event_type, "total": len(tasks), "failures": failures},
        )
    else:
        logger.info("webhook_dispatch_complete", extra={"event": event_type, "total": len(tasks)})
