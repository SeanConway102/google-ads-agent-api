"""
RED: Test for GoogleAdsClient.remove_keywords method.
MCP-004: Agent can remove keywords via MCP.
Tests that the method calls the correct GAds service operation.
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
