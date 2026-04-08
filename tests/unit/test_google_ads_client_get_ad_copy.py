"""
Test get_ad_copy and list_campaigns untested code paths.

get_ad_copy (lines 341-378): was untested, now covered
list_campaigns (lines 116-141): was untested, now covered using GoogleAdsService.search()
"""
from unittest.mock import MagicMock, patch

import pytest

from src.mcp.google_ads_client import GoogleAdsClient, GoogleAdsClientError


class TestGetAdCopy:
    """get_ad_copy fetches ad copy for a campaign."""

    @pytest.fixture
    def mock_guard(self, monkeypatch):
        mock = MagicMock()
        mock.check.return_value = None
        monkeypatch.setattr(
            "src.mcp.google_ads_client.CapabilityGuard", lambda: mock
        )
        return mock

    @pytest.fixture
    def mock_google_client(self, monkeypatch):
        mock = MagicMock()
        # _get_client calls GoogleAdsClient.load_from_env() inside a local import,
        # so we need to patch both the module-level reference and the actual google-ads import
        monkeypatch.setattr(
            "src.mcp.google_ads_client.GoogleAdsClient",
            lambda customer_id: mock,
        )
        monkeypatch.setattr(
            "google.ads.googleads.client.GoogleAdsClient.load_from_env",
            lambda: mock,
        )
        return mock

    def test_get_ad_copy_returns_list_of_ad_copy(self, mock_guard, mock_google_client):
        """
        get_ad_copy should return a list of AdCopy objects for a campaign.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        # Mock the service and response
        # Code accesses ad.ad.expanded_text_ad.headline_part1
        mock_ad = MagicMock()
        mock_ad.id = 999
        mock_ad.status = "ENABLED"
        mock_ad.ad.expanded_text_ad.headline_part1 = "Summer Shoes"
        mock_ad.ad.expanded_text_ad.headline_part2 = "Free Shipping"
        mock_ad.ad.expanded_text_ad.headline_part3 = "Buy Now"
        mock_ad.ad.expanded_text_ad.description1 = "Best deals online"
        mock_ad.ad.expanded_text_ad.description2 = "Shop today"

        mock_row = MagicMock()
        mock_row.ad_group_ad = mock_ad
        mock_row.ad_group.id = 111
        mock_row.campaign.id = 222

        mock_response = MagicMock()
        mock_response.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_service = MagicMock()
        mock_service.search.return_value = mock_response

        mock_google_client.get_service.return_value = mock_service

        result = client.get_ad_copy(customer_id="1234567890", campaign_id="222")

        assert len(result) == 1
        assert result[0].headline_part1 == "Summer Shoes"
        assert result[0].headline_part2 == "Free Shipping"
        assert result[0].campaign_id == "222"

    def test_get_ad_copy_guard_check_called(self, mock_guard, mock_google_client):
        """
        get_ad_copy should call guard.check with google_ads.get_ad_copy.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_service = MagicMock()
        mock_service.search.return_value = iter([])
        mock_google_client.get_service.return_value = mock_service

        client.get_ad_copy(customer_id="1234567890", campaign_id="222")

        mock_guard.check.assert_called_with("google_ads.get_ad_copy")

    def test_get_ad_copy_wraps_errors_in_google_ads_client_error(self, mock_guard, mock_google_client):
        """
        Errors from the Google Ads client should be wrapped in GoogleAdsClientError.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_service = MagicMock()
        mock_service.search.side_effect = Exception("ads API error")
        mock_google_client.get_service.return_value = mock_service

        with pytest.raises(GoogleAdsClientError, match="get_ad_copy failed"):
            client.get_ad_copy(customer_id="1234567890", campaign_id="222")


class TestListCampaigns:
    """list_campaigns fetches all campaigns for a customer via GoogleAdsService.search."""

    def test_list_campaigns_returns_list_of_campaigns(self):
        """
        list_campaigns should return a list of Campaign objects with correct field values.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        # Build mock campaign row matching the GAQL response structure
        mock_campaign = MagicMock()
        mock_campaign.id = 111
        mock_campaign.name = "Summer Sale"
        mock_campaign.status = "ENABLED"
        mock_campaign.advertising_channel_type = "SEARCH"
        mock_campaign.manual_cpc = None  # No CPC bid set

        mock_row = MagicMock()
        mock_row.campaign = mock_campaign

        mock_response = MagicMock()
        mock_response.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_service = MagicMock()
        mock_service.search.return_value = mock_response

        mock_google_client = MagicMock()
        mock_google_client.get_service.return_value = mock_service

        with patch.object(client, "_get_client", return_value=mock_google_client):
            with patch.object(client, "_guard") as mock_guard:
                mock_guard.check.return_value = None
                result = client.list_campaigns(customer_id="1234567890")

        assert len(result) == 1
        assert result[0].id == "111"
        assert result[0].name == "Summer Sale"
        assert result[0].status == "ENABLED"
        assert result[0].campaign_type == "SEARCH"
        assert result[0].customer_id == "1234567890"
        assert result[0].budget_amount_micros == 0  # manual_cpc is None

    def test_list_campaigns_returns_empty_list_when_no_results(self):
        """
        list_campaigns should return [] when no campaigns exist.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_response = MagicMock()
        mock_response.__iter__ = MagicMock(return_value=iter([]))

        mock_service = MagicMock()
        mock_service.search.return_value = mock_response

        mock_google_client = MagicMock()
        mock_google_client.get_service.return_value = mock_service

        with patch.object(client, "_get_client", return_value=mock_google_client):
            with patch.object(client, "_guard") as mock_guard:
                mock_guard.check.return_value = None
                result = client.list_campaigns(customer_id="1234567890")

        assert result == []

    def test_list_campaigns_guard_check_called(self):
        """
        list_campaigns should call guard.check with google_ads.list_campaigns.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_response = MagicMock()
        mock_response.__iter__ = MagicMock(return_value=iter([]))

        mock_service = MagicMock()
        mock_service.search.return_value = mock_response

        mock_google_client = MagicMock()
        mock_google_client.get_service.return_value = mock_service

        with patch.object(client, "_get_client", return_value=mock_google_client):
            with patch.object(client, "_guard") as mock_guard:
                mock_guard.check.return_value = None
                client.list_campaigns(customer_id="1234567890")

        mock_guard.check.assert_called_with("google_ads.list_campaigns")

    def test_list_campaigns_wraps_errors_in_google_ads_client_error(self):
        """
        Errors from the Google Ads client should be wrapped in GoogleAdsClientError.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_service = MagicMock()
        mock_service.search.side_effect = Exception("ads API error")

        mock_google_client = MagicMock()
        mock_google_client.get_service.return_value = mock_service

        with patch.object(client, "_get_client", return_value=mock_google_client):
            with patch.object(client, "_guard") as mock_guard:
                mock_guard.check.return_value = None
                with pytest.raises(GoogleAdsClientError, match="list_campaigns failed"):
                    client.list_campaigns(customer_id="1234567890")


class TestGetCampaign:
    """get_campaign fetches a single campaign by ID via GoogleAdsService.search."""

    def test_get_campaign_returns_campaign_object(self):
        """
        get_campaign should return a Campaign object with correct field values.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_campaign = MagicMock()
        mock_campaign.id = 111
        mock_campaign.name = "Summer Sale"
        mock_campaign.status = "ENABLED"
        mock_campaign.advertising_channel_type = "SEARCH"
        mock_campaign.manual_cpc = None

        mock_row = MagicMock()
        mock_row.campaign = mock_campaign

        mock_response = MagicMock()
        mock_response.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_service = MagicMock()
        mock_service.search.return_value = mock_response

        mock_google_client = MagicMock()
        mock_google_client.get_service.return_value = mock_service

        with patch.object(client, "_get_client", return_value=mock_google_client):
            with patch.object(client, "_guard") as mock_guard:
                mock_guard.check.return_value = None
                result = client.get_campaign(customer_id="1234567890", campaign_id="111")

        assert result.id == "111"
        assert result.name == "Summer Sale"
        assert result.status == "ENABLED"
        assert result.campaign_type == "SEARCH"
        assert result.customer_id == "1234567890"
        assert result.budget_amount_micros == 0

    def test_get_campaign_guard_check_called(self):
        """
        get_campaign should call guard.check with google_ads.get_campaign.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_row = MagicMock()
        mock_row.campaign.name = "Test"

        mock_response = MagicMock()
        mock_response.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_service = MagicMock()
        mock_service.search.return_value = mock_response

        mock_google_client = MagicMock()
        mock_google_client.get_service.return_value = mock_service

        with patch.object(client, "_get_client", return_value=mock_google_client):
            with patch.object(client, "_guard") as mock_guard:
                mock_guard.check.return_value = None
                client.get_campaign(customer_id="1234567890", campaign_id="111")

        mock_guard.check.assert_called_with("google_ads.get_campaign")

    def test_get_campaign_wraps_errors_in_google_ads_client_error(self):
        """
        Errors from the Google Ads client should be wrapped in GoogleAdsClientError.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_service = MagicMock()
        mock_service.search.side_effect = Exception("ads API error")

        mock_google_client = MagicMock()
        mock_google_client.get_service.return_value = mock_service

        with patch.object(client, "_get_client", return_value=mock_google_client):
            with patch.object(client, "_guard") as mock_guard:
                mock_guard.check.return_value = None
                with pytest.raises(GoogleAdsClientError, match="get_campaign failed"):
                    client.get_campaign(customer_id="1234567890", campaign_id="111")

