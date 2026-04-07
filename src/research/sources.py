"""
Research source definitions and fetchers.
Uses Jina MCP for web search and content extraction.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Source:
    """A single research source fetched from the web."""
    name: str
    url: Optional[str]
    content: str
    fetched_at: str
    source_type: str  # "academic", "industry_news", "google_ads_doc", "campaign_data"


# Initial academic search queries — seeds the wiki on first run
ACADEMIC_SEARCH_QUERIES = [
    "advertising attribution models multi-touch",
    "real-time bid optimization search advertising",
    "keyword-level ROI prediction paid search",
    "search advertising effectiveness measurement",
    "quality score impact on ad rank Google Ads",
]

INDUSTRY_NEWS_QUERIES = [
    "Google Ads keyword optimization best practices 2026",
    "PPC bid strategy machine learning",
    "search advertising CTR optimization techniques",
]

GOOGLE_ADS_DOC_TOPICS = [
    "https://developers.google.com/google-ads/api/fields/latest/overview",
    "https://ads.google.com/apis/ads/publisher/v202406",
]
