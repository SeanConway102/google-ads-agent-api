"""
Tests for scripts/run_research_cycle.py CLI entry point.
The script accepts optional --campaign-id to run for a single campaign.
"""
import sys
from unittest.mock import patch

import pytest


class TestRunResearchCycleScriptArgParsing:
    """Test the CLI script's argument parsing behavior."""

    def test_script_parses_campaign_id_from_sys_argv(self):
        """The script's _main() parses --campaign-id from sys.argv and passes it to run_daily_research."""
        import scripts.run_research_cycle as script_mod

        with patch.object(sys, "argv", ["run_research_cycle.py", "--campaign-id", "test-uuid-123"]):
            # Patch where run_daily_research is resolved (inside _main)
            with patch("src.cron.daily_research.run_daily_research") as mock_run:
                mock_run.return_value = None
                script_mod._main()
                mock_run.assert_called_once_with(target_campaign_id="test-uuid-123")

    def test_script_defaults_to_none_when_no_campaign_id(self):
        """When no --campaign-id is given, run_daily_research is called with None."""
        import scripts.run_research_cycle as script_mod

        with patch.object(sys, "argv", ["run_research_cycle.py"]):
            with patch("src.cron.daily_research.run_daily_research") as mock_run:
                mock_run.return_value = None
                script_mod._main()
                mock_run.assert_called_once_with(target_campaign_id=None)

    def test_script_accepts_campaign_id_with_equals_syntax(self):
        """--campaign-id=uuid syntax is also accepted."""
        import scripts.run_research_cycle as script_mod

        with patch.object(sys, "argv", ["run_research_cycle.py", "--campaign-id=my-uuid"]):
            with patch("src.cron.daily_research.run_daily_research") as mock_run:
                mock_run.return_value = None
                script_mod._main()
                mock_run.assert_called_once_with(target_campaign_id="my-uuid")

    def test_script_returns_without_error_on_success(self):
        """The script completes without error when run_daily_research succeeds."""
        import scripts.run_research_cycle as script_mod

        with patch.object(sys, "argv", ["run_research_cycle.py"]):
            with patch("src.cron.daily_research.run_daily_research") as mock_run:
                mock_run.return_value = None
                # Should not raise
                script_mod._main()

    def test_script_propagates_exceptions_from_run_daily_research(self):
        """If run_daily_research raises, the script propagates the exception."""
        import scripts.run_research_cycle as script_mod

        with patch.object(sys, "argv", ["run_research_cycle.py"]):
            with patch("src.cron.daily_research.run_daily_research") as mock_run:
                mock_run.side_effect = RuntimeError("Database error")
                with pytest.raises(RuntimeError, match="Database error"):
                    script_mod._main()
