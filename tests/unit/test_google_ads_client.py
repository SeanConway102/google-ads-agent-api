"""
Tests for GoogleAdsClient keyword write operations.
MCP-004: remove_keywords
MCP-005: update_keyword_bids
MCP-006: update_keyword_match_types
"""
from unittest.mock import MagicMock, patch
import pytest

from src.mcp.google_ads_client import GoogleAdsClient


def test_remove_keywords_method_exists():
    """GoogleAdsClient should have a remove_keywords method."""
    client = GoogleAdsClient()
    assert hasattr(client, "remove_keywords"), "remove_keywords method not found"


def test_remove_keywords_calls_ad_group_criterion_mutation():
    """remove_keywords should call ad_group_criterion_mutation with remove operations."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.results = [
        MagicMock(resource_name="customers/123/adGroups/456/criteria/789"),
        MagicMock(resource_name="customers/123/adGroups/456/criteria/790"),
    ]
    mock_service.mutate_ad_group_criteria.return_value = mock_result

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        resource_names = [
            "customers/123/adGroups/456/criteria/789",
            "customers/123/adGroups/456/criteria/790",
        ]
        result = client.remove_keywords(customer_id="123", keyword_resource_names=resource_names)

    mock_service.mutate_ad_group_criteria.assert_called_once()
    call_kwargs = mock_service.mutate_ad_group_criteria.call_args
    assert call_kwargs.kwargs["customer_id"] == "123"
    operations = call_kwargs.kwargs["operations"]
    assert len(operations) == 2


def test_remove_keywords_returns_resource_names():
    """remove_keywords should return resource names from the API response."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.results = [
        MagicMock(resource_name="customers/123/adGroups/456/criteria/789"),
    ]
    mock_service.mutate_ad_group_criteria.return_value = mock_result

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        resource_names = ["customers/123/adGroups/456/criteria/789"]
        result = client.remove_keywords(customer_id="123", keyword_resource_names=resource_names)

    assert len(result) == 1
    assert result[0] == "customers/123/adGroups/456/criteria/789"


def test_remove_keywords_empty_list_returns_empty():
    """remove_keywords with empty list should return empty list without calling API."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        result = client.remove_keywords(customer_id="123", keyword_resource_names=[])

    assert result == []
    mock_service.mutate_ad_group_criteria.assert_not_called()


def test_remove_keywords_requires_capability():
    """remove_keywords should call _guard.check before making API call."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        with patch.object(client, "_guard") as mock_guard:
            client.remove_keywords(customer_id="123", keyword_resource_names=["some/resource"])

    mock_guard.check.assert_called_once_with("google_ads.remove_keywords")


# ─── update_keyword_bids (MCP-005) ───────────────────────────────────────────────

def test_update_keyword_bids_method_exists():
    """GoogleAdsClient should have an update_keyword_bids method."""
    client = GoogleAdsClient()
    assert hasattr(client, "update_keyword_bids"), "update_keyword_bids method not found"


def test_update_keyword_bids_calls_mutation_api():
    """update_keyword_bids should call mutate_ad_group_criteria with update operations."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.results = [MagicMock(resource_name="customers/123/adGroups/456/criteria/789")]
    mock_service.mutate_ad_group_criteria.return_value = mock_result

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        updates = [{"resource_name": "customers/123/adGroups/456/criteria/789", "cpc_bid_micros": 150000}]
        result = client.update_keyword_bids(customer_id="123", updates=updates)

    mock_service.mutate_ad_group_criteria.assert_called_once()
    call_kwargs = mock_service.mutate_ad_group_criteria.call_args
    assert call_kwargs.kwargs["customer_id"] == "123"
    operations = call_kwargs.kwargs["operations"]
    assert len(operations) == 1


def test_update_keyword_bids_empty_list_returns_empty():
    """update_keyword_bids with empty list should return empty list without calling API."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        result = client.update_keyword_bids(customer_id="123", updates=[])

    assert result == []
    mock_service.mutate_ad_group_criteria.assert_not_called()


def test_update_keyword_bids_requires_capability():
    """update_keyword_bids should call _guard.check before making API call."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        with patch.object(client, "_guard") as mock_guard:
            client.update_keyword_bids(customer_id="123", updates=[{"resource_name": "r", "cpc_bid_micros": 100}])

    mock_guard.check.assert_called_once_with("google_ads.update_keyword_bids")


# ─── update_keyword_match_types (MCP-006) ─────────────────────────────────────────

def test_update_keyword_match_types_method_exists():
    """GoogleAdsClient should have an update_keyword_match_types method."""
    client = GoogleAdsClient()
    assert hasattr(client, "update_keyword_match_types"), "update_keyword_match_types method not found"


def test_update_keyword_match_types_calls_mutation_api():
    """update_keyword_match_types should call mutate_ad_group_criteria with update operations."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.results = [MagicMock(resource_name="customers/123/adGroups/456/criteria/789")]
    mock_service.mutate_ad_group_criteria.return_value = mock_result

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        updates = [{"resource_name": "customers/123/adGroups/456/criteria/789", "match_type": "PHRASE"}]
        result = client.update_keyword_match_types(customer_id="123", updates=updates)

    mock_service.mutate_ad_group_criteria.assert_called_once()
    call_kwargs = mock_service.mutate_ad_group_criteria.call_args
    assert call_kwargs.kwargs["customer_id"] == "123"
    operations = call_kwargs.kwargs["operations"]
    assert len(operations) == 1


def test_update_keyword_match_types_requires_capability():
    """update_keyword_match_types should call _guard.check before making API call."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        with patch.object(client, "_guard") as mock_guard:
            client.update_keyword_match_types(customer_id="123", updates=[{"resource_name": "r", "match_type": "EXACT"}])

    mock_guard.check.assert_called_once_with("google_ads.update_keyword_match_types")
