"""
Test configuration — loaded from environment variables.
Mirrors ClientApp/tests/support/config.js pattern.
"""
import os

# API base URL — defaults to localhost, override via TEST_BASE_URL env var
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")

# Admin API key for test environment
ADMIN_API_KEY = os.environ.get("TEST_ADMIN_API_KEY", "test-admin-key-123")

# Database URL — must be a test database, never production
DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ads_agent_test"
)

# MiniMax API key (for LLM adapter tests)
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "test-minimax-key")

# Check required env vars at import time — fail fast
_TEST_PASSWORD = os.environ.get("TEST_ADMIN_API_KEY")
if not _TEST_PASSWORD and "CI" in os.environ:
    raise RuntimeError(
        "TEST_ADMIN_API_KEY environment variable is required. "
        "Set it in .env.test or pass it: TEST_ADMIN_API_KEY=xxx pytest ..."
    )
