"""
RED: Failing test for silent failure when gads_client operations raise.
When gads_client.add_keywords() raises an exception (network error, API error),
except Exception: pass silently swallows it and returns status="approved"
even though the operation never succeeded.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.email_replies import router


class TestEmailReplyExecutionError:
    """
    When Google Ads operations fail during approval, the error must not be
    silently swallowed. The owner should get feedback on what went wrong.
    """

    def _make_app(self, mock_adapter):
        """Build a test app with mocked DB."""
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

    def test_gads_client_exception_not_silently_swallowed(self, mock_adapter):
        """
        When gads_client.add_keywords() raises an exception, the route must NOT
        return 200 with status="approved" — the error must be surfaced.
        Silently swallowing the exception means owners approve proposals that
        never actually get applied to Google Ads.
        """
        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign_by_owner_email.return_value = self._make_campaign_row()
        mock_adapter.get_latest_debate_state_any_cycle.return_value = self._make_debate_row(campaign_id)

        # gads_client raises an exception (e.g., network error, API error)
        mock_gads = MagicMock()
        mock_gads.add_keywords.side_effect = RuntimeError("Google Ads API connection refused")

        with patch("src.api.routes.email_replies.CapabilityGuard") as mock_guard_cls, \
             patch("src.api.routes.email_replies.GoogleAdsClient", return_value=mock_gads):

            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                "/email-replies",
                json={"email_from": "owner@example.com", "body": "yes"},
            )

            # Must NOT return 200 with status="approved" when the underlying
            # Google Ads operation failed. The error must propagate or be handled.
            assert response.status_code != 200 or response.json().get("status") != "approved", (
                f"Got {response.status_code} with status={response.json().get('status')} — "
                "gads_client.add_keywords() raised RuntimeError but the route returned "
                "status='approved'. Execution errors are silently swallowed."
            )

    def test_capability_denied_does_not_return_approved(self, mock_adapter):
        """
        When CapabilityGuard.check() raises CapabilityDenied, the route must
        NOT return 200 with status="approved" — the denial must be surfaced.
        """
        from src.mcp.capability_guard import CapabilityDenied

        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign_by_owner_email.return_value = self._make_campaign_row()
        mock_adapter.get_latest_debate_state_any_cycle.return_value = self._make_debate_row(campaign_id)

        mock_guard = MagicMock()
        mock_guard.check.side_effect = CapabilityDenied("google_ads.add_keywords", "denied")

        with patch("src.api.routes.email_replies.CapabilityGuard", return_value=mock_guard), \
             patch("src.api.routes.email_replies.GoogleAdsClient") as mock_client_cls:

            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                "/email-replies",
                json={"email_from": "owner@example.com", "body": "yes"},
            )

            # CapabilityDenied means the operation was blocked — must not return approved
            assert response.status_code != 200 or response.json().get("status") != "approved", (
                f"Got {response.status_code} with status={response.json().get('status')} — "
                "CapabilityDenied was raised but route returned status='approved'. "
                "Blocked operations must not be reported as successful."
            )

    def test_mixed_proposals_some_blocked_returns_403(self, mock_adapter):
        """
        When multiple proposals exist and some are blocked by CapabilityGuard
        while others succeed, the email reply must return 403 (not 200 or 500).
        This is the same pattern fixed in campaigns.py commit 1201e13.

        email_replies.py currently has NO try/except around the proposal loop,
        so the first CapabilityDenied propagates as an unhandled exception → 500.
        The correct behavior is to collect all blocked proposals and return 403
        with a message listing which proposals were blocked.
        """
        from src.mcp.capability_guard import CapabilityDenied

        campaign_id = uuid.uuid4()
        campaign_row = self._make_campaign_row()
        # Two proposals: keyword_add (blocked) and keyword_remove (would succeed)
        debate_row = {
            "id": uuid.uuid4(),
            "campaign_id": campaign_id,
            "phase": "pending_manual_review",
            "round_number": 2,
            "cycle_date": "2026-04-06",
            "green_proposals": [
                {"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]},
                {"type": "keyword_remove", "resource_names": ["customers/cust_001/adGroupCriteria/ag_001~123"]},
            ],
            "red_objections": [],
            "consensus_reached": False,
        }
        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row

        # keyword_add is blocked; keyword_remove would succeed
        mock_guard = MagicMock()
        # First call (keyword_add): blocked. Second call (keyword_remove): allowed.
        mock_guard.check.side_effect = [
            CapabilityDenied("google_ads.add_keywords", "add_keywords not allowed"),
            None,  # keyword_remove passes
        ]

        mock_gads = MagicMock()
        # keyword_remove succeeds
        mock_gads.remove_keywords.return_value = None

        with patch("src.api.routes.email_replies.CapabilityGuard", return_value=mock_guard), \
             patch("src.api.routes.email_replies.GoogleAdsClient", return_value=mock_gads):

            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                "/email-replies",
                json={"email_from": "owner@example.com", "body": "yes"},
            )

            # Must return 403 (Forbidden) when any proposal is blocked — not 200, not 500
            assert response.status_code == 403, (
                f"Got {response.status_code} — "
                "When some proposals are blocked, email_replies must return 403, "
                "not silently proceed or return a different error."
            )
            # Must not transition to approved phase
            if response.status_code == 403:
                body = response.json()
                assert body.get("detail") is not None, (
                    "403 response must include a detail message about blocked proposals"
                )

    def test_proposal_execution_error_returns_500(self, mock_adapter):
        """
        When a proposal's GoogleAdsClient call raises a non-CapabilityDenied
        exception (e.g., network error), the route must return 500, not 200.
        The debate phase must NOT transition to APPROVED.
        """
        campaign_id = uuid.uuid4()
        mock_adapter.get_campaign_by_owner_email.return_value = self._make_campaign_row()
        mock_adapter.get_latest_debate_state_any_cycle.return_value = self._make_debate_row(campaign_id)

        mock_guard = MagicMock()
        mock_guard.check.return_value = None  # guard passes

        mock_gads = MagicMock()
        mock_gads.add_keywords.side_effect = RuntimeError("Google Ads API timeout")

        with patch("src.api.routes.email_replies.CapabilityGuard", return_value=mock_guard), \
             patch("src.api.routes.email_replies.GoogleAdsClient", return_value=mock_gads):

            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                "/email-replies",
                json={"email_from": "owner@example.com", "body": "yes"},
            )

            # Must return 500 when gads_client itself raises
            assert response.status_code == 500, (
                f"Got {response.status_code} — gads_client raised RuntimeError, "
                "expected 500 Internal Server Error"
            )
            # Must not save APPROVED phase
            mock_adapter.save_debate_state.assert_not_called()

    def test_unknown_proposal_type_does_not_return_approved(self, mock_adapter):
        """
        When a proposal has an unrecognized ptype (not keyword_add, keyword_remove,
        bid_update, or match_type_update), the route must NOT return 200 with
        status="approved". The proposal was never executed, yet the current code
        falls through the if/elif chain and marks it as executed anyway.

        This is the same bug as campaigns.py: executed_proposals.append(ptype) is
        at the if/elif indentation level, so it runs for every ptype regardless of
        whether a branch matched. An unknown ptype silently passes through without
        guard.check() being called, without any Google Ads operation, yet the
        phase transitions to APPROVED.
        """
        campaign_id = uuid.uuid4()
        campaign_row = self._make_campaign_row()
        debate_row = {
            "id": uuid.uuid4(),
            "campaign_id": campaign_id,
            "phase": "pending_manual_review",
            "round_number": 2,
            "cycle_date": "2026-04-06",
            "green_proposals": [
                {"type": "unknown_proposal_type", "some_field": "value"},
            ],
            "red_objections": [],
            "consensus_reached": False,
        }
        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row

        mock_guard = MagicMock()
        mock_gads = MagicMock()

        with patch("src.api.routes.email_replies.CapabilityGuard", return_value=mock_guard), \
             patch("src.api.routes.email_replies.GoogleAdsClient", return_value=mock_gads):

            app = self._make_app(mock_adapter)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.post(
                "/email-replies",
                json={"email_from": "owner@example.com", "body": "yes"},
            )

            # Must NOT return 200 with status="approved" for an unknown proposal type.
            # Either: (a) return 400 for unrecognized ptype, or (b) treat it as blocked.
            assert not (response.status_code == 200 and response.json().get("status") == "approved"), (
                f"Got {response.status_code} with status={response.json().get('status')} — "
                "proposal type 'unknown_proposal_type' was marked as executed without "
                "any guard.check() or gads_client call. An unrecognized ptype must not "
                "result in status='approved'."
            )


@pytest.fixture
def mock_adapter(monkeypatch):
    """Patch PostgresAdapter so tests don't need a real database."""
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.email_replies.PostgresAdapter", lambda: mock)
    return mock
