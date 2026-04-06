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
