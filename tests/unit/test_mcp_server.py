"""
Tests for src/mcp/server.py — MCP stdio transport, tool routing, error handling.
"""
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
        assert "error" in result
        assert isinstance(result["error"], dict)
        assert "code" in result["error"]
        assert "message" in result["error"]
        assert "Unknown tool" in result["error"]["message"]

    def test_capability_denied_returns_error(self):
        """When capability guard denies an operation, return a structured error response."""
        from src.mcp.capability_guard import CapabilityDenied
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.list_campaigns.side_effect = CapabilityDenied("google_ads.list_campaigns", "test deny")
            mock_make.return_value = mock_client
            result = handle_call_tool("google_ads_list_campaigns", {"customer_id": "123-456-7890"})
            assert "error" in result
            assert isinstance(result["error"], dict)
            assert "code" in result["error"]
            assert "message" in result["error"]
            assert "capability denied" in result["error"]["message"].lower()

    def test_google_ads_client_error_returns_error(self):
        """GoogleAdsClientError is caught and returned as error response."""
        from src.mcp.google_ads_client import GoogleAdsClientError
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.list_campaigns.side_effect = GoogleAdsClientError("API failed")
            mock_make.return_value = mock_client
            result = handle_call_tool("google_ads_list_campaigns", {"customer_id": "123"})
            assert "error" in result
            assert isinstance(result["error"], dict)

    def test_unknown_tool_error_is_valid_jsonrpc_error(self):
        """
        handle_call_tool error for unknown tool must be a valid JSON-RPC error object.

        JSON-RPC 2.0 spec requires error responses to have:
          - code: integer (required)
          - message: string (required)

        main() does: response = {"jsonrpc": "2.0", "id": request_id, **result}
        So handle_call_tool must return {"error": {"code": int, "message": str}}.
        """
        result = handle_call_tool("nonexistent_tool", {})

        # Must have error field as an object (not string)
        assert result.get("error") is not None, "missing 'error' field"
        assert isinstance(result["error"], dict), (
            f"error must be dict, got {type(result['error']).__name__}: {result['error']!r}"
        )
        # Must have code (integer) and message (string) per JSON-RPC spec
        error_obj = result["error"]
        assert "code" in error_obj, f"error object missing 'code' field: {error_obj!r}"
        assert "message" in error_obj, f"error object missing 'message' field: {error_obj!r}"
        assert isinstance(error_obj["code"], int), f"code must be int, got {type(error_obj['code']).__name__}"
        assert isinstance(error_obj["message"], str), f"message must be str, got {type(error_obj['message']).__name__}"


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