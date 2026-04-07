"""
RED: Write the failing test first.
Tests for proposal format contract between green team output and add_keywords input.

GoogleAdsClient.add_keywords signature:
    keywords: list[str]   — list of keyword text strings
    match_type: hardcoded to "EXACT" inside the method

Green team outputs proposals as:
    {"type": "keyword_add", "keywords": ["running shoes"], "ad_group_id": "ag_001"}

The approve action passes keywords directly to add_keywords — no transformation needed
since add_keywords accepts list[str]. But it MUST pass the ad_group_id correctly,
and must handle the case where keywords is missing from the proposal.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.campaigns import router


@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.campaigns.PostgresAdapter", lambda: mock)
    return mock


@pytest.fixture
def mock_guard_and_client(monkeypatch):
    """Mock CapabilityGuard.check() and GoogleAdsClient."""
    mock_guard = MagicMock()
    mock_guard.check.return_value = None  # allowed

    mock_gads = MagicMock()
    mock_gads.add_keywords.return_value = None

    def patched_guard():
        return mock_guard

    def patched_client(**_kwargs):
        return mock_gads

    monkeypatch.setattr("src.api.routes.campaigns.CapabilityGuard", patched_guard)
    monkeypatch.setattr("src.api.routes.campaigns.GoogleAdsClient", patched_client)
    return mock_guard, mock_gads


@pytest.fixture
def campaign_app(mock_adapter, mock_guard_and_client):
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(campaign_app):
    return TestClient(campaign_app, raise_server_exceptions=False)


def make_campaign_row(campaign_id: uuid.UUID) -> dict:
    return {
        "id": campaign_id,
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


class TestApproveProposalKeywordFormat:
    """
    GoogleAdsClient.add_keywords(keywords: list[str]) takes string keywords.
    Match type is hardcoded to EXACT inside add_keywords.
    """

    def test_approve_action_passes_string_keywords_directly_to_add_keywords(
        self, mock_adapter, client, mock_guard_and_client
    ):
        """
        add_keywords accepts list[str], so string keywords from green team
        are passed through directly — no transformation needed.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row(campaign_uuid)
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-06",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [
                {
                    "type": "keyword_add",
                    "keywords": ["running shoes", "trail running"],
                    "ad_group_id": "ag_001",
                }
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        _, mock_gads = mock_guard_and_client

        response = client.post(f"/campaigns/{campaign_uuid}/approve")

        assert response.status_code == 200
        mock_gads.add_keywords.assert_called_once()
        call_kwargs = mock_gads.add_keywords.call_args

        # ad_group_id must be passed through from proposal
        assert call_kwargs.kwargs.get("ad_group_id") == "ag_001"

        # keywords must be passed as list of strings (not dicts)
        keywords_arg = call_kwargs.kwargs.get("keywords")
        assert keywords_arg == ["running shoes", "trail running"]

    def test_approve_action_handles_proposals_without_keywords_field(
        self, mock_adapter, client, mock_guard_and_client
    ):
        """
        Proposals missing the keywords field entirely should not crash.
        """
        campaign_uuid = uuid.uuid4()
        campaign_row = make_campaign_row(campaign_uuid)
        debate_row = {
            "id": 1,
            "cycle_date": "2026-04-06",
            "campaign_id": campaign_uuid,
            "phase": "pending_manual_review",
            "round_number": 3,
            "green_proposals": [
                {
                    "type": "keyword_add",
                    # keywords field is absent
                    "ad_group_id": "ag_001",
                }
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        mock_adapter.get_campaign.return_value = campaign_row
        mock_adapter.get_latest_debate_state_any_cycle.return_value = debate_row
        mock_adapter.save_debate_state.return_value = {**debate_row, "phase": "approved"}

        response = client.post(f"/campaigns/{campaign_uuid}/approve")

        # Must not raise 500
        assert response.status_code in (200, 422)
