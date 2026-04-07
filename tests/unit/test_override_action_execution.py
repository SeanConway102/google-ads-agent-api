"""
RED: Write the failing test first.
Tests for override_campaign_action execution of non-keyword_add actions.

BUG: The override action's else-branch only calls guard.check() but never
calls the corresponding GoogleAdsClient method. keyword_remove, bid_update,
and match_type_update are checked against the guard but never executed.
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
    mock.get_campaign.return_value = {
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
    mock.write_audit_log.return_value = {"id": 999}
    monkeypatch.setattr("src.api.routes.campaigns.PostgresAdapter", lambda: mock)
    return mock


@pytest.fixture
def mock_gads_and_guard(monkeypatch, mock_adapter):
    """Mock GoogleAdsClient and CapabilityGuard."""
    mock_guard = MagicMock()
    mock_guard.check.return_value = None  # allowed

    mock_gads = MagicMock()
    mock_gads.add_keywords.return_value = None
    mock_gads.remove_keywords.return_value = None

    def patched_guard():
        return mock_guard

    def patched_client(**_kwargs):
        return mock_gads

    monkeypatch.setattr("src.api.routes.campaigns.CapabilityGuard", patched_guard)
    monkeypatch.setattr("src.api.routes.campaigns.GoogleAdsClient", patched_client)
    return mock_guard, mock_gads


@pytest.fixture
def campaign_app(mock_adapter, mock_gads_and_guard):
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(campaign_app):
    return TestClient(campaign_app, raise_server_exceptions=False)


class TestOverrideKeywordRemoveExecution:
    """override_campaign_action must call gads_client.remove_keywords for keyword_remove."""

    def test_override_keyword_remove_calls_gads_remove_keywords(
        self, mock_adapter, client, mock_gads_and_guard
    ):
        """
        For action_type=keyword_remove, the override action must call
        gads_client.remove_keywords(), not just check the guard.
        """
        mock_guard, mock_gads = mock_gads_and_guard
        campaign_uuid = mock_adapter.get_campaign.return_value["id"]

        response = client.post(
            f"/campaigns/{campaign_uuid}/override",
            json={
                "action_type": "keyword_remove",
                "keywords": ["customers/cust/keywords/kw1"],
            },
        )

        assert response.status_code == 200

        # Must call remove_keywords on the GoogleAdsClient
        mock_gads.remove_keywords.assert_called_once()
        call_kwargs = mock_gads.remove_keywords.call_args
        assert call_kwargs.kwargs.get("customer_id") == "cust_001"
        assert call_kwargs.kwargs.get("keyword_resource_names") == ["customers/cust/keywords/kw1"]


class TestOverrideBidUpdateExecution:
    """override_campaign_action must call gads_client.update_keyword_bids for bid_update."""

    def test_override_bid_update_calls_gads_update_bids(
        self, mock_adapter, client, mock_gads_and_guard
    ):
        """
        For action_type=bid_update, the override action must call
        gads_client.update_keyword_bids(), not just check the guard.
        """
        mock_guard, mock_gads = mock_gads_and_guard
        campaign_uuid = mock_adapter.get_campaign.return_value["id"]

        response = client.post(
            f"/campaigns/{campaign_uuid}/override",
            json={
                "action_type": "bid_update",
                "bid_adjustment": 0.15,
            },
        )

        assert response.status_code == 200

        # Must call update_keyword_bids on the GoogleAdsClient
        mock_gads.update_keyword_bids.assert_called_once()
        call_kwargs = mock_gads.update_keyword_bids.call_args
        assert call_kwargs.kwargs.get("customer_id") == "cust_001"

    def test_override_bid_update_with_updates_uses_explicit_values(
        self, mock_adapter, client, mock_gads_and_guard
    ):
        """
        bid_update override must use the explicit updates format (matching green
        team proposals) — updates field carries [{resource_name, cpc_bid_micros}].
        This is the same format the coordinator outputs and approve action uses.
        """
        mock_guard, mock_gads = mock_gads_and_guard
        campaign_uuid = mock_adapter.get_campaign.return_value["id"]

        response = client.post(
            f"/campaigns/{campaign_uuid}/override",
            json={
                "action_type": "bid_update",
                "updates": [
                    {"resource_name": "customers/cust/campaigns/cmp_001/adGroupAds/ag_001/criteria/kw1", "cpc_bid_micros": 115000},
                ],
            },
        )

        assert response.status_code == 200
        mock_gads.update_keyword_bids.assert_called_once()

        # Verify updates format: [{resource_name, cpc_bid_micros}]
        updates = mock_gads.update_keyword_bids.call_args.kwargs.get("updates", [])
        assert len(updates) == 1
        assert updates[0]["resource_name"] == "customers/cust/campaigns/cmp_001/adGroupAds/ag_001/criteria/kw1"
        assert updates[0]["cpc_bid_micros"] == 115000


class TestOverrideMatchTypeUpdateExecution:
    """override_campaign_action must call gads_client.update_keyword_match_types for match_type_update."""

    def test_override_match_type_update_calls_gads_update_match_types(
        self, mock_adapter, client, mock_gads_and_guard
    ):
        """
        For action_type=match_type_update, the override action must call
        gads_client.update_keyword_match_types() with explicit updates format.
        """
        mock_guard, mock_gads = mock_gads_and_guard
        campaign_uuid = mock_adapter.get_campaign.return_value["id"]

        response = client.post(
            f"/campaigns/{campaign_uuid}/override",
            json={
                "action_type": "match_type_update",
                "updates": [
                    {"resource_name": "customers/cust/campaigns/cmp_001/adGroupAds/ag_001/criteria/kw1", "match_type": "PHRASE"},
                ],
            },
        )

        assert response.status_code == 200

        # Must call update_keyword_match_types with correctly-formatted updates
        mock_gads.update_keyword_match_types.assert_called_once()
        updates = mock_gads.update_keyword_match_types.call_args.kwargs.get("updates", [])
        assert len(updates) == 1
        assert updates[0]["resource_name"] == "customers/cust/campaigns/cmp_001/adGroupAds/ag_001/criteria/kw1"
        assert updates[0]["match_type"] == "PHRASE"


class TestOverrideUnknownActionType:
    """override_campaign_action must reject unknown action_type with 422."""

    def test_unknown_action_type_returns_422(
        self, mock_adapter, client, mock_gads_and_guard
    ):
        """
        When action_type is not a recognised operation, the override endpoint
        must return 422 — not silently write an audit log and return 200.
        The else-branch calls guard.check() but executes nothing.
        """
        mock_guard, mock_gads = mock_gads_and_guard
        campaign_uuid = mock_adapter.get_campaign.return_value["id"]

        response = client.post(
            f"/campaigns/{campaign_uuid}/override",
            json={
                "action_type": "unknown_nonsense_action",
            },
        )

        # Must reject with 422, not 200
        assert response.status_code == 422
        # Audit log must NOT be written — no operation occurred
        mock_adapter.write_audit_log.assert_not_called()
        # No Google Ads client method should have been called
        mock_gads.add_keywords.assert_not_called()
        mock_gads.remove_keywords.assert_not_called()
