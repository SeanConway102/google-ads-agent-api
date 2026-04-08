"""
Test get_performance_report and related untested code paths.

Lines 249-307: get_performance_report is untested (now covered)
Lines 575-576: update_keyword_match_types empty updates early return (now covered)
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.mcp.google_ads_client import GoogleAdsClient, GoogleAdsClientError


class TestGetPerformanceReport:
    """get_performance_report fetches metrics for a campaign over a date range."""

    def test_get_performance_report_returns_performance_report(self):
        """
        get_performance_report should return a PerformanceReport with correct field values.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        mock_row = MagicMock()
        mock_row.metrics.impressions = 10000
        mock_row.metrics.clicks = 500
        mock_row.metrics.cost_micros = 5000000
        mock_row.metrics.conversions = 10.0
        mock_row.metrics.ctr = 0.05
        mock_row.metrics.average_cpc = 10000

        mock_response = MagicMock()
        mock_response.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_service = MagicMock()
        mock_service.search.return_value = mock_response

        mock_google_client = MagicMock()
        mock_google_client.get_service.return_value = mock_service

        with patch.object(client, "_get_client", return_value=mock_google_client):
            with patch.object(client, "_guard") as mock_guard:
                mock_guard.check.return_value = None
                result = client.get_performance_report(
                    customer_id="1234567890",
                    campaign_id="111",
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                )

        assert result.campaign_id == "111"
        assert result.date_range == "2024-01-01:2024-01-31"
        assert result.impressions == 10000
        assert result.clicks == 500
        assert result.spend_micros == 5000000
        assert result.conversions == 10.0
        assert result.ctr == 0.05
        assert result.avg_cpc_micros == 10000

    def test_get_performance_report_returns_zeros_when_no_data(self):
        """
        get_performance_report should return zeros when no metrics found for date range.
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
                result = client.get_performance_report(
                    customer_id="1234567890",
                    campaign_id="111",
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                )

        assert result.impressions == 0
        assert result.clicks == 0
        assert result.spend_micros == 0
        assert result.conversions == 0.0
        assert result.ctr == 0.0
        assert result.avg_cpc_micros == 0
        assert result.date_range == "2024-01-01:2024-01-31"

    def test_get_performance_report_guard_check_called(self):
        """
        get_performance_report should call guard.check with google_ads.get_performance_report.
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
                client.get_performance_report(
                    customer_id="1234567890",
                    campaign_id="111",
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                )

        mock_guard.check.assert_called_with("google_ads.get_performance_report")

    def test_get_performance_report_wraps_errors_in_google_ads_client_error(self):
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
                with pytest.raises(GoogleAdsClientError, match="get_performance_report failed"):
                    client.get_performance_report(
                        customer_id="1234567890",
                        campaign_id="111",
                        start_date=date(2024, 1, 1),
                        end_date=date(2024, 1, 31),
                    )

    def test_get_performance_report_rejects_non_numeric_campaign_id(self):
        """
        get_performance_report must reject non-numeric campaign_id to prevent GAQL injection.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        with pytest.raises(GoogleAdsClientError, match="must be numeric"):
            client.get_performance_report(
                customer_id="1234567890",
                campaign_id="abc",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )


class TestUpdateKeywordMatchTypesEmptyUpdates:
    """update_keyword_match_types returns [] early when updates is empty."""

    def test_update_keyword_match_types_empty_returns_early_without_api_call(self):
        """
        When updates is empty, update_keyword_match_types returns [] without
        calling the guard or making any API call.
        """
        client = GoogleAdsClient(customer_id="1234567890")

        with patch.object(client, "_guard") as mock_guard:
            result = client.update_keyword_match_types(customer_id="123", updates=[])

        assert result == []
        mock_guard.check.assert_not_called()


class TestCapabilityDeniedPropagates:
    """_call re-raises CapabilityDenied without wrapping it."""

    def test_capability_denied_propagates_without_wrapping(self):
        """
        When _guard.check raises CapabilityDenied, it should propagate
        uncaught — not be wrapped in GoogleAdsClientError.
        """
        from src.mcp.capability_guard import CapabilityDenied

        client = GoogleAdsClient(customer_id="1234567890")

        # Make guard.check raise CapabilityDenied
        with patch.object(client, "_guard") as mock_guard:
            mock_guard.check.side_effect = CapabilityDenied("google_ads.list_campaigns")
            with pytest.raises(CapabilityDenied):
                client.list_campaigns(customer_id="1234567890")

