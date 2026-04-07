"""
Google Ads API client — typed wrapper around google-ads-py.

Provides a clean, typed interface for the operations permitted by CapabilityGuard.
All methods verify capabilities before making API calls.

Note: google-ads library imports are lazy (inside methods) so this module can be
imported and tested without the library installed.
"""
from dataclasses import dataclass
from datetime import date
from typing import Any

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


@dataclass
class AdCopy:
    """An ad copy (expanded text ad) — normalized response type."""
    id: str
    ad_group_id: str
    campaign_id: str
    headline_part1: str
    headline_part2: str
    headline_part3: str
    description1: str
    description2: str
    status: str


class GoogleAdsClientError(Exception):
    """Base exception for Google Ads client errors."""
    pass


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
        self._guard = guard or CapabilityGuard()
        self._customer_id = customer_id or ""
        self._client: Any = None  # Lazy-initialized google-ads client instance

    def _get_client(self) -> Any:
        """Lazily initialize the google-ads client."""
        if self._client is None:
            # Lazy import — only fails at runtime if google-ads is not installed
            from google.ads.googleads.client import GoogleAdsClient
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
            from google.ads.googleads.v17.services.services.campaign_service import CampaignServiceClient
            from google.ads.googleads.v17.services.types.campaign_service import ListCampaignsRequest
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
                    budget_amount_micros=(
                        campaign.manual_cpc.enhanced_cpc.cpc_bid_micros
                        if campaign.manual_cpc else 0
                    ),
                    start_date=campaign.start_date or None,
                    end_date=campaign.end_date or None,
                ))
            return campaigns

        return self._call("google_ads.list_campaigns", _call)

    def list_keywords(self, customer_id: str, campaign_id: str) -> list[Keyword]:
        """
        List all keywords in a campaign.
        Requires: google_ads.list_keywords
        """
        def _call() -> list[Keyword]:
            from google.ads.googleads.v17.services.types.google_ads_service import SearchGoogleAdsRequest
            client = self._get_client()
            service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT
                    campaign.id,
                    ad_group.id,
                    ad_group_criterion.keyword.text,
                    ad_group_criterion.keyword.match_type,
                    ad_group_criterion.status
                FROM ad_group_criterion
                WHERE campaign.id = '{campaign_id}'
                  AND ad_group_criterion.type = 'KEYWORD'
            """
            request = SearchGoogleAdsRequest(customer_id=customer_id, query=query)
            response = service.search(request=request)
            keywords = []
            for row in response:
                kw = row.ad_group_criterion.keyword
                keywords.append(Keyword(
                    id=str(row.ad_group_criterion.resource_name.split("/")[-1]),
                    text=kw.text,
                    match_type=kw.match_type,
                    campaign_id=str(row.campaign.id),
                    ad_group_id=str(row.ad_group.id),
                    status=str(row.ad_group_criterion.status),
                ))
            return keywords

        return self._call("google_ads.list_keywords", _call)

    def get_campaign(self, customer_id: str, campaign_id: str) -> Campaign:
        """
        Get a single campaign by ID.
        Requires: google_ads.get_campaign
        """
        def _call() -> Campaign:
            from google.ads.googleads.v17.services.services.campaign_service import CampaignServiceClient
            from google.ads.googleads.v17.services.types.campaign_service import GetCampaignRequest
            client = self._get_client()
            service: CampaignServiceClient = client.get_service("CampaignService")
            request = GetCampaignRequest(customer_id=customer_id, campaign_id=campaign_id)
            response = service.get_campaign(request=request)
            campaign = response.campaign
            return Campaign(
                id=str(campaign.id),
                name=campaign.name,
                status=str(campaign.status),
                campaign_type=str(campaign.advertising_channel_type),
                customer_id=customer_id,
                budget_amount_micros=(
                    campaign.manual_cpc.enhanced_cpc.cpc_bid_micros
                    if campaign.manual_cpc else 0
                ),
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
        # Validate campaign_id is numeric — prevents SQL injection in GAQL query
        if not campaign_id.isdigit():
            raise GoogleAdsClientError(
                f"Invalid campaign_id {campaign_id!r}: must be numeric"
            )

        def _call() -> PerformanceReport:
            from google.ads.googleads.v17.services.types.google_ads_service import SearchGoogleAdsRequest
            client = self._get_client()
            service = client.get_service("GoogleAdsService")
            # campaign_id is validated above; start_date/end_date are date objects
            # whose isoformat() always produces safe YYYY-MM-DD format
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

    def get_keyword_performance(
        self,
        customer_id: str,
        campaign_id: str,
    ) -> list[dict]:
        """
        Get keyword-level performance metrics for a campaign.
        Requires: google_ads.get_keyword_performance
        """
        def _call() -> list[dict]:
            from google.ads.googleads.v17.services.types.google_ads_service import SearchGoogleAdsRequest
            client = self._get_client()
            service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT
                    campaign.id,
                    ad_group_criterion.keyword.text,
                    ad_group_criterion.keyword.match_type,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.ctr,
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.average_cpc
                FROM ad_group_criterion
                WHERE campaign.id = '{campaign_id}'
                  AND ad_group_criterion.type = 'KEYWORD'
                ORDER BY metrics.impressions DESC
            """
            request = SearchGoogleAdsRequest(customer_id=customer_id, query=query)
            response = service.search(request=request)
            results = []
            for row in response:
                kw = row.ad_group_criterion.keyword
                m = row.metrics
                results.append({
                    "keyword": kw.text,
                    "match_type": kw.match_type,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": m.ctr,
                    "cost_micros": m.cost_micros,
                    "conversions": m.conversions,
                    "average_cpc": m.average_cpc,
                })
            return results

        return self._call("google_ads.get_keyword_performance", _call)

    def get_ad_copy(
        self,
        customer_id: str,
        campaign_id: str,
    ) -> list[AdCopy]:
        """
        Get ad copy (expanded text ads) for a campaign.
        Requires: google_ads.get_ad_copy
        """
        if not campaign_id.isdigit():
            raise GoogleAdsClientError(
                f"Invalid campaign_id {campaign_id!r}: must be numeric"
            )

        def _call() -> list[AdCopy]:
            from google.ads.googleads.v17.services.types.google_ads_service import SearchGoogleAdsRequest
            client = self._get_client()
            service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT
                    ad_group_ad.id,
                    ad_group.id,
                    campaign.id,
                    ad_group_ad.ad.expanded_text_ad.headline_part1,
                    ad_group_ad.ad.expanded_text_ad.headline_part2,
                    ad_group_ad.ad.expanded_text_ad.headline_part3,
                    ad_group_ad.ad.expanded_text_ad.description1,
                    ad_group_ad.ad.expanded_text_ad.description2,
                    ad_group_ad.status
                FROM ad_group_ad
                WHERE campaign.id = '{campaign_id}'
                  AND ad_group_ad.status != 'REMOVED'
            """
            request = SearchGoogleAdsRequest(customer_id=customer_id, query=query)
            response = service.search(request=request)
            results = []
            for row in response:
                ad = row.ad_group_ad
                results.append(AdCopy(
                    id=str(ad.id),
                    ad_group_id=str(row.ad_group.id),
                    campaign_id=str(row.campaign.id),
                    headline_part1=ad.ad.expanded_text_ad.headline_part1 or "",
                    headline_part2=ad.ad.expanded_text_ad.headline_part2 or "",
                    headline_part3=ad.ad.expanded_text_ad.headline_part3 or "",
                    description1=ad.ad.expanded_text_ad.description1 or "",
                    description2=ad.ad.expanded_text_ad.description2 or "",
                    status=str(ad.status),
                ))
            return results

        return self._call("google_ads.get_ad_copy", _call)
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
            from google.ads.googleads.v17.services.services.campaign_service import CampaignServiceClient
            client = self._get_client()
            service: CampaignServiceClient = client.get_service("CampaignService")
            resource_name = service.campaign_path(customer_id, campaign_id)
            operation = client.get_type("CampaignOperation")
            operation.update.campaign.resource_name = resource_name
            operation.update.campaign.manual_cpc.enhanced_cpc.cpc_bid_micros = budget_amount_micros
            response = service.mutate_campaigns(customer_id=customer_id, operations=[operation])
            return len(response.results) > 0

        return self._call("google_ads.update_campaign_budget", _call)

    def update_campaign_status(
        self,
        customer_id: str,
        campaign_id: str,
        status: str,
    ) -> bool:
        """
        Update a campaign's status (pause/resume).
        Requires: google_ads.update_campaign_status
        """
        def _call() -> bool:
            from google.ads.googleads.v17.services.services.campaign_service import CampaignServiceClient
            client = self._get_client()
            service: CampaignServiceClient = client.get_service("CampaignService")
            resource_name = service.campaign_path(customer_id, campaign_id)
            operation = client.get_type("CampaignOperation")
            operation.update.campaign.resource_name = resource_name
            operation.update.campaign.status = status
            response = service.mutate_campaigns(customer_id=customer_id, operations=[operation])
            return len(response.results) > 0

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

        Args:
            customer_id: Google Ads customer ID
            ad_group_id: Target ad group ID
            keywords: List of keyword text strings to add (match_type defaults to EXACT)
        """
        def _call() -> list[str]:
            client = self._get_client()
            service = client.get_service("AdGroupCriterionService")
            operations = []
            for keyword_text in keywords:
                op = client.get_type("AdGroupCriterionOperation")
                op.create.ad_group_criterion.ad_group = (
                    f"customers/{customer_id}/adGroups/{ad_group_id}"
                )
                op.create.ad_group_criterion.keyword.text = keyword_text
                op.create.ad_group_criterion.keyword.match_type = "EXACT"
                operations.append(op)
            response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=operations)
            return [str(r.resource_name) for r in response.results]

        return self._call("google_ads.add_keywords", _call)

    def remove_keywords(
        self,
        customer_id: str,
        keyword_resource_names: list[str],
    ) -> list[str]:
        """
        Remove keywords from an ad group by their resource names.
        Requires: google_ads.remove_keywords
        """
        if not keyword_resource_names:
            return []

        def _call() -> list[str]:
            client = self._get_client()
            service = client.get_service("AdGroupCriterionService")
            operations = []
            for resource_name in keyword_resource_names:
                op = client.get_type("AdGroupCriterionOperation")
                op.remove = resource_name
                operations.append(op)
            response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=operations)
            return [str(r.resource_name) for r in response.results]

        return self._call("google_ads.remove_keywords", _call)

    def update_keyword_bids(
        self,
        customer_id: str,
        updates: list[dict],
    ) -> list[str]:
        """
        Update CPC bids for existing keywords.
        Requires: google_ads.update_keyword_bids
        """
        if not updates:
            return []

        def _call() -> list[str]:
            client = self._get_client()
            service = client.get_service("AdGroupCriterionService")
            operations = []
            for update in updates:
                op = client.get_type("AdGroupCriterionOperation")
                op.update.ad_group_criterion.resource_name = update["resource_name"]
                op.update.ad_group_criterion.cpc_bid_micros = update["cpc_bid_micros"]
                operations.append(op)
            response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=operations)
            return [str(r.resource_name) for r in response.results]

        return self._call("google_ads.update_keyword_bids", _call)

    def update_keyword_match_types(
        self,
        customer_id: str,
        updates: list[dict],
    ) -> list[str]:
        """
        Update match types for existing keywords.
        Requires: google_ads.update_keyword_match_types
        """
        if not updates:
            return []

        def _call() -> list[str]:
            client = self._get_client()
            service = client.get_service("AdGroupCriterionService")
            operations = []
            for update in updates:
                op = client.get_type("AdGroupCriterionOperation")
                op.update.ad_group_criterion.resource_name = update["resource_name"]
                op.update.ad_group_criterion.keyword.match_type = update["match_type"]
                operations.append(op)
            response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=operations)
            return [str(r.resource_name) for r in response.results]

        return self._call("google_ads.update_keyword_match_types", _call)
