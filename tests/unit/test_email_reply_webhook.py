"""
RED: Write the failing test first.
Tests for POST /email-replies — Resend inbound email reply webhook handler.

BUG: send_proposal_email tells owners to reply with "approve"/"yes"/"sounds good"
or "reject"/"no"/"not this time", but there is no route to receive and process
those email replies. The inbound reply processing is entirely missing.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.email_replies import router


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.email_replies.PostgresAdapter", lambda: mock)
    return mock


@pytest.fixture
def mock_guard_and_client(monkeypatch):
    mock_guard = MagicMock()
    mock_guard.check.return_value = None

    mock_gads = MagicMock()
    mock_gads.add_keywords.return_value = ["kw1"]
    mock_gads.remove_keywords.return_value = []
    mock_gads.update_keyword_bids.return_value = []
    mock_gads.update_keyword_match_types.return_value = []

    def patched_guard():
        return mock_guard

    def patched_client(**_kwargs):
        return mock_gads

    monkeypatch.setattr("src.api.routes.email_replies.CapabilityGuard", patched_guard)
    monkeypatch.setattr("src.api.routes.email_replies.GoogleAdsClient", patched_client)
    return mock_guard, mock_gads


@pytest.fixture
def email_reply_app(mock_adapter, mock_guard_and_client):
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(email_reply_app):
    return TestClient(email_reply_app, raise_server_exceptions=False)


# ──────────────────────────────────────────────────────────────────────────────
# Sample data
# ──────────────────────────────────────────────────────────────────────────────

def make_campaign_row(
    owner_email: str = "owner@example.com",
    campaign_id: str = "12345",
    hitl_enabled: bool = True,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "campaign_id": campaign_id,
        "customer_id": "cust_001",
        "name": "Test Campaign",
        "status": "active",
        "campaign_type": "search",
        "owner_tag": "marketing",
        "owner_email": owner_email,
        "hitl_enabled": hitl_enabled,
        "created_at": datetime(2026, 4, 6, 10, 0, 0),
        "last_synced_at": datetime(2026, 4, 6, 8, 0, 0),
        "last_reviewed_at": datetime(2026, 4, 5, 8, 0, 0),
    }


# ──────────────────────────────────────────────────────────────────────────────
# RED: Failing tests for email reply webhook
# ──────────────────────────────────────────────────────────────────────────────

class TestEmailReplyWebhookApprove:
    """Owner replies "approve", "yes", or "sounds good" → debate state approved."""

    def test_approve_keyword_add_via_yes_reply(self, mock_adapter, client, mock_guard_and_client):
        """
        A reply body containing "yes" from the owner triggers approval
        of the pending keyword_add proposal.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row(owner_email="owner@example.com", campaign_id="cmp_001")
        campaign_row["id"] = campaign_uuid

        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [
                {"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["new shoes"]},
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required: keyword_add on campaign \"Test Campaign\"",
                "body": "yes",
                "in_reply_to": "<original-message-id@example.com>",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["campaign_id"] == str(campaign_uuid)
        mock_adapter.save_debate_state.assert_called_once()
        saved = mock_adapter.save_debate_state.call_args[0][0]
        assert saved["phase"] == "approved"

    def test_approve_via_sounds_good_reply(self, mock_adapter, client, mock_guard_and_client):
        """
        A reply body containing "sounds good" triggers approval.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 2,
            "green_proposals": [{"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]}],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "Sounds good, go ahead",
            },
        )

        assert response.status_code == 200
        mock_adapter.save_debate_state.assert_called_once()
        saved = mock_adapter.save_debate_state.call_args[0][0]
        assert saved["phase"] == "approved"


class TestEmailReplyWebhookReject:
    """Owner replies "reject", "no", or "not this time" → debate state rejected."""

    def test_reject_via_no_reply(self, mock_adapter, client, mock_guard_and_client):
        """
        A reply body containing "no" triggers rejection of the pending proposal.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [{"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]}],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "rejected"}

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "no, not right now",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        mock_adapter.save_debate_state.assert_called_once()
        saved = mock_adapter.save_debate_state.call_args[0][0]
        assert saved["phase"] == "rejected"

    def test_reject_via_not_this_time(self, mock_adapter, client, mock_guard_and_client):
        """
        A reply body containing "not this time" triggers rejection.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 1,
            "green_proposals": [{"type": "bid_update", "updates": []}],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "rejected"}

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "Not this time, thanks",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"


class TestEmailReplyWebhookNotFound:
    """No matching campaign or no pending proposal → 404."""

    def test_returns_404_when_no_campaign_for_email(self, mock_adapter, client):
        """Returns 404 when no campaign is registered for the replying email address."""
        mock_adapter.get_campaign_by_owner_email.return_value = None

        response = client.post(
            "/email-replies",
            json={
                "email_from": "unknown@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "yes",
            },
        )

        assert response.status_code == 404
        assert "no campaign" in response.json()["detail"].lower()

    def test_returns_404_when_no_pending_proposal(self, mock_adapter, client):
        """Returns 404 when campaign has no proposal awaiting approval."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = None  # no debate ever run

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "yes",
            },
        )

        assert response.status_code == 404
        assert "pending" in response.json()["detail"].lower() or "no proposal" in response.json()["detail"].lower()


class TestEmailReplyApproveExecutesAllProposalTypes:
    """
    When owner approves via email reply, ALL proposal types in green_proposals
    must be executed — not just keyword_add.

    BUG: handle_email_reply approve branch only handles keyword_add.
    keyword_remove, bid_update, and match_type_update are silently skipped.
    """

    def test_approve_keyword_remove_executes_gads_remove_keywords(
        self, mock_adapter, client, mock_guard_and_client
    ):
        """
        An approval reply must call gads_client.remove_keywords for
        keyword_remove proposals.
        """
        mock_guard, mock_gads = mock_guard_and_client
        mock_gads.remove_keywords.return_value = ["customers/cust/keywords/kw1"]

        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [
                {
                    "type": "keyword_remove",
                    "resource_names": ["customers/cust/keywords/kw1"],
                },
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "yes",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        mock_gads.remove_keywords.assert_called_once()
        call_kwargs = mock_gads.remove_keywords.call_args
        assert call_kwargs.kwargs.get("customer_id") == "cust_001"
        assert call_kwargs.kwargs.get("keyword_resource_names") == ["customers/cust/keywords/kw1"]

    def test_approve_bid_update_executes_gads_update_bids(
        self, mock_adapter, client, mock_guard_and_client
    ):
        """
        An approval reply must call gads_client.update_keyword_bids for
        bid_update proposals.
        """
        mock_guard, mock_gads = mock_guard_and_client
        mock_gads.update_keyword_bids.return_value = []

        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [
                {
                    "type": "bid_update",
                    "updates": [
                        {
                            "resource_name": "customers/cust/campaigns/cmp_001/adGroupAds/ag_001/criteria/kw1",
                            "cpc_bid_micros": 115000,
                        },
                    ],
                },
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "approve",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        mock_gads.update_keyword_bids.assert_called_once()
        call_kwargs = mock_gads.update_keyword_bids.call_args
        assert call_kwargs.kwargs.get("customer_id") == "cust_001"
        updates = call_kwargs.kwargs.get("updates", [])
        assert len(updates) == 1
        assert updates[0]["resource_name"] == "customers/cust/campaigns/cmp_001/adGroupAds/ag_001/criteria/kw1"
        assert updates[0]["cpc_bid_micros"] == 115000

    def test_approve_match_type_update_executes_gads_update_match_types(
        self, mock_adapter, client, mock_guard_and_client
    ):
        """
        An approval reply must call gads_client.update_keyword_match_types
        for match_type_update proposals.
        """
        mock_guard, mock_gads = mock_guard_and_client
        mock_gads.update_keyword_match_types.return_value = []

        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [
                {
                    "type": "match_type_update",
                    "updates": [
                        {
                            "resource_name": "customers/cust/campaigns/cmp_001/adGroupAds/ag_001/criteria/kw1",
                            "match_type": "PHRASE",
                        },
                    ],
                },
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "yes",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        mock_gads.update_keyword_match_types.assert_called_once()
        call_kwargs = mock_gads.update_keyword_match_types.call_args
        assert call_kwargs.kwargs.get("customer_id") == "cust_001"
        updates = call_kwargs.kwargs.get("updates", [])
        assert len(updates) == 1
        assert updates[0]["match_type"] == "PHRASE"

    def test_approve_mixed_proposals_executes_all_three_types(
        self, mock_adapter, client, mock_guard_and_client
    ):
        """
        A single approval must execute keyword_add, keyword_remove,
        bid_update, AND match_type_update when all are present.
        """
        mock_guard, mock_gads = mock_guard_and_client
        mock_gads.add_keywords.return_value = []
        mock_gads.remove_keywords.return_value = []
        mock_gads.update_keyword_bids.return_value = []
        mock_gads.update_keyword_match_types.return_value = []

        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [
                {"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]},
                {"type": "keyword_remove", "resource_names": ["customers/cust/keywords/kw_old"]},
                {
                    "type": "bid_update",
                    "updates": [{"resource_name": "kw1", "cpc_bid_micros": 150000}],
                },
                {
                    "type": "match_type_update",
                    "updates": [{"resource_name": "kw2", "match_type": "PHRASE"}],
                },
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "go ahead",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        mock_gads.add_keywords.assert_called_once()
        mock_gads.remove_keywords.assert_called_once()
        mock_gads.update_keyword_bids.assert_called_once()
        mock_gads.update_keyword_match_types.assert_called_once()


class TestEmailReplyWebhookHitlDisabled:
    """HITL must be enabled for email replies to modify debate state."""

    def test_approve_returns_404_when_hitl_disabled(self, mock_adapter, client):
        """
        When the campaign has hitl_enabled=False, approve replies must be rejected.
        This prevents bypassing HITL via the email-replies endpoint.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        campaign_row["hitl_enabled"] = False

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [
                {"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]},
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "yes",
            },
        )

        assert response.status_code == 404
        mock_adapter.save_debate_state.assert_not_called()

    def test_reject_returns_404_when_hitl_disabled(self, mock_adapter, client):
        """
        When the campaign has hitl_enabled=False, reject replies must also be rejected.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        campaign_row["hitl_enabled"] = False

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [],
            "red_objections": [],
            "consensus_reached": False,
        }

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "no",
            },
        )

        assert response.status_code == 404
        mock_adapter.save_debate_state.assert_not_called()


class TestEmailReplyInvalidPhase:
    """Invalid phase strings in DB must not cause 500 errors."""

    def test_invalid_phase_returns_404_not_500(self, mock_adapter, client):
        """
        If debate_row contains an invalid phase string (not a valid Phase enum),
        Phase(...) raises ValueError. The endpoint must return 404, not 500.
        Without the fix, ValueError propagates and FastAPI returns 500.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        campaign_row["hitl_enabled"] = True

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "not_a_valid_phase",  # invalid
            "round_number": 3,
            "green_proposals": [],
            "red_objections": [],
            "consensus_reached": False,
        }

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "yes",
            },
        )

        # Must return 404 (no pending proposal), not 500 (server error)
        assert response.status_code == 404

    def test_returns_404_when_phase_already_approved(self, mock_adapter, client):
        """
        When the debate is in APPROVED phase (not PENDING_MANUAL_REVIEW),
        a reply must return 404 — there is nothing pending to act on.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        campaign_row["hitl_enabled"] = True

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "approved",  # already approved
            "round_number": 1,
            "green_proposals": [],
            "red_objections": [],
            "consensus_reached": False,
        }

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "yes",
            },
        )

        assert response.status_code == 404


class TestEmailReplyWebhookQuestion:
    """Owner asks a question → webhook fires question_asked event, returns 200."""

    def test_question_fires_webhook_and_returns_200(self, mock_adapter, client, monkeypatch):
        """A reply that is neither approve nor reject fires a question_asked webhook."""
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row()
        campaign_row["id"] = campaign_uuid
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-07",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [{"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]}],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign_by_owner_email.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row

        dispatched_events = []
        async def fake_dispatch(event_type, payload):
            dispatched_events.append((event_type, payload))
        # Patch the module-level dispatch_event in the email_replies module
        import src.api.routes.email_replies as email_replies_module
        monkeypatch.setattr(email_replies_module, "dispatch_event", fake_dispatch)

        response = client.post(
            "/email-replies",
            json={
                "email_from": "owner@example.com",
                "subject": "Re: [AdsAgent] Action required",
                "body": "Can you explain why this is needed?",
            },
        )

        assert response.status_code == 200
        assert ("question_asked", {
            "campaign_id": str(campaign_uuid),
            "owner_email": "owner@example.com",
            "question": "Can you explain why this is needed?",
            "proposals": debate_row["green_proposals"],
        }) in dispatched_events
        # Phase must NOT change when owner asks a question
        mock_adapter.save_debate_state.assert_not_called()
