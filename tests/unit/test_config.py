"""
RED: Write the failing test first.
This test describes what config.py SHOULD do.

Mirrors ClientApp's rule: "A test that only checks status code proves nothing."
This test verifies actual behavior: env var loading, defaults, validation.
"""
import pytest
import os
from importlib import reload


class TestConfigLoading:
    """Tests for src/config.py — environment variable loading and validation."""

    def test_settings_loads_admin_api_key_from_env(self, monkeypatch):
        """
        When ADMIN_API_KEY is set in environment, it must be accessible via settings.
        This is the most critical config value — the system is useless without it.
        """
        monkeypatch.setenv("ADMIN_API_KEY", "my-secret-key-123")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/ads_agent")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test-key")

        # Reload config module to pick up env vars
        import src.config as cfg
        reload(cfg)

        settings = cfg.get_settings()
        assert settings.ADMIN_API_KEY == "my-secret-key-123", \
            "ADMIN_API_KEY should be loaded from environment"

    def test_settings_loads_database_url_with_defaults(self, monkeypatch):
        """
        When DATABASE_URL is not set, a sensible default should apply.
        Default must point to localhost PostgreSQL.
        """
        # Clear any existing env vars
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")

        import src.config as cfg
        reload(cfg)

        settings = cfg.get_settings()
        assert "postgresql" in settings.DATABASE_URL, \
            "DATABASE_URL should default to PostgreSQL"
        assert "localhost" in settings.DATABASE_URL, \
            "Default DATABASE_URL should point to localhost"

    def test_settings_loads_minimax_config(self, monkeypatch):
        """MiniMax API settings must be configurable via environment variables."""
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-abc123")
        monkeypatch.setenv("MINIMAX_BASE_URL", "https://custom.minimax.io")
        monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Text-01")

        import src.config as cfg
        reload(cfg)

        settings = cfg.get_settings()
        assert settings.MINIMAX_API_KEY == "minimax-abc123"
        assert settings.MINIMAX_BASE_URL == "https://custom.minimax.io"
        assert settings.MINIMAX_MODEL == "MiniMax-Text-01"

    def test_settings_has_correct_defaults(self, monkeypatch):
        """Non-critical settings have sensible defaults when not explicitly set."""
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("MAX_DEBATE_ROUNDS", raising=False)

        import src.config as cfg
        reload(cfg)

        settings = cfg.get_settings()
        assert settings.MAX_DEBATE_ROUNDS == 5, \
            "MAX_DEBATE_ROUNDS should default to 5"
        assert settings.RESEARCH_CRON == "0 8 * * *", \
            "RESEARCH_CRON should default to 8am daily"
        assert settings.DB_PROVIDER == "postgresql", \
            "DB_PROVIDER should default to postgresql"

    def test_settings_ignores_extra_env_vars(self, monkeypatch):
        """
        Extra environment variables not defined in Settings should be ignored.
        This prevents the app from crashing due to typos in env var names.
        """
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("SUPER_EXTRA_UNKNOWN_VAR", "should-be-ignored")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/ads")

        import src.config as cfg
        reload(cfg)

        settings = cfg.get_settings()
        # Should not raise — extra vars should be silently ignored
        assert hasattr(settings, "ADMIN_API_KEY")
        # SUPER_EXTRA_UNKNOWN_VAR should not appear in settings
        assert not hasattr(settings, "SUPER_EXTRA_UNKNOWN_VAR")


class TestConfigValidation:
    """Tests for config value validation."""

    def test_settings_requires_admin_api_key(self, monkeypatch):
        """
        ADMIN_API_KEY is required — missing it should cause a ValidationError
        when Settings is instantiated. This is a security critical field.

        Strategy: test the Settings class directly without reloading the module,
        avoiding the module-level singleton that would crash during import.
        """
        # Create a new Settings instance with only optional fields set
        from src.config import Settings
        with pytest.raises(Exception) as exc_info:
            Settings(
                DATABASE_URL="postgresql://localhost/test",
                MINIMAX_API_KEY="minimax-key",
            )
        # Confirm the error is about the missing required ADMIN_API_KEY
        assert "ADMIN_API_KEY" in str(exc_info.value)

    def test_settings_validates_db_provider(self, monkeypatch):
        """DB_PROVIDER must be one of the supported values (postgresql or sqlite)."""
        from src.config import Settings
        # "mysql" is not a valid DB_PROVIDER — should raise ValidationError
        with pytest.raises(Exception) as exc_info:
            Settings(
                ADMIN_API_KEY="test-key",
                DATABASE_URL="postgresql://localhost/test",
                MINIMAX_API_KEY="minimax-key",
                DB_PROVIDER="mysql",  # Invalid — only postgresql/sqlite allowed
            )
        assert "DB_PROVIDER" in str(exc_info.value)

    def test_hitl_settings_fields(self, monkeypatch):
        """Settings must have all HITL/Resend env var fields."""
        monkeypatch.setenv("RESEND_API_KEY", "re_test123")
        monkeypatch.setenv("RESEND_INBOUND_SECRET", "inbound_secret")
        monkeypatch.setenv("HITL_ENABLED", "true")
        monkeypatch.setenv("HITL_DEFAULT_EMAIL", "owner@example.com")
        monkeypatch.setenv("HITL_PROPOSAL_TTL_DAYS", "14")
        monkeypatch.setenv("HITL_WEEKLY_CRON", "0 8 * * 3")
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        import src.config as cfg
        reload(cfg)

        s = cfg.get_settings()
        # Pydantic loads env vars as uppercase attributes (RESEND_API_KEY env var → RESEND_API_KEY attr)
        assert getattr(s, "RESEND_API_KEY", None) == "re_test123", "Settings needs RESEND_API_KEY"
        assert getattr(s, "RESEND_INBOUND_SECRET", None) == "inbound_secret", "Settings needs RESEND_INBOUND_SECRET"
        assert getattr(s, "HITL_ENABLED", None) is True, "Settings needs HITL_ENABLED"
        assert getattr(s, "HITL_DEFAULT_EMAIL", None) == "owner@example.com", "Settings needs HITL_DEFAULT_EMAIL"
        assert getattr(s, "HITL_PROPOSAL_TTL_DAYS", None) == 14, "Settings needs HITL_PROPOSAL_TTL_DAYS"
        assert getattr(s, "HITL_WEEKLY_CRON", None) == "0 8 * * 3", "Settings needs HITL_WEEKLY_CRON"

    def test_hitl_ttl_days_default(self, monkeypatch):
        """HITL_PROPOSAL_TTL_DAYS defaults to 7 when not set."""
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.delenv("HITL_PROPOSAL_TTL_DAYS", raising=False)

        import src.config as cfg
        reload(cfg)

        s = cfg.get_settings()
        assert getattr(s, "HITL_PROPOSAL_TTL_DAYS", None) == 7, "HITL_PROPOSAL_TTL_DAYS should default to 7"

    def test_hitl_weekly_cron_default(self, monkeypatch):
        """HITL_WEEKLY_CRON defaults to '0 9 * * 1' (Monday 9am UTC) when not set."""
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.delenv("HITL_WEEKLY_CRON", raising=False)

        import src.config as cfg
        reload(cfg)

        s = cfg.get_settings()
        assert getattr(s, "HITL_WEEKLY_CRON", None) == "0 9 * * 1", "HITL_WEEKLY_CRON should default to '0 9 * * 1'"

    def test_settings_accepts_valid_llm_provider(self, monkeypatch):
        """LLM_PROVIDER must be a supported provider (minimax, openai, anthropic)."""
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("LLM_PROVIDER", "openai")

        import src.config as cfg
        reload(cfg)

        settings = cfg.Settings()
        assert settings.LLM_PROVIDER == "openai"
