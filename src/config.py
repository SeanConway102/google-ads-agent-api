"""
Configuration loading and validation.
Mirrors ClientApp's env-var-driven config pattern (tests/support/config.js).
"""
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


# Singleton settings instance — import this in all modules
settings = Settings()
