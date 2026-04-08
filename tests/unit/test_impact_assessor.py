"""
RED: Write the failing test first.
Tests for src/services/impact_assessor.py — threshold rules evaluator for HITL.
"""


class TestIsAboveThreshold:
    """Tests for is_above_threshold()."""

    def test_budget_update_above_20_percent_is_above_threshold(self):
        """Budget change >20% is above threshold."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="budget_update",
            current_value=100.0,
            proposed_value=125.0,
        )
        assert result is True

    def test_budget_update_exactly_20_percent_is_not_above_threshold(self):
        """Budget change exactly 20% is NOT above threshold."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="budget_update",
            current_value=100.0,
            proposed_value=120.0,
        )
        assert result is False

    def test_budget_update_below_20_percent_is_not_above_threshold(self):
        """Budget change <20% is NOT above threshold."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="budget_update",
            current_value=100.0,
            proposed_value=115.0,
        )
        assert result is False

    def test_budget_update_zero_current_returns_false_without_division(self):
        """Budget update with current_value=0 returns False (avoids zero division)."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="budget_update",
            current_value=0,
            proposed_value=100.0,
        )
        assert result is False

    def test_budget_update_negative_current_returns_false(self):
        """Budget update with negative current_value returns False (debt scenario)."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="budget_update",
            current_value=-50.0,
            proposed_value=0.0,
        )
        assert result is False

    def test_keyword_add_above_5_is_above_threshold(self):
        """Adding >5 keywords at once is above threshold."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="keyword_add",
            count=6,
        )
        assert result is True

    def test_keyword_add_exactly_5_is_not_above_threshold(self):
        """Adding exactly 5 keywords is NOT above threshold."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="keyword_add",
            count=5,
        )
        assert result is False

    def test_keyword_add_3_is_not_above_threshold(self):
        """Adding 3 keywords is below threshold."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="keyword_add",
            count=3,
        )
        assert result is False

    def test_keyword_remove_always_above_threshold(self):
        """Any keyword removal is above threshold."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="keyword_remove",
            count=1,
        )
        assert result is True

        result2 = is_above_threshold(
            proposal_type="keyword_remove",
            count=10,
        )
        assert result2 is True

    def test_match_type_change_always_above_threshold(self):
        """Any broad-to-exact match type change is above threshold."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="match_type_change",
            count=1,
        )
        assert result is True

    def test_unknown_proposal_type_not_above_threshold(self):
        """Unknown proposal types default to NOT above threshold."""
        from src.services.impact_assessor import is_above_threshold
        result = is_above_threshold(
            proposal_type="bid_adjustment",
        )
        assert result is False


class TestShouldRequireApproval:
    """Tests for should_require_approval() — checks hitl_enabled AND above_threshold."""

    def test_above_threshold_and_hitl_enabled_requires_approval(self, monkeypatch):
        """Above-threshold with hitl_enabled=true → requires approval."""
        import os
        from importlib import reload
        import src.config as cfg
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("HITL_ENABLED", "true")
        reload(cfg)
        cfg.get_settings.cache_clear()
        s = cfg.get_settings()
        s.HITL_ENABLED = True

        from src.services.impact_assessor import should_require_approval
        result = should_require_approval(
            proposal_type="budget_update",
            current_value=100.0,
            proposed_value=150.0,
        )
        assert result is True

    def test_below_threshold_with_hitl_enabled_does_not_require_approval(self, monkeypatch):
        """Below-threshold with hitl_enabled=true → does NOT require approval."""
        import os
        from importlib import reload
        import src.config as cfg
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("HITL_ENABLED", "true")
        reload(cfg)
        cfg.get_settings.cache_clear()
        s = cfg.get_settings()
        s.HITL_ENABLED = True

        from src.services.impact_assessor import should_require_approval
        result = should_require_approval(
            proposal_type="budget_update",
            current_value=100.0,
            proposed_value=110.0,
        )
        assert result is False

    def test_above_threshold_with_hitl_disabled_does_not_require_approval(self, monkeypatch):
        """Above-threshold with hitl_enabled=false → does NOT require approval."""
        from importlib import reload
        import src.config as cfg
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("HITL_ENABLED", "false")
        reload(cfg)
        cfg.get_settings.cache_clear()
        s = cfg.get_settings()
        s.HITL_ENABLED = False

        # Re-import to pick up the fresh get_settings reference
        import importlib
        import src.services.impact_assessor as ia
        reload(ia)

        result = ia.should_require_approval(
            proposal_type="budget_update",
            current_value=100.0,
            proposed_value=150.0,
        )
        assert result is False
