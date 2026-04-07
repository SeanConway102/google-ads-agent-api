"""
Research source definitions and fetchers.
Uses Jina MCP for web search and content extraction.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.config import get_settings


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def jina_parallel_search_web(queries: list[str], num_results: int = 5) -> list[dict]:
    """
    Search the web using Jina search API.
    Returns list of result dicts with title, url, description.
    """
    settings = get_settings()
    jina_api_key = getattr(settings, "JINA_API_KEY", None) or ""

    if not jina_api_key:
        return []

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = []
            for q in queries:
                tasks.append(
                    client.get(
                        "https://s.jina.ai/s",
                        params={"q": q, "num_results": num_results},
                        headers={"Authorization": f"Bearer {jina_api_key}"},
                    )
                )
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            results = []
            for resp in responses:
                if isinstance(resp, BaseException):
                    results.extend([])
                elif resp.status_code == 200:
                    data = resp.json()
                    results.extend(data.get("results", []))
                else:
                    results.extend([])
            return results
    except Exception:
        return []


async def jina_read_url(url: str) -> str:
    """Extract text content from a URL using Jina reader."""
    settings = get_settings()
    jina_api_key = getattr(settings, "JINA_API_KEY", None) or ""

    if not jina_api_key:
        return ""

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"https://r.jina.ai/{url}",
                headers={"Authorization": f"Bearer {jina_api_key}"},
            )
            if resp.status_code == 200:
                return resp.text
            return ""
    except Exception:
        return ""


async def fetch_academic_sources(queries: list[str]) -> list[Source]:
    """
    Fetch academic sources for given queries using Jina search.
    Returns list of Source objects with source_type='academic'.
    """
    if not queries:
        return []

    try:
        search_results = await jina_parallel_search_web(queries)
    except Exception:
        return []
    sources = []
    for r in search_results:
        try:
            content = await jina_read_url(r.get("url", ""))
        except Exception:
            content = r.get("description", "")
        sources.append(Source(
            name=r.get("title", ""),
            url=r.get("url"),
            content=content[:2000] if content else r.get("description", ""),
            fetched_at=_now_iso(),
            source_type="academic",
        ))
    return sources


async def fetch_industry_news(queries: list[str]) -> list[Source]:
    """
    Fetch industry news for given queries using Jina search.
    Returns list of Source objects with source_type='industry_news'.
    """
    if not queries:
        return []

    try:
        search_results = await jina_parallel_search_web(queries)
    except Exception:
        return []
    sources = []
    for r in search_results:
        try:
            content = await jina_read_url(r.get("url", ""))
        except Exception:
            content = r.get("description", "")
        sources.append(Source(
            name=r.get("title", ""),
            url=r.get("url"),
            content=content[:2000] if content else r.get("description", ""),
            fetched_at=_now_iso(),
            source_type="industry_news",
        ))
    return sources
