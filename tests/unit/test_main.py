"""
RED: Write the failing test first.
Tests for src/main.py — FastAPI app bootstrap and route mounting.
"""
import pytest
from unittest.mock import MagicMock

from src.main import create_app


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_api_key(monkeypatch):
    """Provide a test admin API key for all tests in this module."""
    monkeypatch.setattr("src.api.middleware.get_admin_api_key", lambda: "test-secret-key")


@pytest.fixture
def mock_settings_env(monkeypatch):
    """Set required environment variables so get_settings() succeeds."""
    monkeypatch.setenv("ADMIN_API_KEY", "test-secret-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("DB_PROVIDER", "postgresql")
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "test-token")
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_ID", "test-id")
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("GOOGLE_ADS_REFRESH_TOKEN", "test-refresh")
    monkeypatch.setenv("GOOGLE_ADS_CUSTOMER_ID", "test-customer")
    monkeypatch.setenv("LLM_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimax.chat")
    monkeypatch.setenv("MINIMAX_MODEL", "test-model")


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCreateApp:
    """Test the FastAPI application factory."""

    def test_create_app_returns_fastapi_instance(self, mock_api_key, mock_settings_env):
        """create_app() returns a FastAPI application."""
        app = create_app()
        assert app is not None

    def test_health_endpoint_returns_ok(self, mock_api_key, mock_settings_env):
        """GET /health returns {"status": "ok"} without auth check (exempt)."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    def test_health_response_includes_request_id_header(self, mock_api_key, mock_settings_env):
        """Health endpoint responses include X-Request-ID header from RequestLoggingMiddleware."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert "x-request-id" in response.headers

    def test_docs_endpoint_accessible(self, mock_api_key, mock_settings_env):
        """GET /docs returns 200 (Swagger UI)."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/docs")
            assert response.status_code == 200

    def test_redoc_endpoint_accessible(self, mock_api_key, mock_settings_env):
        """GET /redoc returns 200 (ReDoc)."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/redoc")
            assert response.status_code == 200

    def test_openapi_endpoint_accessible(self, mock_api_key, mock_settings_env):
        """GET /openapi.json returns 200 with valid OpenAPI schema."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/openapi.json")
            assert response.status_code == 200
            data = response.json()
            assert "openapi" in data
            assert "info" in data
            assert "version" in data["info"]  # version field exists in info object

    def test_openapi_schema_has_paths(self, mock_api_key, mock_settings_env):
        """OpenAPI schema includes a paths object with at least the health endpoint."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/openapi.json")
            data = response.json()
            assert "paths" in data
            assert "/health" in data["paths"]


class TestRouteMounting:
    """Verify all routes are mounted on the app."""

    def test_campaigns_router_mounted(self, mock_api_key, mock_settings_env):
        """Campaign router is included in the app."""
        app = create_app()
        routes = [r.path for r in app.routes]
        assert any("campaigns" in r for r in routes)

    def test_wiki_router_mounted(self, mock_api_key, mock_settings_env):
        """Wiki router is included in the app."""
        app = create_app()
        routes = [r.path for r in app.routes]
        assert any("wiki" in r or "research" in r for r in routes)

    def test_webhooks_router_mounted(self, mock_api_key, mock_settings_env):
        """Webhooks router is included in the app."""
        app = create_app()
        routes = [r.path for r in app.routes]
        assert any("webhook" in r for r in routes)

    def test_audit_router_mounted(self, mock_api_key, mock_settings_env):
        """Audit router is included in the app."""
        app = create_app()
        routes = [r.path for r in app.routes]
        assert any("audit" in r for r in routes)


class TestMiddlewareApplied:
    """Verify middleware is applied to the app."""

    def test_request_logging_middleware_is_active(self, mock_api_key, mock_settings_env):
        """RequestLoggingMiddleware is active — responses on health have request ID header."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/health")
            assert "x-request-id" in response.headers

    def test_cors_middleware_enabled(self, mock_api_key, mock_settings_env):
        """CORS middleware is enabled — preflight requests get access-control-allow-origin header."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
            # CORS preflight should get access-control-allow-origin header
            assert "access-control-allow-origin" in response.headers

    def test_protected_routes_require_api_key(self, mock_api_key, mock_settings_env):
        """Protected routes (campaigns) return 401 without X-API-Key header."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/campaigns")
            assert response.status_code == 401

    def test_protected_routes_accept_valid_api_key(self, mock_api_key, mock_settings_env):
        """Protected routes accept requests with valid X-API-Key header."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/campaigns", headers={"X-API-Key": "test-secret-key"})
            # Should not be 401 — may be 200 (if DB available) or 500 (if DB not available)
            assert response.status_code != 401

    def test_unauthenticated_request_returns_json_error_structure(self, mock_api_key, mock_settings_env):
        """Unauthenticated requests (no API key) return JSON error with error and detail fields."""
        app = create_app()
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/campaigns")
            assert response.status_code == 401
            body = response.json()
            assert "error" in body
            assert "detail" in body