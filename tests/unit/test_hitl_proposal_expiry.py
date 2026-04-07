"""
RED: Test for HITL proposal auto-expiry.
Proposals older than HITL_PROPOSAL_TTL_DAYS should be marked expired.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


class TestExpireOldProposals:
    """Tests for _expire_old_proposals()."""

    def test_proposal_newer_than_ttl_is_not_expired(self):
        """A proposal created today should not be marked expired."""
        from src.cron.weekly_digest import _expire_old_proposals
        mock_adapter = MagicMock()
        now = datetime.now(timezone.utc)
        mock_adapter.list_campaigns.return_value = [
            {"id": "camp1", "hitl_enabled": True, "owner_email": "a@b.com"}
        ]
        mock_adapter.list_hitl_proposals.return_value = [
            {
                "id": "uuid1",
                "campaign_id": "camp1",
                "status": "pending",
                "created_at": now.isoformat(),
            }
        ]
        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter):
            import src.cron.weekly_digest as wd
            result = wd._expire_old_proposals(ttl_days=7)

            assert result["expired"] == 0
            mock_adapter.update_hitl_proposal_status.assert_not_called()

    def test_proposal_older_than_ttl_is_expired(self):
        """A proposal created 10 days ago (TTL=7) should be marked expired."""
        from src.cron.weekly_digest import _expire_old_proposals
        mock_adapter = MagicMock()
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        mock_adapter.list_campaigns.return_value = [
            {"id": "camp1", "hitl_enabled": True, "owner_email": "a@b.com"}
        ]
        mock_adapter.list_hitl_proposals.return_value = [
            {
                "id": "uuid1",
                "campaign_id": "camp1",
                "status": "pending",
                "created_at": old_date,
            }
        ]
        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter):
            import src.cron.weekly_digest as wd
            result = wd._expire_old_proposals(ttl_days=7)

            assert result["expired"] == 1
            mock_adapter.update_hitl_proposal_status.assert_called_once_with(
                "uuid1", "expired"
            )

    def test_proposal_already_decided_is_not_modified(self):
        """Approved/rejected proposals are not touched by expiry."""
        from src.cron.weekly_digest import _expire_old_proposals
        mock_adapter = MagicMock()
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        mock_adapter.list_campaigns.return_value = [
            {"id": "camp1", "hitl_enabled": True, "owner_email": "a@b.com"}
        ]
        mock_adapter.list_hitl_proposals.return_value = [
            {
                "id": "uuid1",
                "campaign_id": "camp1",
                "status": "approved",
                "created_at": old_date,
            }
        ]
        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter):
            import src.cron.weekly_digest as wd
            result = wd._expire_old_proposals(ttl_days=7)

            assert result["expired"] == 0
            mock_adapter.update_hitl_proposal_status.assert_not_called()

    def test_multiple_proposals_expired_correctly(self):
        """Mixed old/new and pending/approved — only old pending are expired."""
        from src.cron.weekly_digest import _expire_old_proposals
        mock_adapter = MagicMock()
        now = datetime.now(timezone.utc)
        mock_adapter.list_campaigns.return_value = [
            {"id": "camp1", "hitl_enabled": True, "owner_email": "a@b.com"}
        ]
        mock_adapter.list_hitl_proposals.return_value = [
            {"id": "uuid1", "status": "pending", "created_at": (now - timedelta(days=10)).isoformat()},
            {"id": "uuid2", "status": "pending", "created_at": (now - timedelta(days=5)).isoformat()},
            {"id": "uuid3", "status": "approved", "created_at": (now - timedelta(days=10)).isoformat()},
            {"id": "uuid4", "status": "pending", "created_at": (now - timedelta(days=8)).isoformat()},
        ]
        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter):
            import src.cron.weekly_digest as wd
            result = wd._expire_old_proposals(ttl_days=7)

            assert result["expired"] == 2
            called_ids = {
                call[0][0]
                for call in mock_adapter.update_hitl_proposal_status.call_args_list
            }
            assert called_ids == {"uuid1", "uuid4"}
