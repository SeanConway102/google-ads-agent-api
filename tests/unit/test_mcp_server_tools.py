"""
RED: Test that MCP server exposes all keyword tool definitions.
MCP-001: tools/list returns only allowed tools.
MCP-004: remove_keywords tool
MCP-005: update_keyword_bids tool
MCP-006: update_keyword_match_types tool
MCP-007: get_keyword_performance tool
"""
import pytest
from src.mcp.server import TOOLS, TOOL_HANDLERS


def test_server_exposes_remove_keywords_tool():
    """Server TOOLS list should include google_ads_remove_keywords."""
    tool_names = [t["name"] for t in TOOLS]
    assert "google_ads_remove_keywords" in tool_names


def test_server_exposes_update_keyword_bids_tool():
    """Server TOOLS list should include google_ads_update_keyword_bids."""
    tool_names = [t["name"] for t in TOOLS]
    assert "google_ads_update_keyword_bids" in tool_names


def test_server_exposes_update_keyword_match_types_tool():
    """Server TOOLS list should include google_ads_update_keyword_match_types."""
    tool_names = [t["name"] for t in TOOLS]
    assert "google_ads_update_keyword_match_types" in tool_names


def test_server_exposes_get_keyword_performance_tool():
    """Server TOOLS list should include google_ads_get_keyword_performance."""
    tool_names = [t["name"] for t in TOOLS]
    assert "google_ads_get_keyword_performance" in tool_names


def test_server_has_handlers_for_all_keyword_tools():
    """TOOL_HANDLERS should have entries for all keyword tools."""
    required_handlers = [
        "google_ads_remove_keywords",
        "google_ads_update_keyword_bids",
        "google_ads_update_keyword_match_types",
        "google_ads_get_keyword_performance",
    ]
    for name in required_handlers:
        assert name in TOOL_HANDLERS, f"Missing handler for {name}"
