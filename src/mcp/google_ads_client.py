"""
Google Ads API client — typed wrapper around google-ads-py.

Provides a clean, typed interface for the operations permitted by CapabilityGuard.
All methods verify capabilities before making API calls.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.v17.services.services.campaign_service import CampaignServiceClient
from google.ads.googleads.v17.services.services.keyword_plan_service import KeywordPlanServiceClient
from google.ads.googleads.v17.services.types.campaign_service import (
    ListCampaignsRequest,
    GetCampaignRequest,
)
from google.ads.googleads.v17.services.types.keyword_plan_service import (
    GenerateKeywordIdeasRequest,
)
from google.ads.googleads.v17.services.types.google_ads_service import SearchGoogleAdsRequest

from src.config import get_settings
from src.mcp.capability_guard import CapabilityGuard, CapabilityDenied


@dataclass
class Campaign:
    """A Google Ads campaign — normalized response type."""
    id: str
    name: str
    status: str
    campaign_type: str
    customer_id: str
    budget_amount_micros: int
    start_date: str | None
    end_date: str | None


@dataclass
class Keyword:
    """A Google Ads keyword — normalized response type."""
    id: str
    text: str
    match_type: str
    campaign_id: str
    ad_group_id: str
    status: str


@dataclass
class PerformanceReport:
    """Campaign performance metrics — normalized response type."""
    campaign_id: str
    date_range: str
    impressions: int
    clicks: int
    spend_micros: int
    conversions: float
    ctr: float
    avg_cpc_micros: int


class GoogleAdsClientError(Exception):
    """Base exception for Google Ads client errors."""
    pass


class GoogleAdsAPIError(GoogleAdsClientError):
    """Raised when the Google Ads API returns an error."""
    def __init__(self, error_code: int, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(f"Google Ads API error {error_code}: {message}")


class GoogleAdsClient:
    """
    Typed Google Ads API client with capability enforcement.

    All operations go through CapabilityGuard.check() before execution.
    Requires GOOGLE_ADS_* env vars and a valid refresh token flow.
    """

    def __init__(
        self,
        guard: CapabilityGuard | None = None,
        customer_id: str | None = None,
    ) -> None:
        self._settings = get_settings()
        self._guard = guard or CapabilityGuard()
        self._customer_id = customer_id or ""
        self._client: GoogleAdsClient | None = None

    def _get_client(self) -> GoogleAdsClient:
        """Lazily initialize the google-ads client."""
        if self._client is None:
            self._client = GoogleAdsClient.load_from_env()
        return self._client

    def _call(self, operation: str, fn, *args, **kwargs) -> Any:
        """Execute a Google Ads call after capability check."""
        self._guard.check(operation)
        try:
            return fn(*args, **kwargs)
        except CapabilityDenied:
            raise
        except Exception as exc:
            raise GoogleAdsClientError(f"{operation} failed: {exc}") from exc

    # ─── Read operations ─────────────────────────────────────────────────────

    def list_campaigns(self, customer_id: str) -> list[Campaign]:
        """
        List all campaigns for a customer ID.
        Requires: google_ads.list_campaigns
        """
        def _call() -> list[Campaign]:
            client = self._get_client()
            service: CampaignServiceClient = client.get_service("CampaignService")
            request = ListCampaignsRequest(customer_id=customer_id)
            response = service.list_campaigns(request=request)
            campaigns = []
            for row in response.results:
                campaign = row.campaign
                campaigns.append(Campaign(
                    id=str(campaign.id),
                    name=campaign.name,
                    status=str(campaign.status),
                    campaign_type=str(campaign.advertising_channel_type),
                    customer_id=customer_id,
                    budget_amount_micros=campaign.manual_cpc.enhanced_cpc.cpc_bid_micros,
                    start_date=campaign.start_date or None,
                    end_date=campaign.end_date or None,
                ))
            return campaigns

        return self._call("google_ads.list_campaigns", _call)

    def get_campaign(self, customer_id: str, campaign_id: str) -> Campaign:
        """
        Get a single campaign by ID.
        Requires: google_ads.get_campaign
        """
        def _call() -> Campaign:
            client = self._get_client()
            service: CampaignServiceClient = client.get_service("CampaignService")
            resource_name = service.campaign_path(customer_id, campaign_id)
            request = GetCampaignRequest(customer_id=customer_id, campaign_id=campaign_id)
            response = service.get_campaign(request=request)
            campaign = response.campaign
            return Campaign(
                id=str(campaign.id),
                name=campaign.name,
                status=str(campaign.status),
                campaign_type=str(campaign.advertising_channel_type),
                customer_id=customer_id,
                budget_amount_micros=campaign.manual_cpc.enhanced_cpc.cpc_bid_micros,
                start_date=campaign.start_date or None,
                end_date=campaign.end_date or None,
            )

        return self._call("google_ads.get_campaign", _call)

    def get_performance_report(
        self,
        customer_id: str,
        campaign_id: str,
        start_date: date,
        end_date: date,
    ) -> PerformanceReport:
        """
        Get performance metrics for a campaign over a date range.
        Requires: google_ads.get_performance_report
        """
        def _call() -> PerformanceReport:
            client = self._get_client()
            service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT
                    campaign.id,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.ctr,
                    metrics.average_cpc
                FROM campaign
                WHERE campaign.id = {campaign_id}
                AND segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
            """
            request = SearchGoogleAdsRequest(customer_id=customer_id, query=query)
            response = service.search(request=request)
            row = next(iter(response), None)
            if row is None:
                return PerformanceReport(
                    campaign_id=campaign_id,
                    date_range=f"{start_date.isoformat()}:{end_date.isoformat()}",
                    impressions=0, clicks=0, spend_micros=0,
                    conversions=0.0, ctr=0.0, avg_cpc_micros=0,
                )
            m = row.metrics
            return PerformanceReport(
                campaign_id=campaign_id,
                date_range=f"{start_date.isoformat()}:{end_date.isoformat()}",
                impressions=m.impressions,
                clicks=m.clicks,
                spend_micros=m.cost_micros,
                conversions=m.conversions,
                ctr=m.ctr,
                avg_cpc_micros=m.average_cpc,
            )

        return self._call("google_ads.get_performance_report", _call)

    def get_account_hierarchy(self, customer_id: str) -> dict[str, Any]:
        """
        Get the account hierarchy (MCC → customer accounts).
        Requires: google_ads.get_account_hierarchy
        """
        def _call() -> dict[str, Any]:
            client = self._get_client()
            service = client.get_service("CustomerService")
            resource_name = service.customer_path(customer_id)
            request = {"customer": resource_name}
            response = service.get_customer(request=request)
            customer = response.customer
            return {
                "id": customer.id,
                "descriptive_name": customer.descriptive_name,
                "currency_code": customer.currency_code,
                "time_zone": customer.time_zone,
            }

        return self._call("google_ads.get_account_hierarchy", _call)

    # ─── Write operations (require explicit capability) ─────────────────────

    def update_campaign_budget(
        self,
        customer_id: str,
        campaign_id: str,
        budget_amount_micros: int,
    ) -> bool:
        """
        Update a campaign's daily budget.
        Requires: google_ads.update_campaign_budget
        """
        def _call() -> bool:
            client = self._get_client()
            service: CampaignServiceClient = client.get_service("CampaignService")
            resource_name = service.campaign_path(customer_id, campaign_id)
            operation = client.resource_utils.create_update_operation(
                "Campaign",
                {"resource_name": resource_name, "manual_cpc": {"cpc_bid_micros": budget_amount_micros}},
            )
            response = service.mutate_campaigns(customer_id=customer_id, operations=[operation])
            return len(response.results) > 0

        return self._call("google_ads.update_campaign_budget", _call)

    def update_campaign_status(
        self,
        customer_id: str,
        campaign_id: str,
        status: str,  # "ENABLED", "PAUSED", "REMOVED"
    ) -> bool:
        """
        Update a campaign's status (pause/resume).
        Requires: google_ads.update_campaign_status
        """
        def _call() -> bool:
            client = self._get_client()
            service: CampaignServiceClient = client.get_service("CampaignService")
            resource_name = service.campaign_path(customer_id, campaign_id)
            operation = client.resource_utils.create_update_operation(
                "Campaign",
                {"resource_name": resource_name, "status": status},
            )
            response = service.mutate_campaigns(customer_id=customer_id, operations=[operation])
            return len(response.results) > 0

        self._guard.require_write_permission("google_ads.update_campaign_status")
        return self._call("google_ads.update_campaign_status", _call)

    def add_keywords(
        self,
        customer_id: str,
        ad_group_id: str,
        keywords: list[str],
    ) -> list[str]:
        """
        Add keywords to an ad group.
        Requires: google_ads.add_keywords
        """
        def _call() -> list[str]:
            client = self._get_client()
            service = client.get_service("AdGroupCriterionService")
            operations = []
            for keyword in keywords:
                op = client.resource_utils.create_create_operation(
                    "AdGroupCriterion",
                    {
                        "ad_group": f"customers/{customer_id}/adGroups/{ad_group_id}",
                        "keyword": {"text": keyword, "match_type": "EXACT"},
                    },
                )
                operations.append(op)
            response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=operations)
            return [str(r.resource_name) for r in response.results]

        return self._call("google_ads.add_keywords", _call)
