"""
RED: Test get_ad_copy and get_keyword_performance untested code paths.

Lines 341-378: get_ad_copy is untested
Lines 412-423: get_keyword_performance is untested
Both are high-value Google Ads read operations.
"""
import uuid
from unittest.mock import MagicMock

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


class TestGetKeywordPerformance:
    """get_keyword_performance fetches keyword metrics."""

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

    def test_get_keyword_performance_returns_list(self, mock_guard, mock_google_client):
        """
        get_keyword_performance should return a list of dict objects.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        # Code accesses row.ad_group_criterion.keyword.text and row.metrics
        mock_row = MagicMock()
        mock_row.ad_group_criterion.keyword.text = "running shoes"
        mock_row.ad_group_criterion.keyword.match_type = "BROAD"
        mock_row.metrics.clicks = 100
        mock_row.metrics.impressions = 5000
        mock_row.metrics.ctr = 0.02
        mock_row.metrics.cost_micros = 150000
        mock_row.metrics.conversions = 0
        mock_row.metrics.average_cpc = 200000

        mock_response = MagicMock()
        mock_response.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_service = MagicMock()
        mock_service.search.return_value = mock_response
        mock_google_client.get_service.return_value = mock_service

        result = client.get_keyword_performance(
            customer_id="1234567890",
            campaign_id="444",
        )

        assert len(result) == 1
        assert result[0]["keyword"] == "running shoes"
        assert result[0]["match_type"] == "BROAD"
        assert result[0]["clicks"] == 100

    def test_get_keyword_performance_guard_check_called(self, mock_guard, mock_google_client):
        """
        get_keyword_performance should call guard.check with google_ads.get_keyword_performance.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_service = MagicMock()
        mock_service.search.return_value = iter([])
        mock_google_client.get_service.return_value = mock_service

        client.get_keyword_performance(
            customer_id="1234567890",
            campaign_id="444",
        )

        mock_guard.check.assert_called_with("google_ads.get_keyword_performance")
