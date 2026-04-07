"""
RED: Tests for HITL proposal routes.
GET /campaigns/{uuid}/hitl/proposals
GET /campaigns/{uuid}/hitl/proposals/{proposal_id}
POST /campaigns/{uuid}/hitl/proposals/{proposal_id}/decide
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.hitl import router


# ──────────────────────────────────────────────────────────────────────────────
# Sample data
# ──────────────────────────────────────────────────────────────────────────────

def make_proposal_row(
    proposal_id: str | None = None,
    campaign_id: str | None = None,
    status: str = "pending",
    proposal_type: str = "keyword_add",
) -> dict:
    pid = proposal_id or str(uuid.uuid4())
    cid = campaign_id or str(uuid.uuid4())
    now = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    return {
        "id": pid,
        "campaign_id": cid,
        "proposal_type": proposal_type,
        "impact_summary": "Add 10 keywords to improve CTR",
        "reasoning": "Green team analysis shows CTR opportunity",
        "status": status,
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
        "replier_response": None,
    }


def make_campaign_row(campaign_id: str | None = None) -> dict:
    cid = campaign_id or str(uuid.uuid4())
    return {
        "id": cid,
        "campaign_id": "123",
        "customer_id": "cust",
        "name": "Test Campaign",
        "status": "active",
        "campaign_type": "search",
        "owner_tag": None,
        "api_key_token": "token",
        "created_at": "2026-01-01",
        "last_synced_at": None,
        "last_reviewed_at": None,
        "hitl_enabled": True,
        "owner_email": "a@b.com",
        "hitl_threshold": "budget>20pct",
    }


# ──────────────────────────────────────────────────────────────────────────────
# App fixture
# ──────────────────────────────────────────────────────────────────────────────

def _make_app(mock_adapter):
    """Build a test app with mocked DB."""
    app = FastAPI()
    app.include_router(router)
    # Monkeypatch so _adapter() returns our mock
    import src.api.routes.hitl as hitl_module
    hitl_module._adapter = lambda: mock_adapter
    return app


class TestListHitlProposals:
    """GET /campaigns/{uuid}/hitl/proposals"""

    def test_list_returns_proposals(self):
        """Returns all proposals for a campaign."""
        campaign_id = uuid.uuid4()
        proposal = make_proposal_row(campaign_id=str(campaign_id))

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.list_hitl_proposals.return_value = [proposal]

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.get(f"/campaigns/{campaign_id}/hitl/proposals")

        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["id"] == str(proposal["id"])
        assert payload[0]["status"] == "pending"

    def test_list_filters_by_status(self):
        """Passing ?status=pending returns only pending proposals."""
        campaign_id = uuid.uuid4()

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.list_hitl_proposals.return_value = []

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.get(f"/campaigns/{campaign_id}/hitl/proposals?status=pending")

        assert response.status_code == 200
        mock_adapter.list_hitl_proposals.assert_called_once()
        # Called with campaign_id and status="pending" keyword arg
        call_args = mock_adapter.list_hitl_proposals.call_args
        assert call_args[1]["status"] == "pending"

    def test_list_returns_404_when_campaign_not_found(self):
        """Returns 404 if the campaign does not exist."""
        from src.main import create_app

        campaign_id = uuid.uuid4()
        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = None

        with patch("src.api.routes.hitl._adapter", return_value=mock_adapter), \
             patch("src.api.middleware.get_admin_api_key", return_value="test-key"):
            app = create_app()
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                f"/campaigns/{campaign_id}/hitl/proposals",
                headers={"X-API-Key": "test-key"},
            )

        assert response.status_code == 404


class TestGetHitlProposal:
    """GET /campaigns/{uuid}/hitl/proposals/{proposal_id}"""

    def test_get_returns_proposal(self):
        """Returns a single proposal by ID."""
        campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()
        proposal = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(campaign_id),
        )

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.get_hitl_proposal.return_value = proposal

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.get(f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(proposal_id)
        assert payload["campaign_id"] == str(campaign_id)

    def test_get_returns_404_when_proposal_not_found(self):
        """Returns 404 if the proposal does not exist."""
        campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.get_hitl_proposal.return_value = None

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.get(f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}")

        assert response.status_code == 404

    def test_get_returns_404_when_proposal_belongs_to_different_campaign(self):
        """Returns 404 if the proposal belongs to a different campaign."""
        campaign_id = uuid.uuid4()
        other_campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()
        proposal = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(other_campaign_id),  # belongs to different campaign
        )

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.get_hitl_proposal.return_value = proposal

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.get(f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}")

        assert response.status_code == 404


class TestDecideHitlProposal:
    """POST /campaigns/{uuid}/hitl/proposals/{proposal_id}/decide"""

    def test_decide_approves_pending_proposal(self):
        """Approving a pending proposal updates its status to approved."""
        campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()
        now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        updated_proposal = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(campaign_id),
            status="approved",
        )
        updated_proposal["decided_at"] = now
        updated_proposal["replier_response"] = "LGTM"

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.get_hitl_proposal.return_value = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(campaign_id),
            status="pending",
        )
        mock_adapter.update_hitl_proposal_status.return_value = updated_proposal

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.post(
            f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide",
            json={"decision": "approved", "notes": "LGTM"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "approved"

    def test_decide_rejects_pending_proposal(self):
        """Rejecting a pending proposal updates its status to rejected."""
        campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()
        now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        updated_proposal = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(campaign_id),
            status="rejected",
        )
        updated_proposal["decided_at"] = now
        updated_proposal["replier_response"] = "Too risky"

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.get_hitl_proposal.return_value = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(campaign_id),
            status="pending",
        )
        mock_adapter.update_hitl_proposal_status.return_value = updated_proposal

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.post(
            f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide",
            json={"decision": "rejected", "notes": "Too risky"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "rejected"

    def test_decide_returns_404_when_proposal_not_found(self):
        """Returns 404 if the proposal does not exist."""
        campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.get_hitl_proposal.return_value = None

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.post(
            f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide",
            json={"decision": "approved"},
        )

        assert response.status_code == 404

    def test_decide_returns_409_when_proposal_not_pending(self):
        """Returns 409 if the proposal is not in pending status."""
        campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.get_hitl_proposal.return_value = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(campaign_id),
            status="approved",  # already approved
        )

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.post(
            f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide",
            json={"decision": "rejected"},
        )

        assert response.status_code == 409
        assert "already approved" in response.json()["detail"]

    def test_decide_returns_422_for_invalid_decision(self):
        """Returns 422 if decision is not 'approved' or 'rejected'."""
        campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()

        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.get_hitl_proposal.return_value = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(campaign_id),
            status="pending",
        )

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.post(
            f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide",
            json={"decision": "maybe"},  # invalid
        )

        assert response.status_code == 422

    def test_decide_requires_auth(self):
        """Without X-API-Key, returns 401."""
        from src.main import create_app

        campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()
        mock_adapter = MagicMock()
        mock_adapter.get_campaign.return_value = make_campaign_row(str(campaign_id))
        mock_adapter.get_hitl_proposal.return_value = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(campaign_id),
            status="pending",
        )

        with patch("src.api.routes.hitl._adapter", return_value=mock_adapter), \
             patch("src.api.middleware.get_admin_api_key", return_value="test-key"):
            app = create_app()
            client = TestClient(app, raise_server_exceptions=False)
            # No X-API-Key header
            response = client.post(
                f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide",
                json={"decision": "approved"},
            )
            assert response.status_code == 401

    def test_decide_returns_404_when_hitl_disabled(self):
        """
        When hitl_enabled=False on the campaign, decide must return 404.
        No HITL proposals should be decided for non-HITL campaigns — the same
        check that was added to email_replies.py in commit b659a8d must also
        apply to the REST decide endpoint.
        """
        campaign_id = uuid.uuid4()
        proposal_id = uuid.uuid4()

        mock_adapter = MagicMock()
        campaign_row = make_campaign_row(str(campaign_id))
        campaign_row["hitl_enabled"] = False
        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.get_hitl_proposal.return_value = make_proposal_row(
            proposal_id=str(proposal_id),
            campaign_id=str(campaign_id),
            status="pending",
        )
        mock_adapter.update_hitl_proposal_status.return_value = {
            "id": str(proposal_id),
            "status": "approved",
            "decided_at": datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
        }

        client = TestClient(_make_app(mock_adapter), raise_server_exceptions=False)
        response = client.post(
            f"/campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide",
            json={"decision": "approved"},
        )

        assert response.status_code == 404, (
            f"Expected 404 when hitl_enabled=False, got {response.status_code}. "
            "HITL decisions must be rejected for non-HITL campaigns."
        )
