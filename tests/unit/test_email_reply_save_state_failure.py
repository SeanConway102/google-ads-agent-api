"""
RED: Test for save_debate_state failure after Google Ads execution succeeds.

When save_debate_state raises an exception AFTER proposals have already been
executed in Google Ads, the API returns 500 but the proposals are live —
a partial failure with no compensation.

This gap was identified during adversarial review of email_replies.py.
The correct behavior is to wrap the save in a try/except and return a
structured error that distinguishes "execution succeeded, save failed" from
other 500 errors, so operators know to check Google Ads directly.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.email_replies import router


class TestEmailReplySaveDebateStateFailure:
    """
    When proposals are executed in Google Ads but save_debate_state fails,
    the owner gets a 500 error with no indication that their proposals may
    already be live in Google Ads. This is a partial failure — the operator
    cannot tell from the API response whether Google Ads was affected.
    """

    def _make_app(self, mock_adapter):
        app = FastAPI()
        app.include_router(router)
        return app

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

    def test_save_debate_state_fails_after_execution_returns_structured_error(
        self, mock_adapter
    ):
        """
        When proposals execute successfully in Google Ads but save_debate_state
        raises an exception, the current code returns an unhandled 500.

        The correct behavior is to catch the save failure and return a
        structured error (e.g., 500 with detail that indicates execution
        succeeded but persistence failed) so operators know to check
        Google Ads manually.

        Currently this test FAILS because save_debate_state exception
        propagates as a bare 500 with no distinguishing message.
        After the fix, it should return 500 with a message indicating
        the execution succeeded but save failed.
        """
        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign_by_owner_email.return_value = (
            self._make_campaign_row()
        )
        mock_adapter.get_latest_debate_state_any_cycle.return_value = (
            self._make_debate_row(campaign_id)
        )

        # Proposals execute successfully
        mock_guard = MagicMock()
        mock_guard.check.return_value = None

        mock_gads = MagicMock()
        mock_gads.add_keywords.return_value = None

        # save_debate_state fails — DB connection lost, constraint violation, etc.
        mock_adapter.save_debate_state.side_effect = RuntimeError(
            "connection to database lost"
        )

        with patch(
            "src.api.routes.email_replies.CapabilityGuard", return_value=mock_guard
        ), patch(
            "src.api.routes.email_replies.GoogleAdsClient", return_value=mock_gads
        ):
            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                "/email-replies",
                json={"email_from": "owner@example.com", "body": "yes"},
            )

        # save_debate_state was called (execution happened first)
        assert mock_adapter.save_debate_state.called, (
            "save_debate_state should have been called after proposal execution"
        )

        # The response must be a 500 (save failed after execution)
        assert response.status_code == 500, (
            f"Expected 500 when save_debate_state fails after execution, "
            f"got {response.status_code}"
        )

        # The error message must distinguish this from a generic execution error.
        # It should indicate that execution succeeded but save failed, so the
        # operator knows to check Google Ads. The error message should NOT include
        # the raw exception (potential credential/connection string leak).
        detail = response.json().get("detail", "").lower()
        assert "executed" in detail or "save" in detail or "persisted" in detail, (
            f"Error detail must indicate execution succeeded but save failed, "
            f"got: {detail!r}"
        )
        # Verify no raw exception text leaked into the response
        assert "connection to database" not in detail, (
            "Raw exception text leaked into client-facing error detail"
        )

    def test_save_debate_state_failure_does_not_return_approved(
        self, mock_adapter
    ):
        """
        Under no circumstances should save_debate_state failure return
        status='approved'. The phase must stay PENDING_MANUAL_REVIEW
        so a retry can recover.
        """
        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign_by_owner_email.return_value = (
            self._make_campaign_row()
        )
        mock_adapter.get_latest_debate_state_any_cycle.return_value = (
            self._make_debate_row(campaign_id)
        )

        mock_guard = MagicMock()
        mock_guard.check.return_value = None
        mock_gads = MagicMock()
        mock_adapter.save_debate_state.side_effect = RuntimeError(
            "DB write failed"
        )

        with patch(
            "src.api.routes.email_replies.CapabilityGuard", return_value=mock_guard
        ), patch(
            "src.api.routes.email_replies.GoogleAdsClient", return_value=mock_gads
        ):
            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                "/email-replies",
                json={"email_from": "owner@example.com", "body": "yes"},
            )

        # Must not return 200 with status="approved"
        assert not (
            response.status_code == 200
            and response.json().get("status") == "approved"
        ), (
            "save_debate_state failure must not return status='approved'. "
            "Phase stays PENDING so operator can retry."
        )


@pytest.fixture
def mock_adapter(monkeypatch):
    """Patch PostgresAdapter so tests don't need a real database."""
    mock = MagicMock()
    monkeypatch.setattr(
        "src.api.routes.email_replies.PostgresAdapter", lambda: mock
    )
    return mock
