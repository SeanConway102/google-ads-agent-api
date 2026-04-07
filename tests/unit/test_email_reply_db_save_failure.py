"""
Tests for save_debate_state failure after successful gads_client execution.
This is a KNOWN GAP — not currently handled, documented for operator awareness.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.email_replies import router


@pytest.fixture
def mock_adapter(monkeypatch):
    """Patch PostgresAdapter so tests don't need a real database."""
    mock = MagicMock()
    mock.save_debate_state.return_value = {"id": uuid.uuid4()}
    monkeypatch.setattr("src.api.routes.email_replies.PostgresAdapter", lambda: mock)
    return mock


class TestEmailReplyDbSaveFailure:
    """
    When gads_client execution succeeds but save_debate_state fails,
    the API returns 500 after the work is done. Operators receive no
    confirmation that their approval was applied to Google Ads.

    This is a known gap: the fix for silent execution failures moved
    save_debate_state to AFTER execution, which means a DB failure
    after successful execution returns 500 even though proposals ran.

    A proper fix would require a compensation mechanism or two-phase
    approach where the DB state is only updated after all external
    operations confirm success.
    """

    def _make_campaign_row(self) -> dict:
        return {
            "id": uuid.uuid4(),
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

    def _make_debate_row(self, campaign_id: uuid.UUID) -> dict:
        return {
            "id": uuid.uuid4(),
            "campaign_id": campaign_id,
            "phase": "pending_manual_review",
            "round_number": 2,
            "cycle_date": "2026-04-06",
            "green_proposals": [
                {"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]},
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

    def test_db_save_failure_after_successful_execution_returns_500(self, mock_adapter):
        """
        When gads_client succeeds but save_debate_state raises,
        the API returns 500. The operator sees a failure even though
        the proposals were applied to Google Ads.
        """
        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign_by_owner_email.return_value = self._make_campaign_row()
        mock_adapter.get_latest_debate_state_any_cycle.return_value = self._make_debate_row(campaign_id)

        # gads_client succeeds, but save_debate_state fails
        mock_gads = MagicMock()
        mock_gads.add_keywords.return_value = ["kw1"]

        def db_save_that_fails(_data: dict):
            raise RuntimeError("Database connection lost")

        mock_adapter.save_debate_state.side_effect = db_save_that_fails

        with patch("src.api.routes.email_replies.CapabilityGuard"), \
             patch("src.api.routes.email_replies.GoogleAdsClient", return_value=mock_gads):

            app = FastAPI()
            app.include_router(router)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                "/email-replies",
                json={"email_from": "owner@example.com", "body": "yes"},
            )

            # Returns 500 because save_debate_state failed after gads succeeded
            # This is the known gap — the work was done but the state wasn't saved
            assert response.status_code == 500, (
                f"Expected 500 when save_debate_state fails after successful execution, "
                f"got {response.status_code}. Proposals were applied to Google Ads "
                f"but operator receives no confirmation."
            )
