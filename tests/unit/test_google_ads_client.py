"""
Tests for GoogleAdsClient keyword write operations.
MCP-004: remove_keywords
MCP-005: update_keyword_bids
MCP-006: update_keyword_match_types
MCP-007: get_keyword_performance
MCP-008: add_keywords
MCP-(list_keywords): list keywords in a campaign
"""
from unittest.mock import MagicMock, patch
import pytest

from src.mcp.google_ads_client import GoogleAdsClient


# ─── add_keywords (MCP-008) ────────────────────────────────────────────────────

def test_add_keywords_method_exists():
    """GoogleAdsClient should have an add_keywords method."""
    client = GoogleAdsClient()
    assert hasattr(client, "add_keywords"), "add_keywords method not found"


def test_add_keywords_returns_resource_names_on_success():
    """add_keywords should return a list of resource name strings on success."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.results = [
        MagicMock(resource_name="customers/123/adGroupCriteria/456"),
        MagicMock(resource_name="customers/123/adGroupCriteria/789"),
    ]
    mock_service.mutate_ad_group_criteria.return_value = mock_response

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service
    # Use get_type() which is the correct google-ads API — not resource_utils
    mock_client.get_type.return_value = MagicMock()

    with patch.object(client, "_get_client", return_value=mock_client):
        result = client.add_keywords(
            customer_id="123",
            ad_group_id="456",
            keywords=["summer sale", "discount code"],
        )

    assert result == [
        "customers/123/adGroupCriteria/456",
        "customers/123/adGroupCriteria/789",
    ]
    mock_service.mutate_ad_group_criteria.assert_called_once()


def test_add_keywords_uses_get_type_not_resource_utils():
    """add_keywords must use client.get_type() to create AdGroupCriterionOperation.

    The google-ads library uses get_type() (e.g. get_type("AdGroupCriterionOperation")).
    resource_utils.create_create_operation does not exist and would fail at runtime.
    """
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.results = []
    mock_service.mutate_ad_group_criteria.return_value = mock_response

    # Strict mock — raise AttributeError if create_create_operation is accessed
    class StrictMock(MagicMock):
        def __getattr__(self, name):
            if name == "create_create_operation":
                raise AttributeError("resource_utils.create_create_operation does not exist — use get_type()")
            return super().__getattr__(name)

    mock_client = StrictMock()
    mock_client.get_service.return_value = mock_service
    mock_client.get_type.return_value = MagicMock()

    with patch.object(client, "_get_client", return_value=mock_client):
        result = client.add_keywords(
            customer_id="123",
            ad_group_id="456",
            keywords=["test keyword"],
        )

    # Verify get_type was called with "AdGroupCriterionOperation"
    mock_client.get_type.assert_called_with("AdGroupCriterionOperation")


def test_add_keywords_requires_capability():
    """add_keywords should call _guard.check before making the API call."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.results = []
    mock_service.mutate_ad_group_criteria.return_value = mock_response

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service
    mock_client.get_type.return_value = MagicMock()

    with patch.object(client, "_get_client", return_value=mock_client):
        with patch.object(client, "_guard") as mock_guard:
            client.add_keywords(customer_id="123", ad_group_id="456", keywords=["test"])

    mock_guard.check.assert_called_once_with("google_ads.add_keywords")


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


# ─── get_keyword_performance (MCP-007) ─────────────────────────────────────────

def test_get_keyword_performance_method_exists():
    """GoogleAdsClient should have a get_keyword_performance method."""
    client = GoogleAdsClient()
    assert hasattr(client, "get_keyword_performance"), "get_keyword_performance method not found"


def test_get_keyword_performance_returns_keyword_metrics():
    """get_keyword_performance should return keyword-level metrics from Google Ads."""
    client = GoogleAdsClient()

    mock_row = MagicMock()
    mock_row.campaign.id = "123"
    mock_row.ad_group_criterion.keyword.text = "summer sale"
    mock_row.ad_group_criterion.keyword.match_type = "EXACT"
    mock_row.metrics.impressions = 1000
    mock_row.metrics.clicks = 50
    mock_row.metrics.ctr = 0.05
    mock_row.metrics.cost_micros = 5000000
    mock_row.metrics.conversions = 2.0
    mock_row.metrics.average_cpc = 100000

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__iter__ = MagicMock(return_value=iter([mock_row]))
    mock_service.search.return_value = mock_response

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        result = client.get_keyword_performance(customer_id="123", campaign_id="456")

    mock_service.search.assert_called_once()
    assert len(result) == 1
    assert result[0]["keyword"] == "summer sale"
    assert result[0]["impressions"] == 1000
    assert result[0]["clicks"] == 50


def test_get_keyword_performance_empty_when_no_results():
    """get_keyword_performance should return empty list when no keywords found."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__iter__ = MagicMock(return_value=iter([]))
    mock_service.search.return_value = mock_response

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        result = client.get_keyword_performance(customer_id="123", campaign_id="456")

    assert result == []


def test_get_keyword_performance_requires_capability():
    """get_keyword_performance should call _guard.check before making API call."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__iter__ = MagicMock(return_value=iter([]))
    mock_service.search.return_value = mock_response

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        with patch.object(client, "_guard") as mock_guard:
            client.get_keyword_performance(customer_id="123", campaign_id="456")

    mock_guard.check.assert_called_once_with("google_ads.get_keyword_performance")


# ─── list_keywords ───────────────────────────────────────────────────────────────

def test_list_keywords_method_exists():
    """GoogleAdsClient should have a list_keywords method."""
    client = GoogleAdsClient()
    assert hasattr(client, "list_keywords"), "list_keywords method not found"


def test_list_keywords_returns_keyword_objects():
    """list_keywords should return keyword objects with text, match_type, status."""
    client = GoogleAdsClient()

    mock_row = MagicMock()
    mock_row.ad_group_criterion.keyword.text = "running shoes"
    mock_row.ad_group_criterion.keyword.match_type = "EXACT"
    mock_row.ad_group_criterion.status = "ENABLED"
    mock_row.ad_group.id = "123"
    mock_row.campaign.id = "456"

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__iter__ = MagicMock(return_value=iter([mock_row]))
    mock_service.search.return_value = mock_response

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        result = client.list_keywords(customer_id="123", campaign_id="456")

    assert len(result) == 1
    assert result[0].text == "running shoes"
    assert result[0].match_type == "EXACT"
    assert result[0].status == "ENABLED"


def test_list_keywords_empty_when_no_keywords():
    """list_keywords should return empty list when no keywords found."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__iter__ = MagicMock(return_value=iter([]))
    mock_service.search.return_value = mock_response

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        result = client.list_keywords(customer_id="123", campaign_id="456")

    assert result == []


def test_list_keywords_requires_capability():
    """list_keywords should call _guard.check before making API call."""
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__iter__ = MagicMock(return_value=iter([]))
    mock_service.search.return_value = mock_response

    mock_client = MagicMock()
    mock_client.get_service.return_value = mock_service

    with patch.object(client, "_get_client", return_value=mock_client):
        with patch.object(client, "_guard") as mock_guard:
            client.list_keywords(customer_id="123", campaign_id="456")

    mock_guard.check.assert_called_once_with("google_ads.list_keywords")
