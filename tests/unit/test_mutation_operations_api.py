"""
RED: Tests that update_keyword_bids and update_keyword_match_types use the correct
google-ads API (get_type, not resource_utils.create_update_operation).
These are capability-allowed operations — if they use the wrong API they silently fail at runtime.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.mcp.google_ads_client import GoogleAdsClient


class TestUpdateKeywordBidsApi:
    """Test that update_keyword_bids uses client.get_type() not resource_utils."""

    def test_update_keyword_bids_uses_get_type_not_resource_utils(self):
        """update_keyword_bids must use client.get_type("AdGroupCriterionOperation").

        resource_utils.create_update_operation does not exist in the google-ads library.
        """
        client = GoogleAdsClient()

        mock_service = MagicMock()
        mock_response = MagicMock()
        mock_response.results = []
        mock_service.mutate_ad_group_criteria.return_value = mock_response

        class StrictMock(MagicMock):
            def __getattr__(self, name):
                if name == "create_update_operation":
                    raise AttributeError(
                        "resource_utils.create_update_operation does not exist — "
                        "use get_type('AdGroupCriterionOperation')"
                    )
                return super().__getattr__(name)

        mock_client = StrictMock()
        mock_client.get_service.return_value = mock_service
        mock_client.get_type.return_value = MagicMock()

        with patch.object(client, "_get_client", return_value=mock_client):
            result = client.update_keyword_bids(
                customer_id="123",
                updates=[{"resource_name": "customers/123/adGroups/456/criteria/789", "cpc_bid_micros": 150000}],
            )

        mock_client.get_type.assert_called_with("AdGroupCriterionOperation")


class TestUpdateKeywordMatchTypesApi:
    """Test that update_keyword_match_types uses client.get_type() not resource_utils."""

    def test_update_keyword_match_types_uses_get_type_not_resource_utils(self):
        """update_keyword_match_types must use client.get_type("AdGroupCriterionOperation").

        resource_utils.create_update_operation does not exist in the google-ads library.
        """
        client = GoogleAdsClient()

        mock_service = MagicMock()
        mock_response = MagicMock()
        mock_response.results = []
        mock_service.mutate_ad_group_criteria.return_value = mock_response

        class StrictMock(MagicMock):
            def __getattr__(self, name):
                if name == "create_update_operation":
                    raise AttributeError(
                        "resource_utils.create_update_operation does not exist — "
                        "use get_type('AdGroupCriterionOperation')"
                    )
                return super().__getattr__(name)

        mock_client = StrictMock()
        mock_client.get_service.return_value = mock_service
        mock_client.get_type.return_value = MagicMock()

        with patch.object(client, "_get_client", return_value=mock_client):
            result = client.update_keyword_match_types(
                customer_id="123",
                updates=[{"resource_name": "customers/123/adGroups/456/criteria/789", "match_type": "PHRASE"}],
            )

        mock_client.get_type.assert_called_with("AdGroupCriterionOperation")
