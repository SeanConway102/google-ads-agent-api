"""
RED: Write the failing test first.
Tests for src/mcp/server.py — MCP stdio transport, tool routing, error handling.
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from src.mcp.server import (
    TOOL_HANDLERS,
    handle_list_tools,
    handle_call_tool,
    handle_list_campaigns,
)


class TestHandleListTools:

    def test_returns_all_tools(self):
        result = handle_list_tools()
        assert "tools" in result
        tool_names = [t["name"] for t in result["tools"]]
        assert "google_ads_list_campaigns" in tool_names
        assert "google_ads_update_campaign_budget" in tool_names
        assert "google_ads_add_keywords" in tool_names

    def test_read_operation_tools_have_no_warning(self):
        """Read tools should not mention Red team / Green team."""
        result = handle_list_tools()
        for tool in result["tools"]:
            if tool["name"].startswith("google_ads_get") or tool["name"].startswith("google_ads_list"):
                assert "WARNING" not in tool["description"]


class TestHandleCallTool:

    def test_unknown_tool_returns_error(self):
        result = handle_call_tool("nonexistent_tool", {})
        assert result["is_error"] is True
        assert "Unknown tool" in result["error"]

    def test_capability_denied_returns_error(self):
        """When capability guard denies an operation, return a structured error response."""
        from src.mcp.capability_guard import CapabilityDenied
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.list_campaigns.side_effect = CapabilityDenied("google_ads.list_campaigns", "test deny")
            mock_make.return_value = mock_client
            result = handle_call_tool("google_ads_list_campaigns", {"customer_id": "123-456-7890"})
            assert result.get("is_error") is True
            assert "capability denied" in result["error"].lower()

    def test_google_ads_client_error_returns_error(self):
        """GoogleAdsClientError is caught and returned as error response."""
        from src.mcp.google_ads_client import GoogleAdsClientError
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.list_campaigns.side_effect = GoogleAdsClientError("API failed")
            mock_make.return_value = mock_client
            result = handle_call_tool("google_ads_list_campaigns", {"customer_id": "123"})
            assert result.get("is_error") is True


class TestToolHandlersExist:

    def test_all_tools_have_handlers(self):
        """Every tool in TOOL_HANDLERS has a corresponding handler function."""
        from src.mcp.server import TOOLS
        tool_names = [t["name"] for t in TOOLS]
        for name in tool_names:
            assert name in TOOL_HANDLERS, f"No handler for tool: {name}"


class TestCapabilityDeniedError:

    def test_capability_denied_raises_with_operation_name(self):
        """CapabilityDenied includes the operation name for logging."""
        from src.mcp.capability_guard import CapabilityDenied
        exc = CapabilityDenied("google_ads.delete_campaign", "explicit deny")
        assert "google_ads.delete_campaign" in str(exc)
        assert exc.operation == "google_ads.delete_campaign"
