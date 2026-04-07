"""
RED: Tests that update_campaign_budget and update_campaign_status use the correct
google-ads API (get_type, not resource_utils.create_update_operation).
These are currently blocked by the capability guard but must use the correct API
in case they are ever enabled — resource_utils.create_update_operation does not exist.
"""
from unittest.mock import MagicMock, patch
import pytest

from src.mcp.google_ads_client import GoogleAdsClient


class TestUpdateCampaignBudgetApi:
    """Test that update_campaign_budget uses client.get_type() not resource_utils."""

    def test_update_campaign_budget_uses_get_type_not_resource_utils(self):
        """update_campaign_budget must use client.get_type("CampaignOperation").

        resource_utils.create_update_operation does not exist in the google-ads library.
        """
        client = GoogleAdsClient()

        mock_service = MagicMock()
        mock_response = MagicMock()
        mock_response.results = [MagicMock(resource_name="customers/123/campaigns/456")]
        mock_service.mutate_campaigns.return_value = mock_response
        mock_service.campaign_path.return_value = "customers/123/campaigns/456"

        class StrictMock(MagicMock):
            def __getattr__(self, name):
                if name == "create_update_operation":
                    raise AttributeError(
                        "resource_utils.create_update_operation does not exist — "
                        "use get_type('CampaignOperation')"
                    )
                return super().__getattr__(name)

        mock_client = StrictMock()
        mock_client.get_service.return_value = mock_service
        mock_client.get_type.return_value = MagicMock()

        from src.mcp.capability_guard import CapabilityGuard
        # Allow this operation so execution reaches the mock (guard blocks before fn runs)
        allowed_guard = CapabilityGuard(allowed_operations={"google_ads.update_campaign_budget"})
        client = GoogleAdsClient(guard=allowed_guard)

        with patch.object(client, "_get_client", return_value=mock_client):
            result = client.update_campaign_budget(
                customer_id="123",
                campaign_id="456",
                budget_amount_micros=5000000,
            )

        mock_client.get_type.assert_called_with("CampaignOperation")


class TestUpdateCampaignStatusApi:
    """Test that update_campaign_status uses client.get_type() not resource_utils."""

    def test_update_campaign_status_uses_get_type_not_resource_utils(self):
        """update_campaign_status must use client.get_type("CampaignOperation").

        resource_utils.create_update_operation does not exist in the google-ads library.
        """
        from src.mcp.capability_guard import CapabilityGuard
        # Allow this operation so execution reaches the mock (guard blocks before fn runs)
        allowed_guard = CapabilityGuard(allowed_operations={"google_ads.update_campaign_status"})
        client = GoogleAdsClient(guard=allowed_guard)

        mock_service = MagicMock()
        mock_response = MagicMock()
        mock_response.results = [MagicMock(resource_name="customers/123/campaigns/456")]
        mock_service.mutate_campaigns.return_value = mock_response
        mock_service.campaign_path.return_value = "customers/123/campaigns/456"

        class StrictMock(MagicMock):
            def __getattr__(self, name):
                if name == "create_update_operation":
                    raise AttributeError(
                        "resource_utils.create_update_operation does not exist — "
                        "use get_type('CampaignOperation')"
                    )
                return super().__getattr__(name)

        mock_client = StrictMock()
        mock_client.get_service.return_value = mock_service
        mock_client.get_type.return_value = MagicMock()

        with patch.object(client, "_get_client", return_value=mock_client):
            result = client.update_campaign_status(
                customer_id="123",
                campaign_id="456",
                status="PAUSED",
            )

        mock_client.get_type.assert_called_with("CampaignOperation")
