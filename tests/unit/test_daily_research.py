"""
RED: Failing tests for daily_research cron script.
Tests the full daily research cycle orchestration.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
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
        async def mock_run_cycle_consensus(*args, **kwargs):
            return final_state
        mock_validator.run_cycle = mock_run_cycle_consensus

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

        # Directly construct the validator instance so it has async run_cycle.
        # Patching dr.AdversarialValidator as a class and setting return_value
        # is fragile: pytest-asyncio strict mode can cause the mock chain to
        # return a fresh MagicMock instead of our configured mock_validator.
        async def mock_run_cycle(*args, **kwargs):
            return final_state
        mock_validator_instance = MagicMock()
        mock_validator_instance.run_cycle = mock_run_cycle

        dr.PostgresAdapter = MagicMock(return_value=mock_db)
        dr.GoogleAdsClient = MagicMock(return_value=mock_gads_client)
        dr.AdversarialValidator = MagicMock(return_value=mock_validator_instance)
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

    def test_empty_campaign_list_returns_early(self):
        """When no active campaigns exist, run_daily_research returns early without error."""
        from src.cron.daily_research import run_daily_research

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = []

        mock_wiki_writer = MagicMock()
        mock_webhook_service = MagicMock()
        mock_audit_service = MagicMock()
        mock_gads_client = MagicMock()

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
        dr.AdversarialValidator = MagicMock()
        dr.WikiWriter = MagicMock(return_value=mock_wiki_writer)
        dr.WebhookService = MagicMock(return_value=mock_webhook_service)
        dr.AuditService = MagicMock(return_value=mock_audit_service)

        try:
            run_daily_research()
            # Validator should never be called since no campaigns exist
            dr.AdversarialValidator.assert_not_called()
            mock_webhook_service.dispatch.assert_not_called()
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings

    def test_db_unreachable_returns_early_with_error_webhook(self):
        """When DB is unreachable at startup, cycle_error is dispatched and function returns."""
        from src.cron.daily_research import run_daily_research

        mock_webhook_service = MagicMock()

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

        def db_raises(*args, **kwargs):
            raise ConnectionError("could not connect to database")

        dr.PostgresAdapter = MagicMock(side_effect=db_raises)
        dr.WebhookService = MagicMock(return_value=mock_webhook_service)
        dr.GoogleAdsClient = MagicMock()
        dr.AdversarialValidator = MagicMock()
        dr.WikiWriter = MagicMock()
        dr.AuditService = MagicMock()

        try:
            run_daily_research()
            # Should have dispatched a cycle_error webhook
            dispatch_calls = mock_webhook_service.dispatch.call_args_list
            event_names = [call[0][0] for call in dispatch_calls]
            assert "cycle_error" in event_names
            # Error payload should mention campaign fetch failure
            error_payload = next(call[0][1] for call in dispatch_calls if call[0][0] == "cycle_error")
            assert "Failed to fetch campaigns" in error_payload.get("error", "")
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings

    def test_consensus_execution_updates_last_reviewed_at(self):
        """When consensus is reached, campaign last_reviewed_at is updated in DB."""
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
        async def mock_run_cycle_reviewed(*args, **kwargs):
            return final_state
        mock_validator.run_cycle = mock_run_cycle_reviewed

        mock_wiki_writer = MagicMock()
        mock_webhook_service = MagicMock()
        mock_audit_service = MagicMock()
        mock_gads_client = MagicMock()
        mock_gads_client.get_performance_report.return_value = MagicMock(
            impressions=0, clicks=0, ctr=0.0, spend_micros=0,
            conversions=0.0, avg_cpc_micros=0,
        )
        mock_gads_client.add_keywords = MagicMock()

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
            # Verify DB.execute was called to update last_reviewed_at
            db_calls = mock_db.execute.call_args_list
            update_calls = [c for c in db_calls if "UPDATE campaigns SET last_reviewed_at" in str(c)]
            assert len(update_calls) == 1
            # Verify audit was logged
            mock_audit_service.log_decision.assert_called_once()
            # Verify consensus webhook was dispatched
            dispatch_calls = mock_webhook_service.dispatch.call_args_list
            event_names = [call[0][0] for call in dispatch_calls]
            assert "consensus_reached" in event_names
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
            AsyncMock(side_effect=RuntimeError("Google Ads API error")),
            AsyncMock(return_value=good_state),
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

    def test_validator_returns_none_skips_campaign(self):
        """When validator.run_cycle returns None, campaign is skipped without error."""
        from src.cron.daily_research import run_daily_research

        cid = uuid4()
        campaigns = [
            {
                "id": str(cid),
                "campaign_id": "12345",
                "customer_id": "cust_001",
                "name": "Test Campaign",
                "api_key_token": "token",
                "status": "active",
            }
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = campaigns
        mock_db.search_wiki.return_value = []

        mock_validator = MagicMock()
        async def mock_run_cycle_none(*args, **kwargs):
            return None
        mock_validator.run_cycle = mock_run_cycle_none

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
            # No exception should be raised; no webhooks dispatched for this campaign
            dispatch_calls = mock_webhook_service.dispatch.call_args_list
            event_names = [call[0][0] for call in dispatch_calls]
            # Should not fire consensus_reached or manual_review_required or cycle_error
            assert "consensus_reached" not in event_names
            assert "manual_review_required" not in event_names
            assert "cycle_error" not in event_names
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings

    def test_no_consensus_non_pending_phase_skips(self):
        """When phase is not CONSENSUS_LOCKED and not PENDING_MANUAL_REVIEW, campaign is skipped."""
        from src.cron.daily_research import run_daily_research

        cid = uuid4()
        campaigns = [
            {
                "id": str(cid),
                "campaign_id": "12345",
                "customer_id": "cust_001",
                "name": "Test Campaign",
                "api_key_token": "token",
                "status": "active",
            }
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = campaigns
        mock_db.search_wiki.return_value = []

        # Return a state where phase is GREEN_PROPOSES (not consensus, not pending)
        ongoing_state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.GREEN_PROPOSES,
            consensus_reached=False,
            round_number=1,
            green_proposals=[],
            red_objections=[],
        )

        mock_validator = MagicMock()
        async def mock_run_cycle_green(*args, **kwargs):
            return ongoing_state
        mock_validator.run_cycle = mock_run_cycle_green

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
            # No consensus and not pending review → skip silently
            dispatch_calls = mock_webhook_service.dispatch.call_args_list
            event_names = [call[0][0] for call in dispatch_calls]
            assert "consensus_reached" not in event_names
            assert "manual_review_required" not in event_names
            assert "cycle_error" not in event_names
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings


class TestRunDailyResearchLocking:
    """Tests for run_daily_research lock acquisition."""

    def test_returns_early_when_lock_held(self):
        """When lock cannot be acquired, run_daily_research returns early without processing."""
        from src.cron.daily_research import run_daily_research

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

        dr.PostgresAdapter = MagicMock()
        dr.GoogleAdsClient = MagicMock()
        dr.AdversarialValidator = MagicMock()
        dr.WikiWriter = MagicMock()
        dr.WebhookService = MagicMock()
        dr.AuditService = MagicMock()

        try:
            with patch.object(dr, "_acquire_lock", return_value=False):
                run_daily_research()
            # No campaigns fetched because we exited early
            dr.PostgresAdapter.assert_not_called()
            dr.AdversarialValidator.assert_not_called()
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings


class TestSendHitlEmailsMissingOwner:
    """Tests for _send_hitl_emails when owner_email is missing."""

    def test_skips_without_error_when_no_owner_email(self):
        """When hitl_enabled=True but no owner_email, _send_hitl_emails returns early."""
        from src.cron.daily_research import _send_hitl_emails

        import src.cron.daily_research as dr

        mock_webhook = MagicMock()
        state = MagicMock()
        state.green_proposals = [{"type": "keyword_add"}]

        campaign_no_email = {
            "id": "uuid1",
            "campaign_id": "12345",
            "name": "Test",
            "hitl_enabled": True,
            # owner_email intentionally absent
        }

        with patch.object(dr, "send_proposal_email") as mock_email:
            _send_hitl_emails(state, campaign_no_email, mock_webhook)
            mock_email.assert_not_called()


class TestValidatorRunCycleCalledWithAwait:
    """
    RED: run_daily_research must await validator.run_cycle() — it is an async def.

    BUG: validator.run_cycle is async (in validator.py:24) but run_daily_research
    calls it as a sync call: state = validator.run_cycle(...). Without await, state
    is a coroutine object, not a DebateState. Accessing state.consensus_reached raises
    AttributeError: 'coroutine' object has no attribute 'consensus_reached'.

    The existing tests mock AdversarialValidator entirely, so they pass even with
    the missing await. This test uses the real AdversarialValidator with fully mocked
    agents to expose the sync/async mismatch.
    """

    def test_validator_run_cycle_is_called_and_awaited(self):
        """
        When validator.run_cycle() is properly awaited, the research cycle completes
        without AttributeError and fires consensus_reached (not cycle_error).

        This test asserts the CORRECT behavior. With the bug present, it fails:
          - cycle_error fires because coroutine.consensus_reached raises AttributeError
          - consensus_reached does NOT fire because the cycle crashed

        After fix (asyncio.run wrapper), this test passes.
        """
        import warnings
        import src.cron.daily_research as dr
        import src.config as config_module

        cid = uuid4()
        campaigns = [
            {
                "id": str(cid),
                "campaign_id": "12345",
                "customer_id": "cust_001",
                "name": "Test Campaign",
                "api_key_token": "token",
                "status": "active",
            }
        ]

        mock_db = MagicMock()
        mock_db.list_campaigns.return_value = campaigns
        mock_db.search_wiki.return_value = []
        mock_db.get_latest_debate_state.return_value = None

        from src.research.validator import AdversarialValidator

        class TrackerValidator(AdversarialValidator):
            async def run_cycle(self, *args, **kwargs):
                return await super().run_cycle(*args, **kwargs)

        tracker_validator = TrackerValidator(
            green=MagicMock(),
            red=MagicMock(),
            coordinator=MagicMock(),
            state_machine=MagicMock(),
        )

        mock_wiki_writer = MagicMock()
        mock_webhook_service = MagicMock()
        mock_audit_service = MagicMock()
        mock_gads_client = MagicMock()
        mock_gads_client.get_performance_report.return_value = MagicMock(
            impressions=0, clicks=0, ctr=0.0, spend_micros=0,
            conversions=0.0, avg_cpc_micros=0,
        )
        mock_gads_client.add_keywords = MagicMock()

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
        dr.AdversarialValidator = lambda *args, **kwargs: tracker_validator
        dr.WikiWriter = MagicMock(return_value=mock_wiki_writer)
        dr.WebhookService = MagicMock(return_value=mock_webhook_service)
        dr.AuditService = MagicMock(return_value=mock_audit_service)

        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                dr.run_daily_research()
                # With fix: no unawaited coroutine warning
                unawaited = [x for x in w if "was never awaited" in str(x.message)]
                assert len(unawaited) == 0, (
                    f"run_daily_research left a coroutine unawaited: "
                    f"{[str(x.message) for x in unawaited]}. "
                    f"Fix: wrap validator.run_cycle(...) in asyncio.run()"
                )
            # With fix: consensus_reached fires, NOT cycle_error
            dispatch_calls = mock_webhook_service.dispatch.call_args_list
            event_names = [call[0][0] for call in dispatch_calls]
            assert "cycle_error" not in event_names, (
                f"cycle_error fired — the validator coroutine was not awaited "
                f"and crashed with AttributeError. Events fired: {event_names}"
            )
            # consensus_reached should fire (validator completed with consensus)
            assert "consensus_reached" in event_names, (
                f"consensus_reached did not fire — validator may not have completed. "
                f"Events fired: {event_names}"
            )
        finally:
            for name, cls in original_modules.items():
                setattr(dr, name, cls)
            dr.get_settings = original_dr_get_settings
            config_module.get_settings = original_get_settings
