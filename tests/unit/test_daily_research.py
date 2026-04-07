"""
RED: Failing tests for daily_research cron script.
Tests the full daily research cycle orchestration.
"""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from src.agents.debate_state import DebateState, Phase


def _mock_get_settings():
    """Return a mock Settings object with required fields."""
    mock_settings = MagicMock()
    mock_settings.MAX_DEBATE_ROUNDS = 5
    return mock_settings


class TestRunDailyResearch:
    """Test run_daily_research() orchestration."""

    def test_processes_each_active_campaign(self):
        """run_daily_research calls the validation cycle for each campaign."""
        from src.cron.daily_research import run_daily_research

        cid = uuid4()
        campaigns = [
            {
                "id": str(cid),
                "campaign_id": "12345",
                "customer_id": "cust_001",
                "name": "Test Campaign",
                "api_key_token": "refresh_token_abc",
                "status": "active",
            }
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = campaigns

        final_state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.CONSENSUS_LOCKED,
            consensus_reached=True,
            round_number=2,
            green_proposals=[{"type": "keyword_add", "target": "shoes"}],
            red_objections=[],
        )

        mock_validator = MagicMock()
        mock_validator.run_cycle.return_value = final_state

        mock_wiki_writer = MagicMock()
        mock_webhook_service = MagicMock()
        mock_audit_service = MagicMock()
        mock_gads_client = MagicMock()
        mock_gads_client.get_performance_report.return_value = MagicMock(
            impressions=100, clicks=100, ctr=0.05, spend_micros=5000000,
            conversions=2.0, avg_cpc_micros=50000,
        )

        import src.cron.daily_research as dr
        import src.config as config_module

        original_get_settings = config_module.get_settings
        original_dr_get_settings = dr.get_settings
        config_module.get_settings = _mock_get_settings
        dr.get_settings = _mock_get_settings

        original_modules = {
            "PostgresAdapter": dr.PostgresAdapter,
            "GoogleAdsClient": dr.GoogleAdsClient,
            "AdversarialValidator": dr.AdversarialValidator,
            "WikiWriter": dr.WikiWriter,
            "WebhookService": dr.WebhookService,
            "AuditService": dr.AuditService,
        }

        dr.PostgresAdapter = MagicMock(return_value=mock_db)
        dr.GoogleAdsClient = MagicMock(return_value=mock_gads_client)
        dr.AdversarialValidator = MagicMock(return_value=mock_validator)
        dr.WikiWriter = MagicMock(return_value=mock_wiki_writer)
        dr.WebhookService = MagicMock(return_value=mock_webhook_service)
        dr.AuditService = MagicMock(return_value=mock_audit_service)

        try:
            run_daily_research()
            mock_validator.run_cycle.assert_called_once()
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings

    def test_consensus_reached_executes_and_fires_webhook(self):
        """When consensus is reached, approved proposals are executed and webhook fired."""
        from src.cron.daily_research import run_daily_research

        cid = uuid4()
        campaigns = [
            {
                "id": str(cid),
                "campaign_id": "12345",
                "customer_id": "cust_002",
                "name": "Campaign 2",
                "api_key_token": "token",
                "status": "active",
            }
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = campaigns
        mock_db.search_wiki.return_value = []

        final_state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.CONSENSUS_LOCKED,
            consensus_reached=True,
            round_number=1,
            green_proposals=[{"type": "keyword_add", "target": "running shoes"}],
            red_objections=[],
        )

        mock_validator = MagicMock()
        mock_validator.run_cycle.return_value = final_state

        mock_wiki_writer = MagicMock()
        mock_webhook_service = MagicMock()
        mock_audit_service = MagicMock()
        mock_gads_client = MagicMock()
        mock_gads_client.get_performance_report.return_value = MagicMock(
            impressions=0, clicks=0, ctr=0.0, spend_micros=0,
            conversions=0.0, avg_cpc_micros=0,
        )

        import src.cron.daily_research as dr
        import src.config as config_module

        original_get_settings = config_module.get_settings
        original_dr_get_settings = dr.get_settings
        config_module.get_settings = _mock_get_settings
        dr.get_settings = _mock_get_settings

        original_modules = {
            "PostgresAdapter": dr.PostgresAdapter,
            "GoogleAdsClient": dr.GoogleAdsClient,
            "AdversarialValidator": dr.AdversarialValidator,
            "WikiWriter": dr.WikiWriter,
            "WebhookService": dr.WebhookService,
            "AuditService": dr.AuditService,
        }

        dr.PostgresAdapter = MagicMock(return_value=mock_db)
        dr.GoogleAdsClient = MagicMock(return_value=mock_gads_client)
        dr.AdversarialValidator = MagicMock(return_value=mock_validator)
        dr.WikiWriter = MagicMock(return_value=mock_wiki_writer)
        dr.WebhookService = MagicMock(return_value=mock_webhook_service)
        dr.AuditService = MagicMock(return_value=mock_audit_service)

        try:
            run_daily_research()
            mock_webhook_service.dispatch.assert_called()
            dispatch_calls = mock_webhook_service.dispatch.call_args_list
            event_names = [call[0][0] for call in dispatch_calls]
            assert "consensus_reached" in event_names
            mock_audit_service.log_decision.assert_called_once()
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings

    def test_pending_manual_review_fires_manual_review_webhook(self):
        """When max rounds reached, manual_review_required webhook is fired."""
        from src.cron.daily_research import run_daily_research

        cid = uuid4()
        campaigns = [
            {
                "id": str(cid),
                "campaign_id": "12345",
                "customer_id": "cust_003",
                "name": "Campaign 3",
                "api_key_token": "token",
                "status": "active",
            }
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = campaigns
        mock_db.search_wiki.return_value = []

        final_state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.PENDING_MANUAL_REVIEW,
            consensus_reached=False,
            round_number=5,
            green_proposals=[{"type": "keyword_add"}],
            red_objections=[{"objection": "too risky"}],
        )

        mock_validator = MagicMock()
        mock_validator.run_cycle.return_value = final_state

        mock_wiki_writer = MagicMock()
        mock_webhook_service = MagicMock()
        mock_audit_service = MagicMock()
        mock_gads_client = MagicMock()
        mock_gads_client.get_performance_report.return_value = MagicMock(
            impressions=0, clicks=0, ctr=0.0, spend_micros=0,
            conversions=0.0, avg_cpc_micros=0,
        )

        import src.cron.daily_research as dr
        import src.config as config_module

        original_get_settings = config_module.get_settings
        original_dr_get_settings = dr.get_settings
        config_module.get_settings = _mock_get_settings
        dr.get_settings = _mock_get_settings

        original_modules = {
            "PostgresAdapter": dr.PostgresAdapter,
            "GoogleAdsClient": dr.GoogleAdsClient,
            "AdversarialValidator": dr.AdversarialValidator,
            "WikiWriter": dr.WikiWriter,
            "WebhookService": dr.WebhookService,
            "AuditService": dr.AuditService,
        }

        dr.PostgresAdapter = MagicMock(return_value=mock_db)
        dr.GoogleAdsClient = MagicMock(return_value=mock_gads_client)
        dr.AdversarialValidator = MagicMock(return_value=mock_validator)
        dr.WikiWriter = MagicMock(return_value=mock_wiki_writer)
        dr.WebhookService = MagicMock(return_value=mock_webhook_service)
        dr.AuditService = MagicMock(return_value=mock_audit_service)

        try:
            run_daily_research()
            dispatch_calls = mock_webhook_service.dispatch.call_args_list
            event_names = [call[0][0] for call in dispatch_calls]
            assert "manual_review_required" in event_names
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings

    def test_campaign_error_does_not_stop_other_campaigns(self):
        """If one campaign raises, the loop continues to the next campaign."""
        from src.cron.daily_research import run_daily_research

        cid1 = uuid4()
        cid2 = uuid4()
        campaigns = [
            {
                "id": str(cid1),
                "campaign_id": "12345",
                "customer_id": "cust_fail",
                "name": "Failing Campaign",
                "api_key_token": "bad_token",
                "status": "active",
            },
            {
                "id": str(cid2),
                "campaign_id": "67890",
                "customer_id": "cust_ok",
                "name": "OK Campaign",
                "api_key_token": "good_token",
                "status": "active",
            },
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = campaigns

        good_state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid2,
            phase=Phase.CONSENSUS_LOCKED,
            consensus_reached=True,
            round_number=1,
            green_proposals=[],
            red_objections=[],
        )

        mock_validator = MagicMock()
        mock_validator.run_cycle.side_effect = [
            Exception("Google Ads API error"),
            good_state,
        ]

        mock_wiki_writer = MagicMock()
        mock_webhook_service = MagicMock()
        mock_audit_service = MagicMock()
        mock_gads_client = MagicMock()
        mock_gads_client.get_performance_report.return_value = MagicMock(
            impressions=0, clicks=0, ctr=0.0, spend_micros=0,
            conversions=0.0, avg_cpc_micros=0,
        )

        import src.cron.daily_research as dr
        import src.config as config_module

        original_get_settings = config_module.get_settings
        original_dr_get_settings = dr.get_settings
        config_module.get_settings = _mock_get_settings
        dr.get_settings = _mock_get_settings

        original_modules = {
            "PostgresAdapter": dr.PostgresAdapter,
            "GoogleAdsClient": dr.GoogleAdsClient,
            "AdversarialValidator": dr.AdversarialValidator,
            "WikiWriter": dr.WikiWriter,
            "WebhookService": dr.WebhookService,
            "AuditService": dr.AuditService,
        }

        dr.PostgresAdapter = MagicMock(return_value=mock_db)
        dr.GoogleAdsClient = MagicMock(return_value=mock_gads_client)
        dr.AdversarialValidator = MagicMock(return_value=mock_validator)
        dr.WikiWriter = MagicMock(return_value=mock_wiki_writer)
        dr.WebhookService = MagicMock(return_value=mock_webhook_service)
        dr.AuditService = MagicMock(return_value=mock_audit_service)

        try:
            run_daily_research()
            assert mock_validator.run_cycle.call_count == 2
            dispatch_calls = mock_webhook_service.dispatch.call_args_list
            event_names = [call[0][0] for call in dispatch_calls]
            assert "cycle_error" in event_names
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings