"""
RED: Write the failing test first.
Tests for src/api/middleware.py — authentication, logging, error handling.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.middleware import (
    APIKeyAuthMiddleware,
    RequestLoggingMiddleware,
    setup_exception_handlers,
)


# ──────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_settings(monkeypatch):
    """Override get_admin_api_key for all tests in this module."""
    monkeypatch.setattr("src.api.middleware.get_admin_api_key", lambda: "test-secret-key")


@pytest.fixture
def test_app(mock_settings):
    """Create a minimal FastAPI app with middleware for testing."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(APIKeyAuthMiddleware)
    setup_exception_handlers(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/protected")
    def protected():
        return {"data": "secret"}

    @app.post("/protected")
    def protected_post(body: dict):
        return {"received": body}

    @app.get("/items/{item_id}")
    def get_item(item_id: int):
        if item_id == 999:
            raise ValueError("Item not found")
        return {"item_id": item_id}

    @app.get("/error")
    def trigger_error():
        raise RuntimeError("Unexpected error")

    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app, raise_server_exceptions=False)


# ──────────────────────────────────────────────────────────────────────────────
# Authentication middleware tests
# ──────────────────────────────────────────────────────────────────────────────

class TestAPIKeyAuth:

    def test_health_endpoint_exempt_from_auth(self, client):
        """GET /health returns 200 without API key."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_protected_rejects_missing_api_key(self, client):
        """Requests to /protected without X-API-Key return 401."""
        response = client.get("/protected")
        assert response.status_code == 401
        assert response.json()["error"] == "missing_api_key"

    def test_protected_rejects_invalid_api_key(self, client):
        """Requests with wrong X-API-Key return 401."""
        response = client.get(
            "/protected",
            headers={"x-api-key": "wrong-key"},
        )
        assert response.status_code == 401
        assert response.json()["error"] == "invalid_api_key"

    def test_protected_accepts_valid_api_key(self, client):
        """Requests with correct X-API-Key pass through."""
        response = client.get(
            "/protected",
            headers={"x-api-key": "test-secret-key"},
        )
        assert response.status_code == 200
        assert response.json() == {"data": "secret"}

    def test_post_request_validates_with_api_key(self, client):
        """POST requests also require valid API key."""
        response = client.post(
            "/protected",
            headers={"x-api-key": "test-secret-key"},
            json={"name": "test"},
        )
        assert response.status_code == 200
        assert response.json() == {"received": {"name": "test"}}

    def test_request_id_header_added_to_response(self, client):
        """All responses include X-Request-ID header."""
        response = client.get(
            "/protected",
            headers={"x-api-key": "test-secret-key"},
        )
        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) > 0

    def test_existing_request_id_preserved(self, client):
        """If client sends X-Request-ID, it is preserved in the response."""
        response = client.get(
            "/protected",
            headers={
                "x-api-key": "test-secret-key",
                "x-request-id": "my-custom-id-123",
            },
        )
        assert response.headers["x-request-id"] == "my-custom-id-123"


# ──────────────────────────────────────────────────────────────────────────────
# Exception handler tests
# ──────────────────────────────────────────────────────────────────────────────

class TestExceptionHandlers:

    def test_value_error_returns_422(self, client):
        """ValueError exceptions return 422 with error code validation_error."""
        response = client.get(
            "/items/999",
            headers={"x-api-key": "test-secret-key"},
        )
        assert response.status_code == 422
        assert response.json()["error"] == "validation_error"

    def test_unhandled_exception_returns_500(self, client):
        """Unexpected exceptions return 500 with error code internal_error."""
        response = client.get(
            "/error",
            headers={"x-api-key": "test-secret-key"},
        )
        assert response.status_code == 500
        assert response.json()["error"] == "internal_error"

    def test_error_response_includes_request_id(self, client):
        """Error responses include request_id when available, and X-Request-ID header always set."""
        response = client.get(
            "/error",
            headers={"x-api-key": "test-secret-key"},
        )
        body = response.json()
        assert body["error"] == "internal_error"
        # X-Request-ID header is always set by the logging middleware
        assert "x-request-id" in response.headers
