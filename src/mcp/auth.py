"""
Google Ads MCP authentication — OAuth2 refresh token + developer token flow.

Google Ads API requires:
1. A developer token (from Google)
2. OAuth2 credentials (client_id, client_secret, refresh_token)
   for the Google Ads API (not the Google Ads UI)

The refresh token flow is used so the agent doesn't need interactive login.
Tokens are refreshed automatically by the google-ads library.
"""
from dataclasses import dataclass
import logging

from src.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class GoogleAdsCredentials:
    """
    Google Ads API credentials loaded from environment.
    These are used to configure the google-ads-python client.
    """
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    customer_id: str  # The MCC or customer ID to operate on

    @classmethod
    def from_settings(cls) -> "GoogleAdsCredentials":
        """Load credentials from application settings."""
        settings = get_settings()
        return cls(
            developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN,
            client_id=settings.GOOGLE_ADS_CLIENT_ID,
            client_secret=settings.GOOGLE_ADS_CLIENT_SECRET,
            refresh_token=settings.GOOGLE_ADS_REFRESH_TOKEN,  # type: ignore[attr-defined]
            customer_id=settings.GOOGLE_ADS_CUSTOMER_ID,  # type: ignore[attr-defined]
        )

    def to_google_ads_dict(self) -> dict[str, str]:
        """
        Convert to the dict format expected by google-ads-python client.
        Loaded via GoogleAdsClient.load_from_env() which reads from env vars,
        but we also support programmatic configuration.
        """
        return {
            "DEVELOPER_TOKEN": self.developer_token,
            "GOOGLE_ADS_CLIENT_ID": self.client_id,
            "GOOGLE_ADS_CLIENT_SECRET": self.client_secret,
            "GOOGLE_ADS_REFRESH_TOKEN": self.refresh_token,
            "LOGIN_CUSTOMER_ID": self.customer_id,
        }

    def validate(self) -> list[str]:
        """
        Validate that all required credentials are present and non-empty.
        Returns a list of missing field names. Empty list means valid.
        """
        missing = []
        if not self.developer_token:
            missing.append("GOOGLE_ADS_DEVELOPER_TOKEN")
        if not self.client_id:
            missing.append("GOOGLE_ADS_CLIENT_ID")
        if not self.client_secret:
            missing.append("GOOGLE_ADS_CLIENT_SECRET")
        if not self.refresh_token:
            missing.append("GOOGLE_ADS_REFRESH_TOKEN")
        if not self.customer_id:
            missing.append("GOOGLE_ADS_CUSTOMER_ID")
        return missing


def get_credentials() -> GoogleAdsCredentials:
    """
    Get validated Google Ads credentials.
    Raises ValueError if any required credential is missing.
    """
    creds = GoogleAdsCredentials.from_settings()
    missing = creds.validate()
    if missing:
        raise ValueError(f"Missing Google Ads credentials: {', '.join(missing)}")
    logger.info("google_ads_credentials_loaded", extra={"customer_id": creds.customer_id})
    return creds
