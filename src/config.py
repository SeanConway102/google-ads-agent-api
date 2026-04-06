"""
Configuration loading and validation.
Mirrors ClientApp's env-var-driven config pattern (tests/support/config.js).
"""
from functools import lru_cache
from typing import Literal
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    All application configuration — loaded from environment variables.

    Pydantic Settings automatically:
    - Loads from .env file if present
    - Converts env var names (ADMIN_API_KEY from ADMIN_API_KEY)
    - Validates types and enums
    - Raises ValidationError for missing required fields

    Env vars can be set in:
    1. .env file in project root
    2. Environment variables in the shell
    """

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore",  # Ignore unknown env vars — prevents crashes from typos
    )

    # ─── Admin ────────────────────────────────────────────────────────────────
    ADMIN_API_KEY: str  # Required — no default, must be set

    # ─── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ads_agent"
    DB_PROVIDER: Literal["postgresql", "sqlite"] = "postgresql"

    # ─── Google Ads (MCC) ────────────────────────────────────────────────────
    GOOGLE_ADS_DEVELOPER_TOKEN: str = ""
    GOOGLE_ADS_CLIENT_ID: str = ""
    GOOGLE_ADS_CLIENT_SECRET: str = ""
    GOOGLE_ADS_REFRESH_TOKEN: str = ""
    GOOGLE_ADS_CUSTOMER_ID: str = ""

    # ─── LLM ─────────────────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["minimax", "openai", "anthropic"] = "minimax"
    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.minimax.chat"
    MINIMAX_MODEL: str = "MiniMax-Text-01"

    # ─── MCP ─────────────────────────────────────────────────────────────────
    MCP_SERVER_PATH: str = "/opt/ads-agent/mcp_server.py"

    # ─── Research ─────────────────────────────────────────────────────────────
    RESEARCH_CRON: str = "0 8 * * *"  # 8am server time daily
    MAX_DEBATE_ROUNDS: int = 5


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Lazily create and cache the Settings singleton.
    Call this function to get settings — avoids crashing on module import
    before test env vars are set.
    """
    return Settings()


def get_database_url() -> str:
    """Get DATABASE_URL from settings. Lazily initializes settings."""
    return get_settings().DATABASE_URL


def get_admin_api_key() -> str:
    """Get ADMIN_API_KEY from settings. Lazily initializes settings."""
    return get_settings().ADMIN_API_KEY
