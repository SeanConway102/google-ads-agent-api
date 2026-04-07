"""
Tests that daily research sends HITL proposal emails when PENDING_MANUAL_REVIEW is reached.

The flow:
- Coordinator escalates to PENDING_MANUAL_REVIEW
- _send_hitl_emails sends approval emails to owner for each green_proposal
- Owner replies via email (approve/reject/question) → handled by email_replies.py
- Question replies create hitl_proposals records via reply_handler.py
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.agents.debate_state import Phase


class TestDailyResearchPendingManualReviewEmailsOwner:
    """
    When the coordinator escalates to PENDING_MANUAL_REVIEW and hitl_enabled=True,
    send_proposal_email must be called for each pending proposal.
    """

    def test_pending_manual_review_sends_email_when_hitl_enabled(self):
        """
        PENDING_MANUAL_REVIEW + hitl_enabled=True → email sent to owner
        for each green_proposal.
        """
        from src.cron.daily_research import run_daily_research

        campaign_uuid = uuid.uuid4()
        campaign_row = {
            "id": campaign_uuid,
            "campaign_id": "cmp_001",
            "customer_id": "cust_001",
            "name": "Test Campaign",
            "status": "active",
            "campaign_type": "search",
            "owner_tag": "marketing",
            "owner_email": "owner@example.com",
            "hitl_enabled": True,
            "created_at": datetime(2026, 4, 6, 10, 0, 0),
            "last_synced_at": datetime(2026, 4, 6, 8, 0, 0),
            "last_reviewed_at": datetime(2026, 4, 5, 8, 0, 0),
        }
        green_proposals = [
            {
                "type": "keyword_add",
                "target": "shoes",
                "ad_group_id": "ag_001",
                "keywords": ["shoes"],
                "impact_summary": "Adding 5 new keyword themes",
                "reasoning": "CTR above 3% suggests headroom",
            },
            {
                "type": "bid_update",
                "updates": [{"resource_name": "kw1", "cpc_bid_micros": 150000}],
                "impact_summary": "Increase CPC by 15%",
                "reasoning": " CPA trending below target",
            },
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = [campaign_row]
        mock_db.search_wiki.return_value = []
        mock_db.get_latest_debate_state_any_cycle.return_value = {
            "id": 1,
            "phase": Phase.PENDING_MANUAL_REVIEW.value,
            "round_number": 5,
            "green_proposals": green_proposals,
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_gads = MagicMock()
        mock_gads.get_performance_report.return_value = MagicMock()
        mock_gads.list_keywords.return_value = []

        sent_emails = []
        def track_email(**kwargs):
            sent_emails.append(kwargs)
            return {"id": "msg_123"}

        # Mock state object returned by run_cycle (synchronous, not a coroutine)
        mock_state = MagicMock()
        mock_state.phase = Phase.PENDING_MANUAL_REVIEW
        mock_state.consensus_reached = False
        mock_state.round_number = 5
        mock_state.green_proposals = green_proposals
        mock_state.red_objections = []

        def sync_run_cycle(*args, **kwargs):
            return mock_state

        mock_settings = MagicMock()
        mock_settings.ADMIN_API_KEY = "test-key"
        mock_settings.GLOBAL_OWNER_EMAIL = None

        # Mock AdversarialValidator class with synchronous run_cycle
        class MockValidator:
            def __init__(self, *args, **kwargs):
                pass
            async def run_cycle(self, *args, **kwargs):
                return mock_state

        with patch("src.cron.daily_research.PostgresAdapter", return_value=mock_db), \
             patch("src.cron.daily_research.GoogleAdsClient", return_value=mock_gads), \
             patch("src.cron.daily_research.send_proposal_email", side_effect=track_email), \
             patch("src.services.webhook_service.PostgresAdapter", return_value=mock_db), \
             patch("src.config.get_settings", return_value=mock_settings), \
             patch("src.config.Settings", return_value=mock_settings), \
             patch("src.cron.daily_research.AdversarialValidator", MockValidator):

            run_daily_research()

        assert len(sent_emails) == 2, (
            f"Expected 2 emails (one per proposal), got {len(sent_emails)}. "
            f"route_proposals is defined but never called — HITL emails are dead code."
        )
        # Each email must be to the owner
        for email_kwargs in sent_emails:
            assert email_kwargs["to_email"] == "owner@example.com"

    def test_pending_manual_review_skips_email_when_hitl_disabled(self):
        """
        When hitl_enabled=False, send_proposal_email must NOT be called
        (proposals are handled via auto-execution, not human approval).
        """
        from src.cron.daily_research import run_daily_research

        campaign_uuid = uuid.uuid4()
        campaign_row = {
            "id": campaign_uuid,
            "campaign_id": "cmp_001",
            "customer_id": "cust_001",
            "name": "Test Campaign",
            "status": "active",
            "campaign_type": "search",
            "owner_tag": "marketing",
            "owner_email": "owner@example.com",
            "hitl_enabled": False,  # <-- HITL disabled
            "created_at": datetime(2026, 4, 6, 10, 0, 0),
            "last_synced_at": datetime(2026, 4, 6, 8, 0, 0),
            "last_reviewed_at": datetime(2026, 4, 5, 8, 0, 0),
        }
        green_proposals = [
            {
                "type": "keyword_add",
                "target": "shoes",
                "impact_summary": "Adding 5 new keyword themes",
                "reasoning": "CTR above 3% suggests headroom",
            },
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = [campaign_row]
        mock_db.search_wiki.return_value = []
        mock_db.get_latest_debate_state_any_cycle.return_value = {
            "id": 1,
            "phase": Phase.PENDING_MANUAL_REVIEW.value,
            "round_number": 5,
            "green_proposals": green_proposals,
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_gads = MagicMock()
        mock_gads.get_performance_report.return_value = MagicMock()
        mock_gads.list_keywords.return_value = []

        sent_emails = []
        def track_email(**kwargs):
            sent_emails.append(kwargs)
            return {"id": "msg_123"}

        mock_settings = MagicMock()
        mock_settings.ADMIN_API_KEY = "test-key"
        mock_settings.GLOBAL_OWNER_EMAIL = None

        # Mock state for the disabled test too (to avoid coroutine warnings)
        mock_state = MagicMock()
        mock_state.phase = Phase.PENDING_MANUAL_REVIEW
        mock_state.consensus_reached = False
        mock_state.round_number = 5
        mock_state.green_proposals = green_proposals
        mock_state.red_objections = []

        class MockValidator:
            def __init__(self, *args, **kwargs):
                pass
            async def run_cycle(self, *args, **kwargs):
                return mock_state

        with patch("src.cron.daily_research.PostgresAdapter", return_value=mock_db), \
             patch("src.cron.daily_research.GoogleAdsClient", return_value=mock_gads), \
             patch("src.cron.daily_research.send_proposal_email", side_effect=track_email), \
             patch("src.services.webhook_service.PostgresAdapter", return_value=mock_db), \
             patch("src.config.get_settings", return_value=mock_settings), \
             patch("src.config.Settings", return_value=mock_settings), \
             patch("src.cron.daily_research.AdversarialValidator", MockValidator):

            run_daily_research()

        assert len(sent_emails) == 0, (
            "send_proposal_email should not be called when hitl_enabled=False"
        )


class TestDailyResearchMissingOwnerEmail:
    """When hitl_enabled=True but owner_email is None, the cycle must not silently fail."""

    def test_missing_owner_email_logs_warning(self, capsys):
        """
        When hitl_enabled=True but owner_email is None, no email can be sent.
        The cycle must log a warning so operators know the owner was not notified.
        Without the fix, the function returns silently — no email, no warning,
        owner is never told their approval is needed.
        """
        from src.cron.daily_research import run_daily_research

        campaign_uuid = uuid.uuid4()
        campaign_row = {
            "id": campaign_uuid,
            "campaign_id": "cmp_001",
            "customer_id": "cust_001",
            "name": "Test Campaign",
            "status": "active",
            "campaign_type": "search",
            "owner_tag": "marketing",
            "owner_email": None,  # owner_email missing
            "hitl_enabled": True,  # HITL enabled but no email configured
            "created_at": datetime(2026, 4, 6, 10, 0, 0),
            "last_synced_at": datetime(2026, 4, 6, 8, 0, 0),
            "last_reviewed_at": datetime(2026, 4, 5, 8, 0, 0),
        }
        green_proposals = [
            {
                "type": "keyword_add",
                "target": "shoes",
                "impact_summary": "Adding 5 new keyword themes",
                "reasoning": "CTR above 3% suggests headroom",
            },
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = [campaign_row]
        mock_db.search_wiki.return_value = []
        mock_db.get_latest_debate_state_any_cycle.return_value = {
            "id": 1,
            "phase": Phase.PENDING_MANUAL_REVIEW.value,
            "round_number": 5,
            "green_proposals": green_proposals,
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_gads = MagicMock()
        mock_gads.get_performance_report.return_value = MagicMock()
        mock_gads.list_keywords.return_value = []

        sent_emails = []
        def track_email(**kwargs):
            sent_emails.append(kwargs)
            return {"id": "msg_123"}

        mock_settings = MagicMock()
        mock_settings.ADMIN_API_KEY = "test-key"
        mock_settings.GLOBAL_OWNER_EMAIL = None

        mock_state = MagicMock()
        mock_state.phase = Phase.PENDING_MANUAL_REVIEW
        mock_state.consensus_reached = False
        mock_state.round_number = 5
        mock_state.green_proposals = green_proposals
        mock_state.red_objections = []

        class MockValidator:
            def __init__(self, *args, **kwargs):
                pass
            async def run_cycle(self, *args, **kwargs):
                return mock_state

        with patch("src.cron.daily_research.PostgresAdapter", return_value=mock_db), \
             patch("src.cron.daily_research.GoogleAdsClient", return_value=mock_gads), \
             patch("src.cron.daily_research.send_proposal_email", side_effect=track_email), \
             patch("src.services.webhook_service.PostgresAdapter", return_value=mock_db), \
             patch("src.config.get_settings", return_value=mock_settings), \
             patch("src.config.Settings", return_value=mock_settings), \
             patch("src.cron.daily_research.AdversarialValidator", MockValidator):

            run_daily_research()

        captured = capsys.readouterr()
        # Check that stdout contains a warning about missing owner_email or HITL
        assert "owner" in captured.out.lower() or "hitl" in captured.out.lower(), (
            f"Expected a warning about missing owner_email in stdout, got: {captured.out!r}"
        )
