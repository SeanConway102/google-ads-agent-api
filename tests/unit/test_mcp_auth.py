"""
RED: Tests for Google Ads OAuth2 credential management (src/mcp/auth.py).
"""
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest

from src.mcp.auth import GoogleAdsCredentials, get_credentials


class TestGoogleAdsCredentialsValidate:
    """GoogleAdsCredentials.validate()"""

    def test_validate_returns_empty_when_all_fields_present(self):
        """validate() returns [] when all credentials are non-empty."""
        creds = GoogleAdsCredentials(
            developer_token="dev-token",
            client_id="client-id",
            client_secret="client-secret",
            refresh_token="refresh-token",
            customer_id="123-456-7890",
        )
        assert creds.validate() == []

    def test_validate_returns_all_missing_when_all_empty(self):
        """validate() returns all field names when all are empty."""
        creds = GoogleAdsCredentials(
            developer_token="",
            client_id="",
            client_secret="",
            refresh_token="",
            customer_id="",
        )
        missing = creds.validate()
        assert "GOOGLE_ADS_DEVELOPER_TOKEN" in missing
        assert "GOOGLE_ADS_CLIENT_ID" in missing
        assert "GOOGLE_ADS_CLIENT_SECRET" in missing
        assert "GOOGLE_ADS_REFRESH_TOKEN" in missing
        assert "GOOGLE_ADS_CUSTOMER_ID" in missing
        assert len(missing) == 5

    def test_validate_returns_only_missing_fields(self):
        """validate() returns only the fields that are empty."""
        creds = GoogleAdsCredentials(
            developer_token="dev-token",
            client_id="",  # missing
            client_secret="client-secret",
            refresh_token="",
            customer_id="cust-123",
        )
        missing = creds.validate()
        assert missing == ["GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_REFRESH_TOKEN"]
        assert len(missing) == 2

    def test_validate_returns_only_empty_whitespace_fields(self):
        """Fields containing only whitespace are treated as missing."""
        creds = GoogleAdsCredentials(
            developer_token="  ",
            client_id="client-id",
            client_secret="",
            refresh_token="token",
            customer_id="cust",
        )
        missing = creds.validate()
        assert "GOOGLE_ADS_DEVELOPER_TOKEN" in missing
        assert "GOOGLE_ADS_CLIENT_SECRET" in missing


class TestGoogleAdsCredentialsToGoogleAdsDict:
    """GoogleAdsCredentials.to_google_ads_dict()"""

    def test_to_google_ads_dict_returns_correct_keys(self):
        """to_google_ads_dict() returns keys expected by google-ads-python."""
        creds = GoogleAdsCredentials(
            developer_token="dev-token",
            client_id="my-client-id",
            client_secret="my-secret",
            refresh_token="my-refresh",
            customer_id="123-456-7890",
        )
        d = creds.to_google_ads_dict()
        assert d["DEVELOPER_TOKEN"] == "dev-token"
        assert d["GOOGLE_ADS_CLIENT_ID"] == "my-client-id"
        assert d["GOOGLE_ADS_CLIENT_SECRET"] == "my-secret"
        assert d["GOOGLE_ADS_REFRESH_TOKEN"] == "my-refresh"
        assert d["LOGIN_CUSTOMER_ID"] == "123-456-7890"

    def test_to_google_ads_dict_preserves_empty_strings(self):
        """to_google_ads_dict() preserves empty strings (doesn't filter)."""
        creds = GoogleAdsCredentials(
            developer_token="",
            client_id="id",
            client_secret="",
            refresh_token="",
            customer_id="",
        )
        d = creds.to_google_ads_dict()
        assert d["DEVELOPER_TOKEN"] == ""
        assert d["GOOGLE_ADS_CLIENT_SECRET"] == ""


class TestGoogleAdsCredentialsFromSettings:
    """GoogleAdsCredentials.from_settings()"""

    def test_from_settings_loads_values_from_settings(self):
        """from_settings() reads from application settings."""
        mock_settings = MagicMock()
        mock_settings.GOOGLE_ADS_DEVELOPER_TOKEN = "set-dev-token"
        mock_settings.GOOGLE_ADS_CLIENT_ID = "set-client-id"
        mock_settings.GOOGLE_ADS_CLIENT_SECRET = "set-secret"
        mock_settings.GOOGLE_ADS_REFRESH_TOKEN = "set-refresh"
        mock_settings.GOOGLE_ADS_CUSTOMER_ID = "set-customer"

        with patch("src.mcp.auth.get_settings", return_value=mock_settings):
            creds = GoogleAdsCredentials.from_settings()

        assert creds.developer_token == "set-dev-token"
        assert creds.client_id == "set-client-id"
        assert creds.client_secret == "set-secret"
        assert creds.refresh_token == "set-refresh"
        assert creds.customer_id == "set-customer"


class TestGetCredentials:
    """get_credentials() — validated credential getter."""

    def test_get_credentials_returns_valid_credentials(self):
        """get_credentials() returns GoogleAdsCredentials when all fields present."""
        mock_settings = MagicMock()
        mock_settings.GOOGLE_ADS_DEVELOPER_TOKEN = "dev"
        mock_settings.GOOGLE_ADS_CLIENT_ID = "id"
        mock_settings.GOOGLE_ADS_CLIENT_SECRET = "secret"
        mock_settings.GOOGLE_ADS_REFRESH_TOKEN = "refresh"
        mock_settings.GOOGLE_ADS_CUSTOMER_ID = "cust"

        with patch("src.mcp.auth.get_settings", return_value=mock_settings):
            creds = get_credentials()

        assert isinstance(creds, GoogleAdsCredentials)
        assert creds.developer_token == "dev"
        assert creds.customer_id == "cust"

    def test_get_credentials_raises_when_credentials_missing(self):
        """get_credentials() raises ValueError listing all missing fields."""
        mock_settings = MagicMock()
        mock_settings.GOOGLE_ADS_DEVELOPER_TOKEN = ""
        mock_settings.GOOGLE_ADS_CLIENT_ID = ""
        mock_settings.GOOGLE_ADS_CLIENT_SECRET = ""
        mock_settings.GOOGLE_ADS_REFRESH_TOKEN = ""
        mock_settings.GOOGLE_ADS_CUSTOMER_ID = ""

        with patch("src.mcp.auth.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError) as exc_info:
                get_credentials()

        error_msg = str(exc_info.value)
        assert "GOOGLE_ADS_DEVELOPER_TOKEN" in error_msg
        assert "GOOGLE_ADS_CLIENT_ID" in error_msg
        assert "Missing Google Ads credentials" in error_msg

    def test_get_credentials_raises_with_partial_credentials(self):
        """get_credentials() raises ValueError listing only the missing fields."""
        mock_settings = MagicMock()
        mock_settings.GOOGLE_ADS_DEVELOPER_TOKEN = "dev-token"
        mock_settings.GOOGLE_ADS_CLIENT_ID = ""
        mock_settings.GOOGLE_ADS_CLIENT_SECRET = "secret"
        mock_settings.GOOGLE_ADS_REFRESH_TOKEN = "refresh"
        mock_settings.GOOGLE_ADS_CUSTOMER_ID = ""

        with patch("src.mcp.auth.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError) as exc_info:
                get_credentials()

        error_msg = str(exc_info.value)
        assert "GOOGLE_ADS_CLIENT_ID" in error_msg
        assert "GOOGLE_ADS_CUSTOMER_ID" in error_msg
        assert "GOOGLE_ADS_DEVELOPER_TOKEN" not in error_msg
