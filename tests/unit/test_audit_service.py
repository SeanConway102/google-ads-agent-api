"""
Tests for src/services/audit_service.py — centralized audit log writes.
"""
import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.api.schemas import AuditAction


@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.services.audit_service.PostgresAdapter", lambda: mock)
    return mock


class TestLogDecision:
    """Test AuditService.log_decision method (called from daily research cycle)."""

    def test_log_decision_calls_write_audit_log_with_consensus_reached(self, mock_adapter):
        from src.services.audit_service import AuditService
        from src.agents.debate_state import DebateState, Phase

        cid = uuid.uuid4()
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.CONSENSUS_LOCKED,
            consensus_reached=True,
            round_number=2,
            green_proposals=[{"type": "keyword_add", "target": "shoes"}],
            red_objections=[],
        )
        campaign = {
            "id": str(cid),
            "campaign_id": "12345",
            "name": "Test Campaign",
        }
        mock_adapter.write_audit_log.return_value = {"id": 1}

        service = AuditService(mock_adapter)
        result = service.log_decision(state, campaign)

        mock_adapter.write_audit_log.assert_called_once()
        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["action_type"] == AuditAction.CONSENSUS_REACHED.value
        assert call_args["cycle_date"] == "2026-04-06"
        assert call_args["campaign_id"] == cid
        assert call_args["green_proposal"] == [{"type": "keyword_add", "target": "shoes"}]
        assert call_args["debate_rounds"] == 2
        assert call_args["target"]["campaign_name"] == "Test Campaign"

    def test_log_decision_uses_getattr_defaults_for_missing_state_fields(self, mock_adapter):
        from src.services.audit_service import AuditService
        from src.agents.debate_state import DebateState

        cid = uuid.uuid4()
        # Use a plain MagicMock — getattr with default works on any object
        state = MagicMock()
        state.cycle_date = ""
        state.campaign_id = ""
        state.green_proposals = []
        state.red_objections = []
        state.round_number = 0
        state.phase = None
        campaign = {"name": "", "campaign_id": ""}
        mock_adapter.write_audit_log.return_value = {"id": 1}

        service = AuditService(mock_adapter)
        service.log_decision(state, campaign)

        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["green_proposal"] == []
        assert call_args["debate_rounds"] == 0


class TestLogCampaignDeleted:
    """Test log_campaign_deleted standalone function."""

    def test_log_campaign_deleted_calls_write_audit_log(self, mock_adapter):
        from src.services.audit_service import log_campaign_deleted

        campaign_id = uuid.uuid4()
        target = {"campaign_id": "cmp_001", "name": "Deleted Campaign"}
        mock_adapter.write_audit_log.return_value = {"id": 1}

        result = log_campaign_deleted(campaign_id, target)

        mock_adapter.write_audit_log.assert_called_once()
        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["action_type"] == AuditAction.CAMPAIGN_DELETED.value
        assert call_args["campaign_id"] == campaign_id
        assert call_args["cycle_date"] == date.today().isoformat()


class TestLogWikiCreated:
    """Test log_wiki_created standalone function."""

    def test_log_wiki_created_calls_write_audit_log(self, mock_adapter):
        from src.services.audit_service import log_wiki_created

        wiki_id = uuid.uuid4()
        target = {"campaign_id": "cmp_001", "title": "Running Shoes Trends"}
        mock_adapter.write_audit_log.return_value = {"id": 1}

        result = log_wiki_created(wiki_id, target)

        mock_adapter.write_audit_log.assert_called_once()
        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["action_type"] == AuditAction.WIKI_CREATED.value
        assert call_args["target"] == target
        assert call_args["campaign_id"] == "cmp_001"
        assert call_args["cycle_date"] == date.today().isoformat()


class TestLogWikiInvalidated:
    """Test log_wiki_invalidated standalone function."""

    def test_log_wiki_invalidated_calls_write_audit_log(self, mock_adapter):
        from src.services.audit_service import log_wiki_invalidated

        wiki_id = uuid.uuid4()
        campaign_id = uuid.uuid4()
        mock_adapter.write_audit_log.return_value = {"id": 1}

        result = log_wiki_invalidated(wiki_id, campaign_id)

        mock_adapter.write_audit_log.assert_called_once()
        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["action_type"] == AuditAction.WIKI_INVALIDATED.value
        assert call_args["target"] == {"wiki_id": str(wiki_id)}
        assert call_args["campaign_id"] == campaign_id

    def test_log_wiki_invalidated_with_no_campaign_id(self, mock_adapter):
        from src.services.audit_service import log_wiki_invalidated

        wiki_id = uuid.uuid4()
        mock_adapter.write_audit_log.return_value = {"id": 1}

        result = log_wiki_invalidated(wiki_id, None)

        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["campaign_id"] is None


class TestLogDebateStateSaved:
    """Test log_debate_state_saved standalone function."""

    def test_log_debate_state_saved_with_all_fields(self, mock_adapter):
        from src.services.audit_service import log_debate_state_saved

        campaign_id = uuid.uuid4()
        green = {"type": "keyword_add"}
        red = [{"objection": "cost"}]
        mock_adapter.write_audit_log.return_value = {"id": 1}

        result = log_debate_state_saved(
            campaign_id=campaign_id,
            cycle_date="2026-04-06",
            green_proposal=green,
            red_objections=red,
            coordinator_note="All good",
            debate_rounds=3,
        )

        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["action_type"] == AuditAction.DEBATE_STATE_SAVED.value
        assert call_args["green_proposal"] == green
        assert call_args["red_objections"] == red
        assert call_args["coordinator_note"] == "All good"
        assert call_args["debate_rounds"] == 3

    def test_log_debate_state_saved_with_no_optional_fields(self, mock_adapter):
        from src.services.audit_service import log_debate_state_saved

        campaign_id = uuid.uuid4()
        mock_adapter.write_audit_log.return_value = {"id": 1}

        result = log_debate_state_saved(
            campaign_id=campaign_id,
            cycle_date="2026-04-06",
        )

        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["green_proposal"] is None
        assert call_args["red_objections"] == []
        assert call_args["coordinator_note"] is None
        assert call_args["debate_rounds"] is None


class TestLogCampaignCreated:

    def test_log_campaign_created_calls_write_audit_log(self, mock_adapter):
        from src.services.audit_service import log_campaign_created

        campaign_id = uuid.uuid4()
        target = {"campaign_id": "cmp_001", "name": "Test Campaign"}
        mock_adapter.write_audit_log.return_value = {"id": 1}

        result = log_campaign_created(campaign_id, target)

        mock_adapter.write_audit_log.assert_called_once()
        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["action_type"] == AuditAction.CAMPAIGN_CREATED.value
        assert call_args["campaign_id"] == campaign_id
        assert call_args["cycle_date"] == date.today().isoformat()


class TestLogConsensusReached:

    def test_log_consensus_reached_with_all_fields(self, mock_adapter):
        from src.services.audit_service import log_consensus_reached

        campaign_id = uuid.uuid4()
        green = {"type": "keyword_add", "value": ["keyword1"]}
        red = [{"objection": "cost", "resolution": "bid_limit"}]
        mock_adapter.write_audit_log.return_value = {"id": 1}

        result = log_consensus_reached(
            campaign_id=campaign_id,
            cycle_date="2026-04-06",
            green_proposal=green,
            red_objections=red,
            debate_rounds=3,
        )

        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["action_type"] == AuditAction.CONSENSUS_REACHED.value
        assert call_args["green_proposal"] == green
        assert call_args["red_objections"] == red
        assert call_args["debate_rounds"] == 3


class TestLogActionExecuted:

    def test_log_action_executed(self, mock_adapter):
        from src.services.audit_service import log_action_executed

        campaign_id = uuid.uuid4()
        action = {"type": "keyword_add", "value": ["keyword1"]}
        mock_adapter.write_audit_log.return_value = {"id": 1}

        result = log_action_executed(
            campaign_id=campaign_id,
            cycle_date="2026-04-06",
            action=action,
            debate_rounds=5,
        )

        call_args = mock_adapter.write_audit_log.call_args[0][0]
        assert call_args["action_type"] == AuditAction.ACTION_EXECUTED.value
        assert call_args["target"] == action
        assert call_args["debate_rounds"] == 5
