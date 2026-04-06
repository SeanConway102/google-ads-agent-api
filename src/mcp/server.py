"""
MCP server entrypoint — exposes Google Ads capabilities as Model Context Protocol tools.

This server implements the Anthropic MCP spec, allowing the MiniMax LLM
to call Google Ads operations through a typed tool interface.

Usage:
    python -m src.mcp.server

The server communicates over stdio (MCP transport) when run as a subprocess
by the LLM's MCP client.
"""
import logging
import sys
from typing import Any

from src.mcp.capability_guard import CapabilityDenied, CapabilityGuard
from src.mcp.google_ads_client import (
    GoogleAdsClient,
    GoogleAdsClientError,
)
from src.mcp.auth import get_credentials

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ─── Tool definitions ─────────────────────────────────────────────────────────

# Each tool is a dict compatible with the MCP tool schema.
# The LLM uses these definitions to know what tools are available.

TOOLS: list[dict[str, Any]] = [
    {
        "name": "google_ads_list_campaigns",
        "description": "List all Google Ads campaigns for a customer account. Returns campaign id, name, status, type, and budget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads customer ID (e.g. '123-456-7890' or '1234567890')",
                },
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "google_ads_get_campaign",
        "description": "Get details for a single Google Ads campaign by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads customer ID",
                },
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID (numeric string)",
                },
            },
            "required": ["customer_id", "campaign_id"],
        },
    },
    {
        "name": "google_ads_get_performance_report",
        "description": "Get performance metrics (impressions, clicks, spend, conversions, CTR, CPC) for a campaign over a date range.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads customer ID",
                },
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID (numeric string)",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["customer_id", "campaign_id", "start_date", "end_date"],
        },
    },
    {
        "name": "google_ads_update_campaign_budget",
        "description": "Update a campaign's daily budget (in micros). WARNING: Requires explicit capability allowance. Only use after Green team proposes and Red team raises no objection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads customer ID",
                },
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID (numeric string)",
                },
                "budget_amount_micros": {
                    "type": "integer",
                    "description": "New daily budget in micros (1 dollar = 1,000,000 micros)",
                },
            },
            "required": ["customer_id", "campaign_id", "budget_amount_micros"],
        },
    },
    {
        "name": "google_ads_update_campaign_status",
        "description": "Pause or resume a campaign. WARNING: Requires explicit capability allowance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads customer ID",
                },
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID (numeric string)",
                },
                "status": {
                    "type": "string",
                    "enum": ["ENABLED", "PAUSED"],
                    "description": "New campaign status",
                },
            },
            "required": ["customer_id", "campaign_id", "status"],
        },
    },
    {
        "name": "google_ads_add_keywords",
        "description": "Add keywords to an ad group. WARNING: Requires explicit capability allowance. Only use after Green team proposes and Red team raises no objection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads customer ID",
                },
                "ad_group_id": {
                    "type": "string",
                    "description": "Ad group ID (numeric string)",
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keyword texts to add (match type: EXACT)",
                },
            },
            "required": ["customer_id", "ad_group_id", "keywords"],
        },
    },
]


# ─── Tool handlers ─────────────────────────────────────────────────────────────

def _make_client() -> GoogleAdsClient:
    """Create a Google Ads client with default capability guard."""
    guard = CapabilityGuard()
    return GoogleAdsClient(guard=guard)


def handle_list_campaigns(args: dict) -> dict[str, Any]:
    customer_id: str = args["customer_id"]
    client = _make_client()
    campaigns = client.list_campaigns(customer_id)
    return {
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "campaign_type": c.campaign_type,
                "budget_micros": c.budget_amount_micros,
            }
            for c in campaigns
        ],
        "total": len(campaigns),
    }


def handle_get_campaign(args: dict) -> dict[str, Any]:
    customer_id: str = args["customer_id"]
    campaign_id: str = args["campaign_id"]
    client = _make_client()
    campaign = client.get_campaign(customer_id, campaign_id)
    return {
        "id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "campaign_type": campaign.campaign_type,
        "budget_micros": campaign.budget_amount_micros,
        "start_date": campaign.start_date,
        "end_date": campaign.end_date,
    }


def handle_get_performance_report(args: dict) -> dict[str, Any]:
    from datetime import date
    customer_id: str = args["customer_id"]
    campaign_id: str = args["campaign_id"]
    start_date = date.fromisoformat(args["start_date"])
    end_date = date.fromisoformat(args["end_date"])
    client = _make_client()
    report = client.get_performance_report(customer_id, campaign_id, start_date, end_date)
    return {
        "campaign_id": report.campaign_id,
        "date_range": report.date_range,
        "impressions": report.impressions,
        "clicks": report.clicks,
        "spend_micros": report.spend_micros,
        "conversions": report.conversions,
        "ctr": report.ctr,
        "avg_cpc_micros": report.avg_cpc_micros,
    }


def handle_update_campaign_budget(args: dict) -> dict[str, Any]:
    customer_id: str = args["customer_id"]
    campaign_id: str = args["campaign_id"]
    budget_amount_micros: int = args["budget_amount_micros"]
    client = _make_client()
    success = client.update_campaign_budget(customer_id, campaign_id, budget_amount_micros)
    return {"success": success, "campaign_id": campaign_id, "budget_micros": budget_amount_micros}


def handle_update_campaign_status(args: dict) -> dict[str, Any]:
    customer_id: str = args["customer_id"]
    campaign_id: str = args["campaign_id"]
    status: str = args["status"]
    client = _make_client()
    success = client.update_campaign_status(customer_id, campaign_id, status)
    return {"success": success, "campaign_id": campaign_id, "status": status}


def handle_add_keywords(args: dict) -> dict[str, Any]:
    customer_id: str = args["customer_id"]
    ad_group_id: str = args["ad_group_id"]
    keywords: list[str] = args["keywords"]
    client = _make_client()
    resource_names = client.add_keywords(customer_id, ad_group_id, keywords)
    return {"ad_group_id": ad_group_id, "keywords_added": len(resource_names), "resource_names": resource_names}


TOOL_HANDLERS: dict[str, callable] = {
    "google_ads_list_campaigns": handle_list_campaigns,
    "google_ads_get_campaign": handle_get_campaign,
    "google_ads_get_performance_report": handle_get_performance_report,
    "google_ads_update_campaign_budget": handle_update_campaign_budget,
    "google_ads_update_campaign_status": handle_update_campaign_status,
    "google_ads_add_keywords": handle_add_keywords,
}


# ─── MCP protocol handlers ────────────────────────────────────────────────────

def handle_list_tools() -> dict[str, Any]:
    """Handle the MCP list_tools request."""
    return {"tools": TOOLS}


def handle_call_tool(name: str, arguments: dict) -> dict[str, Any]:
    """
    Handle the MCP call_tool request.
    Routes to the appropriate handler and returns a structured response.
    """
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {
            "error": f"Unknown tool: {name}",
            "is_error": True,
        }

    try:
        result = handler(arguments)
        return {"result": result}
    except CapabilityDenied as exc:
        logger.warning("tool_capability_denied", extra={"tool": name, "operation": exc.operation})
        return {
            "error": f"Capability denied: {exc.operation}",
            "is_error": True,
        }
    except GoogleAdsClientError as exc:
        logger.error("tool_google_ads_error", extra={"tool": name, "error": str(exc)})
        return {
            "error": f"Google Ads API error: {exc}",
            "is_error": True,
        }
    except Exception as exc:
        logger.exception("tool_unexpected_error", extra={"tool": name})
        return {
            "error": f"Unexpected error: {exc}",
            "is_error": True,
        }


# ─── Stdio transport ──────────────────────────────────────────────────────────

def main() -> None:
    """
    MCP server main loop — reads JSON-RPC requests from stdin, writes to stdout.
    Uses the MCP stdio transport specification.
    """
    import json
    import sys

    logger.info("mcp_server_starting", extra={"tools": len(TOOLS)})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = request.get("method", "")
        request_id = request.get("id")

        if method == "tools/list":
            response = handle_list_tools()
            _write_response(request_id, response)
        elif method == "tools/call":
            tool_name = request.get("params", {}).get("name", "")
            arguments = request.get("params", {}).get("arguments", {})
            result = handle_call_tool(tool_name, arguments)
            _write_response(request_id, result)
        elif method == "initialize":
            _write_response(request_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "google-ads-mcp", "version": "0.1.0"},
            })
        elif method == "notifications/initialized":
            pass  # Acknowledged — no response needed
        else:
            if request_id is not None:
                _write_response(request_id, {"error": f"Unknown method: {method}"})


def _write_response(request_id: Any, result: dict) -> None:
    """Write a JSON-RPC response to stdout."""
    import json
    response = {"jsonrpc": "2.0", "id": request_id, **result}
    print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
