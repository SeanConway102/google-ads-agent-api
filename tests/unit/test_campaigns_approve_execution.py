"""
RED: Tests for campaigns.py approve endpoint — execution must happen BEFORE phase transition.

When CapabilityGuard denies ALL proposals, the campaigns.py approve endpoint:
1. First persists phase=APPROVED to DB
2. Then iterates proposals with `except CapabilityDenied: pass` — silently skips all
3. Returns 200 with status="approved" even though nothing executed in Google Ads

This is the reverse of the email_replies.py bug. The fix should:
- Execute proposals FIRST
- Only transition to APPROVED if execution succeeded
- Return 500 if all proposals were blocked/denied
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.campaigns import router
from src.mcp.capability_guard import CapabilityDenied


class TestCampaignsApproveExecution:
    """
    The approve endpoint should execute proposals BEFORE transitioning phase to APPROVED.
    If execution fails (CapabilityDenied or gads_client error), the phase must stay
    PENDING_MANUAL_REVIEW and return an error — not silently swallow the failure.
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
                {"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["boots"]},
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

    def test_all_proposals_blocked_returns_error_not_approved(self, mock_adapter):
        """
        When CapabilityGuard blocks ALL proposals, the endpoint must NOT return
        200 with status="approved". The phase should stay PENDING_MANUAL_REVIEW
        and the operator should be notified that execution was blocked.
        """
        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign.return_value = self._make_campaign_row()
        mock_adapter.get_latest_debate_state_any_cycle.return_value = self._make_debate_row(campaign_id)

        # All proposals are blocked by capability guard
        mock_guard = MagicMock()
        mock_guard.check.side_effect = CapabilityDenied("google_ads.add_keywords", "denied")

        mock_gads = MagicMock()

        with patch("src.api.routes.campaigns.CapabilityGuard", return_value=mock_guard), \
             patch("src.api.routes.campaigns.GoogleAdsClient", return_value=mock_gads):

            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                f"/campaigns/{campaign_id}/approve",
                headers={"X-API-Key": "test-key"},
            )

            # Must NOT return 200 "approved" when every proposal was blocked.
            # The correct behavior: return 403 (capability denied) or 500 (execution failed),
            # with phase staying PENDING_MANUAL_REVIEW so the operator can retry.
            assert not (response.status_code == 200 and response.json().get("status") == "approved"), (
                f"Got {response.status_code} with status={response.json().get('status')} — "
                "ALL proposals were blocked by CapabilityGuard but endpoint returned 'approved'. "
                "Blocked operations must not be reported as successful."
            )

    def test_gads_client_error_returns_error_not_approved(self, mock_adapter):
        """
        When gads_client.add_keywords() raises an error, the endpoint must NOT
        return 200 with status="approved". The phase should stay PENDING_MANUAL_REVIEW.
        """
        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign.return_value = self._make_campaign_row()
        mock_adapter.get_latest_debate_state_any_cycle.return_value = self._make_debate_row(campaign_id)

        mock_guard = MagicMock()
        mock_gads = MagicMock()
        mock_gads.add_keywords.side_effect = RuntimeError("Google Ads API connection refused")

        with patch("src.api.routes.campaigns.CapabilityGuard", return_value=mock_guard), \
             patch("src.api.routes.campaigns.GoogleAdsClient", return_value=mock_gads):

            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                f"/campaigns/{campaign_id}/approve",
                headers={"X-API-Key": "test-key"},
            )

            # Must NOT return 200 "approved" when Google Ads API failed
            assert not (response.status_code == 200 and response.json().get("status") == "approved"), (
                f"Got {response.status_code} with status={response.json().get('status')} — "
                "gads_client.add_keywords() raised RuntimeError but endpoint returned 'approved'. "
                "Execution errors must not be reported as successful."
            )

    def test_partial_block_means_no_approved_status(self, mock_adapter):
        """
        When some proposals execute and others are blocked by CapabilityGuard,
        the endpoint must NOT return 200 with status="approved".

        The partial execution gap: first proposal executes, second is blocked,
        operator gets "approved" with no indication half the work was skipped.

        The correct fix: return 403 (or 500) and stay PENDING when any proposal
        is blocked, so operator can retry with adjusted capabilities.

        This test will FAIL until the partial execution gap is fixed.
        """
        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign.return_value = self._make_campaign_row()

        # Two proposals: first executes, second is blocked
        debate_row = self._make_debate_row(campaign_id)
        debate_row["green_proposals"] = [
            {"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]},
            {"type": "keyword_add", "ad_group_id": "ag_002", "keywords": ["boots"]},
        ]
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row

        mock_guard = MagicMock()
        # First call succeeds, second call is denied
        mock_guard.check.side_effect = [
            None,  # first proposal passes
            CapabilityDenied("google_ads.add_keywords", "denied"),  # second blocked
        ]

        mock_gads = MagicMock()
        mock_gads.add_keywords.return_value = ["kw_001"]

        with patch("src.api.routes.campaigns.CapabilityGuard", return_value=mock_guard), \
             patch("src.api.routes.campaigns.GoogleAdsClient", return_value=mock_gads):

            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                f"/campaigns/{campaign_id}/approve",
                headers={"X-API-Key": "test-key"},
            )

            # Must NOT return 200 "approved" when only some proposals executed.
            # If ANY proposal is blocked, the operator must be notified — returning
            # "approved" after partial execution hides that some work was skipped.
            assert not (response.status_code == 200 and response.json().get("status") == "approved"), (
                f"Got {response.status_code} with status={response.json().get('status')} — "
                "proposal 1 executed but proposal 2 was blocked. "
                "Partial execution must not return 'approved' without clear reporting. "
                "This is the partial execution gap — fix by returning 403 (blocked) or 500 (error)."
            )

            # The real question: does this return "approved" when only 1 of 2 proposals executed?
            # This test documents the desired behavior — in practice the fix should either:
            # (a) return 207 Multi-Status with per-proposal results, or
            # (b) return 500 and roll back if ANY proposal fails, or
            # (c) return 200 with a detailed breakdown of what happened
            # For now, this test FAILS because the current implementation returns "approved"
            # after silently skipping the blocked proposal

    def test_unknown_proposal_type_does_not_return_approved(self, mock_adapter):
        """
        When a green_proposals item has an unrecognized ptype, the approve
        endpoint must NOT return 200 with status="approved".

        Same bug as email_replies.py: executed_proposals.append(ptype) is at the
        if/elif indentation level, so it runs for every ptype even if no branch
        matched. An unknown ptype silently passes through without guard.check()
        or any gads_client call, yet the phase transitions to APPROVED.
        """
        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign.return_value = self._make_campaign_row()
        mock_adapter.get_latest_debate_state_any_cycle.return_value = {
            "id": uuid.uuid4(),
            "campaign_id": campaign_id,
            "phase": "pending_manual_review",
            "round_number": 2,
            "cycle_date": "2026-04-06",
            "green_proposals": [
                {"type": "unknown_proposal_type"},
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_guard = MagicMock()
        mock_gads = MagicMock()

        with patch("src.api.routes.campaigns.CapabilityGuard", return_value=mock_guard), \
             patch("src.api.routes.campaigns.GoogleAdsClient", return_value=mock_gads):

            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                f"/campaigns/{campaign_id}/approve",
                headers={"X-API-Key": "test-key"},
            )

            assert not (response.status_code == 200 and response.json().get("status") == "approved"), (
                f"Got {response.status_code} with status={response.json().get('status')} — "
                "proposal type 'unknown_proposal_type' was marked as executed without "
                "any guard.check() or gads_client call. Unknown ptype must not result "
                "in status='approved'."
            )


@pytest.fixture
def mock_adapter(monkeypatch):
    """Patch PostgresAdapter so tests don't need a real database."""
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.campaigns.PostgresAdapter", lambda: mock)
    return mock