"""
RED: Write the failing test first.
Tests for src/cron/weekly_digest.py — weekly HITL digest email cron.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestBuildDigestData:
    """Tests for _build_digest_data()."""

    def test_campaign_with_no_performance_data_returns_zeros(self):
        """Campaign with no performance data should return zero metrics."""
        from src.cron.weekly_digest import _build_digest_data
        result = _build_digest_data(
            campaign={"id": "uuid1", "name": "Test Campaign", "customer_id": "123"},
            performance_data=None,
            pending_count=0,
            approved_count=0,
            rejected_count=0,
        )
        assert result["campaign_name"] == "Test Campaign"
        assert result["impressions"] == 0
        assert result["clicks"] == 0
        assert result["spend"] == 0.0
        assert result["ctr"] == 0.0
        assert result["n_pending"] == 0
        assert result["n_approved"] == 0
        assert result["n_rejected"] == 0

    def test_campaign_with_performance_data_extracts_metrics(self):
        """Campaign with Google Ads performance data returns correct metrics."""
        from src.cron.weekly_digest import _build_digest_data
        result = _build_digest_data(
            campaign={"id": "uuid1", "name": "Test Campaign", "customer_id": "123"},
            performance_data={
                "impressions": 50000,
                "clicks": 1250,
                "cost_micros": 250000000,  # $250.00 in microdollars
            },
            pending_count=2,
            approved_count=3,
            rejected_count=1,
        )
        assert result["impressions"] == 50000
        assert result["clicks"] == 1250
        assert result["spend"] == 250.00
        assert result["ctr"] == 2.5
        assert result["n_pending"] == 2
        assert result["n_approved"] == 3
        assert result["n_rejected"] == 1

    def test_ctr_calculation_avoid_zero_division(self):
        """CTR is 0 when impressions is 0 (avoids zero division)."""
        from src.cron.weekly_digest import _build_digest_data
        result = _build_digest_data(
            campaign={"id": "uuid1", "name": "Test", "customer_id": "123"},
            performance_data={
                "impressions": 0,
                "clicks": 0,
                "cost_micros": 0,
            },
            pending_count=0,
            approved_count=0,
            rejected_count=0,
        )
        assert result["ctr"] == 0.0


class TestCountProposalsByStatus:
    """Tests for _count_proposals_by_status()."""

    def test_returns_correct_counts_for_each_status(self):
        """Returns (pending, approved, rejected) counts from hitl_proposals."""
        mock_adapter = MagicMock()
        mock_adapter.list_hitl_proposals.return_value = [
            {"id": "p1", "status": "pending"},
            {"id": "p2", "status": "pending"},
            {"id": "p3", "status": "approved"},
            {"id": "p4", "status": "rejected"},
            {"id": "p5", "status": "expired"},
        ]

        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter):
            import src.cron.weekly_digest as wd
            pending, approved, rejected = wd._count_proposals_by_status("camp_123")

        assert pending == 2, f"Expected 2 pending, got {pending}"
        assert approved == 1, f"Expected 1 approved, got {approved}"
        assert rejected == 1, f"Expected 1 rejected, got {rejected}"

    def test_returns_zeros_when_no_proposals(self):
        """Returns (0, 0, 0) when campaign has no hitl_proposals."""
        mock_adapter = MagicMock()
        mock_adapter.list_hitl_proposals.return_value = []

        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter):
            import src.cron.weekly_digest as wd
            pending, approved, rejected = wd._count_proposals_by_status("camp_empty")

        assert pending == 0
        assert approved == 0
        assert rejected == 0


class TestCollectActiveHitlCampaigns:
    """Tests for _collect_active_hitl_campaigns()."""

    def test_returns_only_campaigns_with_hitl_enabled_and_email(self):
        """Only campaigns with hitl_enabled=true AND owner_email set are returned."""
        mock_adapter = MagicMock()
        mock_adapter.list_campaigns.return_value = [
            {"id": "uuid1", "name": "Hitl Enabled", "hitl_enabled": True, "owner_email": "a@b.com"},
            {"id": "uuid2", "name": "Hitl Disabled", "hitl_enabled": False, "owner_email": None},
            {"id": "uuid3", "name": "No Email", "hitl_enabled": True, "owner_email": None},
            {"id": "uuid4", "name": "Both Set", "hitl_enabled": True, "owner_email": "c@d.com"},
        ]
        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter):
            import src.cron.weekly_digest as wd
            result = wd._collect_active_hitl_campaigns()

            assert len(result) == 2
            assert all(c["hitl_enabled"] for c in result)
            assert all(c.get("owner_email") for c in result)


class TestSendWeeklyDigests:
    """Tests for send_weekly_digests()."""

    def test_send_weekly_digests_calls_email_service_for_each_campaign(self):
        """send_weekly_digests sends digest emails for all active HITL campaigns."""
        mock_adapter = MagicMock()
        mock_adapter.list_hitl_proposals.side_effect = [
            [],  # Campaign 1: no pending
            [{"id": "p1", "status": "pending"}],  # Campaign 2: 1 pending
        ]
        mock_settings = MagicMock()
        mock_settings.HITL_PROPOSAL_TTL_DAYS = 7
        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter), \
             patch("src.cron.weekly_digest._collect_active_hitl_campaigns") as mock_collect, \
             patch("src.cron.weekly_digest.send_weekly_digest") as mock_email, \
             patch("src.cron.weekly_digest.get_settings", return_value=mock_settings), \
             patch("src.cron.weekly_digest._expire_old_proposals") as mock_expire:

            mock_collect.return_value = [
                {"id": "uuid1", "name": "Campaign 1", "customer_id": "cust1", "hitl_enabled": True, "owner_email": "a@b.com"},
                {"id": "uuid2", "name": "Campaign 2", "customer_id": "cust2", "hitl_enabled": True, "owner_email": "c@d.com"},
            ]
            mock_email.return_value = {"id": "msg_test"}

            from src.cron.weekly_digest import send_weekly_digests
            result = send_weekly_digests()

            assert result == {"sent": 2, "failed": 0}
            assert mock_email.call_count == 2
            mock_email.assert_any_call(
                to_email="a@b.com",
                campaign_name="Campaign 1",
                impressions=0,
                clicks=0,
                spend=0.0,
                ctr=0.0,
                n_approved=0,
                n_rejected=0,
                n_pending=0,
            )

    def test_send_weekly_digests_returns_failure_count_on_error(self):
        """send_weekly_digests increments failed counter when email sending fails."""
        mock_adapter = MagicMock()
        mock_adapter.list_hitl_proposals.return_value = []
        mock_settings = MagicMock()
        mock_settings.HITL_PROPOSAL_TTL_DAYS = 7
        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter), \
             patch("src.cron.weekly_digest._collect_active_hitl_campaigns") as mock_collect, \
             patch("src.cron.weekly_digest.send_weekly_digest") as mock_email, \
             patch("src.cron.weekly_digest.get_settings", return_value=mock_settings), \
             patch("src.cron.weekly_digest._expire_old_proposals") as mock_expire:

            mock_collect.return_value = [
                {"id": "uuid1", "name": "Failing Campaign", "hitl_enabled": True, "owner_email": "a@b.com"},
            ]
            mock_email.side_effect = Exception("SMTP error")

            from src.cron.weekly_digest import send_weekly_digests
            result = send_weekly_digests()

            assert result == {"sent": 0, "failed": 1}
