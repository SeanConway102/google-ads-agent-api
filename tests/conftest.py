"""
Pytest fixtures and configuration.
Mirrors ClientApp/tests/support/hooks.js + conftest.py patterns.

Key principles from ClientApp that we replicate:
- TestWorld per scenario (shared state)
- Environment-driven config (no hardcoded credentials)
- Safety guards (e.g., destructive tests only against localhost)
- Cleanup after every scenario
"""
import pytest
import httpx
from tests.support.config import BASE_URL, ADMIN_API_KEY, DATABASE_URL
from tests.support.world import TestWorld


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_url():
    return BASE_URL


@pytest.fixture
def admin_api_key():
    return ADMIN_API_KEY


@pytest.fixture
def database_url():
    return DATABASE_URL


@pytest.fixture
def api_client(base_url, admin_api_key):
    """
    Shared HTTP client for the test scenario.
    Uses X-API-Key authentication — mirrors ClientApp's auth header pattern.
    """
    client = httpx.Client(base_url=base_url, timeout=30.0)
    yield client
    client.close()


@pytest.fixture
def world(base_url, admin_api_key):
    """
    TestWorld — mirrors ClientApp's TestWorld class.
    Holds all shared state for a test scenario.
    Automatically cleaned up after each test.
    """
    w = TestWorld(base_url=base_url, admin_api_key=admin_api_key)
    w.create_api_client()
    yield w
    w.cleanup()


@pytest.fixture
def auth_headers():
    """Standard authenticated headers — used in direct API calls."""
    return {"X-API-Key": ADMIN_API_KEY}


@pytest.fixture
def authenticated_client(api_client, admin_api_key):
    """
    Pre-configured API client with auth headers already set.
    Mirrors ClientApp's "I send an authenticated GET to" pattern.
    """
    api_client.headers["X-API-Key"] = admin_api_key
    return api_client


@pytest.fixture
def clean_db(database_url):
    """
    Provides a clean database connection for tests.
    Tests should use this to set up and tear down test data.
    Note: This fixture assumes the test database is already created.
    For full isolation, tests should clean up after themselves.
    """
    import psycopg2
    conn = psycopg2.connect(database_url)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Pytest configuration
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Pure unit tests, no I/O")
    config.addinivalue_line("markers", "integration: Tests that hit DB or network")
    config.addinivalue_line("markers", "slow: Tests that take >5 seconds")
    config.addinivalue_line("markers", "requires_db: Needs PostgreSQL running")
    config.addinivalue_line("markers", "requires_mcp: Needs MCP server running")


def pytest_collection_modifyitems(config, items):
    """Auto-skip integration tests when --unit-only is passed."""
    if config.option.unit_only:
        skip_integration = pytest.mark.skip(reason="--unit-only: skipping integration tests")
        for item in items:
            if "integration" not in item.keywords and "unit" not in item.keywords:
                item.add_marker(skip_integration)


def pytest_addoption(parser):
    """Add custom CLI options."""
    parser.addoption(
        "--unit-only",
        action="store_true",
        default=False,
        help="Run only unit tests, skip integration tests"
    )


# ---------------------------------------------------------------------------
# Safety guards — mirrors ClientApp's @destructive guard
# ---------------------------------------------------------------------------

def pytest_runtest_setup(item):
    """
    Safety guard: integration tests that modify data should be
    marked with @pytest.mark.integration and will fail if run
    against a non-localhost database.
    """
    db_url = DATABASE_URL
    is_destructive = item.get_closest_marker("integration") is not None

    if is_destructive and not any(
        x in db_url for x in ("localhost", "127.0.0.1", "test")
    ):
        pytest.fail(
            f"SAFETY: Integration tests cannot run against non-localhost DB. "
            f"DATABASE_URL={db_url}. "
            f"Use TEST_DATABASE_URL pointing to a local test database."
        )
