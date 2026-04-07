"""
RED: Failing tests for daily_research cron script.
Tests the full daily research cycle orchestration.
"""
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.agents.debate_state import DebateState, Phase


def _mock_get_settings():
    """Return a mock Settings object with required fields."""
    mock_settings = MagicMock()
    mock_settings.MAX_DEBATE_ROUNDS = 5
    return mock_settings


class TestRunDailyResearch:
    """Test run_daily_research() orchestration."""

    def test_concurrent_run_aborts_when_lock_held(self, monkeypatch):
        """When another cycle is already running, run_daily_research returns early without processing."""
        from src.cron import daily_research as dr_module
        from src.cron.daily_research import run_daily_research

        # Prevent the real lock from being acquired — the function should abort early
        # without touching the database. Using monkeypatch.setitem on sys.modules
        # is NOT needed; we just need to shadow the function at the call site.
        # The simplest reliable way: patch the module's _acquire_lock via setattr.
        # We store the original and restore it using monkeypatch's undo mechanism.
        original = dr_module._acquire_lock
        monkeypatch.setattr(dr_module, "_acquire_lock", lambda lock_path: False)

        # Track whether PostgresAdapter was called (only if lock is acquired)
        adapter_called = False
        original_adapter = dr_module.PostgresAdapter

        def tracking_adapter(*args, **kwargs):
            nonlocal adapter_called
            adapter_called = True
            return original_adapter(*args, **kwargs)

        monkeypatch.setattr(dr_module, "PostgresAdapter", tracking_adapter)
        run_daily_research()

        # Lock was not acquired → PostgresAdapter should not have been called
        assert adapter_called is False, "PostgresAdapter was called despite lock not acquired"

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
        mock_validator.run_cycle.return_value = final_state

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
        mock_validator.run_cycle.return_value = None  # validator returned no state

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
        mock_validator.run_cycle.return_value = ongoing_state

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
