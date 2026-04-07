"""
RED: Test that remove_keywords uses the correct google-ads API.
Like test_add_keywords_uses_get_type_not_resource_utils, this catches the same
bug: resource_utils.create_delete_operation does not exist — must use get_type().
"""
from unittest.mock import MagicMock, patch
import pytest

from src.mcp.google_ads_client import GoogleAdsClient


def test_remove_keywords_uses_get_type_not_resource_utils():
    """remove_keywords must use client.get_type("AdGroupCriterionOperation") to create delete operations.

    The google-ads library uses get_type() for all operation types.
    resource_utils.create_delete_operation does not exist and would fail at runtime.
    """
    client = GoogleAdsClient()

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.results = []
    mock_service.mutate_ad_group_criteria.return_value = mock_response

    # StrictMock — raise AttributeError if create_delete_operation is accessed
    class StrictMock(MagicMock):
        def __getattr__(self, name):
            if name == "create_delete_operation":
                raise AttributeError(
                    "resource_utils.create_delete_operation does not exist — "
                    "use get_type('AdGroupCriterionOperation') for delete operations too"
                )
            return super().__getattr__(name)

    mock_client = StrictMock()
    mock_client.get_service.return_value = mock_service
    mock_client.get_type.return_value = MagicMock()

    with patch.object(client, "_get_client", return_value=mock_client):
        result = client.remove_keywords(
            customer_id="123",
            keyword_resource_names=["customers/123/adGroups/456/criteria/789"],
        )

    # Verify get_type was called (not resource_utils.create_delete_operation)
    mock_client.get_type.assert_called_with("AdGroupCriterionOperation")
