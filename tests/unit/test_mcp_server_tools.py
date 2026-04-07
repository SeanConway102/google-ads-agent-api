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
