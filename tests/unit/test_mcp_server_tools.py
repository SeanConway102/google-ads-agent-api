"""
RED: Test for google_ads_list_keywords MCP tool.
MCP-001: tools/list returns only allowed tools, which includes list_keywords.
"""
import pytest
from src.mcp.server import TOOLS, TOOL_HANDLERS


def test_server_exposes_list_keywords_tool():
    """Server TOOLS list should include google_ads_list_keywords."""
    tool_names = [t["name"] for t in TOOLS]
    assert "google_ads_list_keywords" in tool_names


def test_server_has_handler_for_list_keywords():
    """TOOL_HANDLERS should have an entry for google_ads_list_keywords."""
    assert "google_ads_list_keywords" in TOOL_HANDLERS


class TestGetAdCopyTool:
    """
    google_ads.get_ad_copy must be exposed as an MCP tool.

    The capability matrix marks "Read ad copy and assets" as allowed (✅ Yes).
    The tool must appear in TOOLS and have a handler in TOOL_HANDLERS.
    """

    def test_get_ad_copy_in_tools_list(self):
        """TOOLS must include google_ads_get_ad_copy."""
        tool_names = [t["name"] for t in TOOLS]
        assert "google_ads_get_ad_copy" in tool_names, (
            f"google_ads_get_ad_copy not in TOOLS. Found: {tool_names}. "
            "The capability matrix allows 'Read ad copy and assets' — "
            "this tool must be implemented."
        )

    def test_get_ad_copy_handler_exists(self):
        """TOOL_HANDLERS must have a handler for google_ads_get_ad_copy."""
        assert "google_ads_get_ad_copy" in TOOL_HANDLERS, (
            "google_ads_get_ad_copy handler not found in TOOL_HANDLERS"
        )
