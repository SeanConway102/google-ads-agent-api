"""
RED: Test that weekly_digest cannot run concurrently with itself.
The cron fires every 5 minutes; if a run takes longer than 5 minutes,
a second instance could start and send duplicate emails.
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os


class TestWeeklyDigestLocking:
    """Test that _acquire_lock prevents concurrent digest runs."""

    def test_if_lock_held_by_alive_process_digest_returns_early(self):
        """If another digest process is already running, send_weekly_digests returns early."""
        from src.cron import weekly_digest as wd

        # Mock the lock file as existing with a live PID (not our PID)
        other_pid = os.getpid() + 9999

        def mock_acquire_lock(lock_path: Path) -> bool:
            # Simulate lock already held by a different process
            return False

        mock_adapter = MagicMock()
        mock_adapter.list_campaigns.return_value = []
        mock_settings = MagicMock()
        mock_settings.HITL_PROPOSAL_TTL_DAYS = 7

        with patch.object(wd, "_adapter", return_value=mock_adapter), \
             patch.object(wd, "_acquire_lock", mock_acquire_lock), \
             patch.object(wd, "get_settings", return_value=mock_settings), \
             patch.object(wd, "_expire_old_proposals") as mock_expire:

            result = wd.send_weekly_digests()

            # Should return early without expiring proposals or sending any emails
            assert result == {"sent": 0, "failed": 0}
            mock_expire.assert_not_called()

    def test_if_lock_free_digest_runs_normally(self):
        """If no lock is held, send_weekly_digests proceeds normally."""
        from src.cron import weekly_digest as wd

        def mock_acquire_lock(lock_path: Path) -> bool:
            return True  # lock acquired

        mock_adapter = MagicMock()
        mock_adapter.list_campaigns.return_value = []
        mock_settings = MagicMock()
        mock_settings.HITL_PROPOSAL_TTL_DAYS = 7

        with patch.object(wd, "_adapter", return_value=mock_adapter), \
             patch.object(wd, "_acquire_lock", mock_acquire_lock), \
             patch.object(wd, "get_settings", return_value=mock_settings), \
             patch.object(wd, "_expire_old_proposals") as mock_expire:

            result = wd.send_weekly_digests()

            # Should proceed and expire old proposals
            mock_expire.assert_called_once()
            assert result == {"sent": 0, "failed": 0}
