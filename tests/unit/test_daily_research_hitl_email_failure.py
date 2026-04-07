"""
RED: Failing tests for hitl_email_failed webhook when send_proposal_email raises.
When the Resend API is down or email delivery fails, operators must be notified
via a webhook so they can manually follow up with the campaign owner.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.agents.debate_state import Phase


class TestHitlEmailFailureWebhook:
    """
    When send_proposal_email raises, a hitl_email_failed webhook must fire
    so operators can detect the failure and manually notify owners.
    """

    def test_email_failure_fires_hitl_email_failed_webhook(self):
        """
        When send_proposal_email raises, webhook_service.dispatch must be called
        with event_type='hitl_email_failed' so operators are alerted.
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
                "impact_summary": "Adding 5 new keyword themes",
                "reasoning": "CTR above 3% suggests headroom",
            },
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = [campaign_row]
        mock_db.search_wiki.return_value = []

        mock_gads = MagicMock()
        mock_gads.get_performance_report.return_value = MagicMock()

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
            def run_cycle(self, *args, **kwargs):
                return mock_state

        # Track dispatched webhooks
        webhook_dispatched = []
        def mock_dispatch(event_type, payload):
            webhook_dispatched.append({"event_type": event_type, "payload": payload})

        def failing_email(**kwargs):
            raise Exception("Resend API rate limit exceeded")

        with \
            patch("src.cron.daily_research.PostgresAdapter", return_value=mock_db), \
            patch("src.cron.daily_research.GoogleAdsClient", return_value=mock_gads), \
            patch("src.cron.daily_research.send_proposal_email", side_effect=failing_email), \
            patch("src.services.webhook_service.PostgresAdapter", return_value=mock_db), \
            patch("src.cron.daily_research.get_settings", return_value=mock_settings), \
            patch("src.config.Settings", return_value=mock_settings), \
            patch("src.cron.daily_research.AdversarialValidator", MockValidator), \
            patch("src.cron.daily_research.WebhookService") as mock_ws_cls:

            mock_ws_instance = MagicMock()
            mock_ws_instance.dispatch = mock_dispatch
            mock_ws_cls.return_value = mock_ws_instance

            run_daily_research()

        hitl_failed = [e for e in webhook_dispatched if e["event_type"] == "hitl_email_failed"]
        assert len(hitl_failed) >= 1, (
            f"Expected at least one 'hitl_email_failed' webhook dispatch, "
            f"got {[e['event_type'] for e in webhook_dispatched]}. "
            "When send_proposal_email raises, operators must be alerted via webhook."
        )
        assert hitl_failed[0]["payload"]["campaign_id"] == campaign_row["campaign_id"]
