"""
RED: Write the failing test first.
Tests for src/cron/weekly_digest.py — weekly HITL digest email cron.
"""
import os
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


class TestSendWeeklyDigestsCallsGoogleAds:
    """Tests that send_weekly_digests fetches live Google Ads performance data."""

    def test_fetches_performance_data_from_google_ads_for_each_campaign(self):
        """
        send_weekly_digests must call GoogleAdsClient for each HITL campaign
        and pass the performance data to _build_digest_data.

        Currently performance_data=None is hardcoded — this test will fail
        until the real Google Ads fetch is implemented.
        """
        from src.cron.weekly_digest import send_weekly_digests

        mock_adapter = MagicMock()
        mock_adapter.list_hitl_proposals.return_value = []

        mock_gads_instance = MagicMock()
        mock_gads_instance.get_performance_report.return_value = {
            "impressions": 100000,
            "clicks": 3500,
            "cost_micros": 175000000,  # $175.00
        }

        mock_settings = MagicMock()
        mock_settings.HITL_PROPOSAL_TTL_DAYS = 7

        with patch("src.cron.weekly_digest._adapter", return_value=mock_adapter), \
             patch("src.cron.weekly_digest._collect_active_hitl_campaigns") as mock_collect, \
             patch("src.cron.weekly_digest.send_weekly_digest") as mock_email, \
             patch("src.cron.weekly_digest.get_settings", return_value=mock_settings), \
             patch("src.cron.weekly_digest._expire_old_proposals"), \
             patch("src.cron.weekly_digest.GoogleAdsClient", return_value=mock_gads_instance):

            mock_collect.return_value = [
                {
                    "id": "uuid1",
                    "name": "Test Campaign",
                    "customer_id": "cust_123",
                    "campaign_id": "cmp_abc",
                    "hitl_enabled": True,
                    "owner_email": "owner@example.com",
                },
            ]

            send_weekly_digests()

            # GoogleAdsClient must be instantiated with the campaign's customer_id
            from src.cron.weekly_digest import GoogleAdsClient
            GoogleAdsClient.assert_called_once_with(customer_id="cust_123")

            # get_performance_report must be called to fetch live data
            mock_gads_instance.get_performance_report.assert_called_once()

            # The email must contain the real performance metrics, not zeros
            # (pending=0, approved=0, rejected=0 from empty proposals list)
            mock_email.assert_called_once()
            email_kwargs = mock_email.call_args.kwargs
            assert email_kwargs["impressions"] == 100000, (
                f"Expected impressions=100000 from Google Ads, got {email_kwargs['impressions']}. "
                "performance_data is still None — Google Ads fetch is not implemented."
            )
            assert email_kwargs["clicks"] == 3500
            assert email_kwargs["spend"] == 175.0
            assert email_kwargs["ctr"] == 3.5  # 3500/100000*100


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


class TestExpireOldProposals:
    """Tests for _expire_old_proposals()."""

    def test_expires_pending_proposals_older_than_ttl_days(self):
        """Proposals with status=pending and created_at > ttl_days ago should be marked expired."""
        from datetime import datetime, timezone, timedelta
        from src.cron.weekly_digest import _expire_old_proposals
        import src.cron.weekly_digest as wd

        old_proposal = {
            "id": "proposal_old",
            "status": "pending",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        }
        recent_proposal = {
            "id": "proposal_recent",
            "status": "pending",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        }

        mock_adapter = MagicMock()
        mock_adapter.list_campaigns.return_value = [
            {"id": "camp_001", "name": "Test"},
        ]
        mock_adapter.list_hitl_proposals.side_effect = [
            [old_proposal, recent_proposal],
        ]

        with patch.object(wd, "_adapter", return_value=mock_adapter):
            result = _expire_old_proposals(ttl_days=7)

        assert result["expired"] == 1
        mock_adapter.update_hitl_proposal_status.assert_called_once_with("proposal_old", "expired")

    def test_does_not_expire_non_pending_proposals(self):
        """Proposals that are already approved/rejected/expired are not touched."""
        from datetime import datetime, timezone, timedelta
        from src.cron.weekly_digest import _expire_old_proposals
        import src.cron.weekly_digest as wd

        approved_proposal = {
            "id": "proposal_approved",
            "status": "approved",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        }

        mock_adapter = MagicMock()
        mock_adapter.list_campaigns.return_value = [{"id": "camp_001"}]
        mock_adapter.list_hitl_proposals.return_value = [approved_proposal]

        with patch.object(wd, "_adapter", return_value=mock_adapter):
            result = _expire_old_proposals(ttl_days=7)

        assert result["expired"] == 0
        mock_adapter.update_hitl_proposal_status.assert_not_called()

    def test_handles_naive_datetime_created_at(self):
        """created_at without timezone info should be treated as UTC."""
        from datetime import datetime, timezone, timedelta
        from src.cron.weekly_digest import _expire_old_proposals
        import src.cron.weekly_digest as wd

        naive_proposal = {
            "id": "proposal_naive",
            "status": "pending",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat().replace("+00:00", ""),
        }

        mock_adapter = MagicMock()
        mock_adapter.list_campaigns.return_value = [{"id": "camp_001"}]
        mock_adapter.list_hitl_proposals.return_value = [naive_proposal]

        with patch.object(wd, "_adapter", return_value=mock_adapter):
            result = _expire_old_proposals(ttl_days=7)

        assert result["expired"] == 1

    def test_handles_missing_created_at(self):
        """Proposals without created_at field are skipped without error."""
        from src.cron.weekly_digest import _expire_old_proposals
        import src.cron.weekly_digest as wd

        no_date_proposal = {
            "id": "proposal_no_date",
            "status": "pending",
        }

        mock_adapter = MagicMock()
        mock_adapter.list_campaigns.return_value = [{"id": "camp_001"}]
        mock_adapter.list_hitl_proposals.return_value = [no_date_proposal]

        with patch.object(wd, "_adapter", return_value=mock_adapter):
            result = _expire_old_proposals(ttl_days=7)

        assert result["expired"] == 0


class TestAcquireLock:
    """Tests for _acquire_lock()."""

    def test_returns_false_when_lock_file_held_by_alive_process(self):
        """When lock file exists and contains a live PID, _acquire_lock returns False."""
        from src.cron.weekly_digest import _acquire_lock
        import src.cron.weekly_digest as wd

        with patch.object(wd, "_is_process_alive", return_value=True):
            mock_lock_path = MagicMock()
            mock_lock_path.exists.return_value = True
            mock_lock_path.read_text.return_value = str(os.getpid() + 9999)  # different PID
            mock_lock_path.parent.mkdir = MagicMock()
            result = _acquire_lock(mock_lock_path)

        assert result is False

    def test_returns_true_when_lock_file_stale(self):
        """When lock file exists but PID is dead, lock is acquired (overwrites stale lock)."""
        from src.cron.weekly_digest import _acquire_lock
        import src.cron.weekly_digest as wd

        with patch.object(wd, "_is_process_alive", return_value=False):
            mock_lock_path = MagicMock()
            mock_lock_path.exists.return_value = True
            mock_lock_path.read_text.return_value = str(os.getpid() + 9999)
            mock_lock_path.parent.mkdir = MagicMock()
            mock_lock_path.write_text = MagicMock()
            result = _acquire_lock(mock_lock_path)

        assert result is True
        mock_lock_path.write_text.assert_called_once()

    def test_returns_true_when_no_lock_file(self):
        """When no lock file exists, lock is acquired successfully."""
        from src.cron.weekly_digest import _acquire_lock
        import src.cron.weekly_digest as wd

        mock_lock_path = MagicMock()
        mock_lock_path.exists.return_value = False
        mock_lock_path.parent.mkdir = MagicMock()
        mock_lock_path.write_text = MagicMock()
        result = _acquire_lock(mock_lock_path)

        assert result is True
        mock_lock_path.write_text.assert_called_once()

    def test_returns_false_when_write_fails(self):
        """When lock file write fails (OSError), returns False without crashing."""
        from src.cron.weekly_digest import _acquire_lock
        import src.cron.weekly_digest as wd

        mock_lock_path = MagicMock()
        mock_lock_path.exists.return_value = False
        mock_lock_path.parent.mkdir = MagicMock()
        mock_lock_path.write_text.side_effect = OSError("disk full")
        result = _acquire_lock(mock_lock_path)

        assert result is False
