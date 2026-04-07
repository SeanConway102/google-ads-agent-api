"""
Tests for inbound-email webhook bypass of API key middleware.
POST /webhooks/inbound-email is called by Resend's servers — they don't have
our X-API-Key. The route has its own X-Resend-Webhook-Secret validation.
APIKeyAuthMiddleware must exempt this path so Resend can deliver emails.
"""
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_inbound_email_reachable_without_api_key():
    """
    POST /webhooks/inbound-email must be reachable without X-API-Key header.
    The route validates X-Resend-Webhook-Secret instead (set by Resend servers).
    APIKeyAuthMiddleware must exempt this path — the X-Resend-Webhook-Secret
    header is validated by the route handler, not the API key middleware.
    """
    from src.api.middleware import APIKeyAuthMiddleware
    from src.api.routes.webhooks import router

    assert "/webhooks/inbound-email" in APIKeyAuthMiddleware.EXEMPT_PATHS, (
        f"EXEMPT_PATHS is {APIKeyAuthMiddleware.EXEMPT_PATHS!r} — "
        "/webhooks/inbound-email must be listed to allow Resend servers through."
    )

    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware)
    app.include_router(router)

    mock_adapter = MagicMock()
    mock_adapter.get_campaign_by_owner_email.return_value = None
    mock_adapter.list_webhooks.return_value = []

    # Clear lru_cache on get_settings before patching — otherwise the first
    # cached call (from another test's module import) persists and the patch
    # has no effect on the already-cached Settings instance.
    from src.config import get_settings
    get_settings.cache_clear()

    # Configure a mock Settings object with the test secret.
    # webhooks.py does `from src.config import get_settings` at module level,
    # so patch must target the binding in webhooks' namespace, not src.config.
    mock_settings = MagicMock()
    mock_settings.RESEND_INBOUND_SECRET = "test-resend-secret"

    with patch("src.api.routes.webhooks.PostgresAdapter", return_value=mock_adapter), \
         patch("src.services.reply_handler.PostgresAdapter", return_value=mock_adapter), \
         patch("src.api.middleware.get_admin_api_key", return_value="test-admin-key"), \
         patch("src.api.routes.webhooks.get_settings", return_value=mock_settings):

        with TestClient(app, raise_server_exceptions=False) as client:
            # No API key header — this is how Resend's servers call us
            response = client.post(
                "/webhooks/inbound-email",
                json={
                    "from": "owner@example.com",
                    "to": "reply@adsagent.ai",
                    "subject": "Re: Action needed",
                    "body": "yes",
                },
                headers={
                    "X-Resend-Webhook-Secret": "test-resend-secret",
                },
            )

            # Without the fix: APIKeyAuthMiddleware returns 401
            # With the fix: route processes the request, returns 200/400
            assert response.status_code != 401, (
                f"Got {response.status_code} — APIKeyAuthMiddleware blocked "
                "/webhooks/inbound-email before the route's X-Resend-Webhook-Secret "
                "validation could run. Resend cannot deliver inbound emails."
            )
