"""
Test MCP server handler functions.

handle_list_campaigns, handle_get_campaign, handle_list_keywords
are high-value handler functions not tested in integration.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.mcp.google_ads_client import Campaign, Keyword
from src.mcp.capability_guard import CapabilityDenied


class TestHandleListCampaigns:
    """handle_list_campaigns returns structured campaign list."""

    def test_returns_campaigns_with_correct_structure(self):
        """handle_list_campaigns returns dict with campaigns list and total."""
        from src.mcp.server import handle_list_campaigns

        mock_campaign = MagicMock(spec=Campaign)
        mock_campaign.id = "111"
        mock_campaign.name = "Summer Sale"
        mock_campaign.status = "ENABLED"
        mock_campaign.campaign_type = "SEARCH"
        mock_campaign.budget_amount_micros = 5000000

        mock_client = MagicMock()
        mock_client.list_campaigns.return_value = [mock_campaign]

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_list_campaigns({"customer_id": "123-456-7890"})

        assert "campaigns" in result
        assert "total" in result
        assert result["total"] == 1
        assert result["campaigns"][0]["id"] == "111"
        assert result["campaigns"][0]["name"] == "Summer Sale"
        assert result["campaigns"][0]["status"] == "ENABLED"
        assert result["campaigns"][0]["campaign_type"] == "SEARCH"
        assert result["campaigns"][0]["budget_micros"] == 5000000

    def test_returns_empty_when_no_campaigns(self):
        """handle_list_campaigns returns empty campaigns list when none exist."""
        from src.mcp.server import handle_list_campaigns

        mock_client = MagicMock()
        mock_client.list_campaigns.return_value = []

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_list_campaigns({"customer_id": "123-456-7890"})

        assert result["campaigns"] == []
        assert result["total"] == 0

    def test_raises_value_error_for_invalid_customer_id(self):
        """handle_list_campaigns raises ValueError for malformed customer_id."""
        from src.mcp.server import handle_list_campaigns

        with pytest.raises(ValueError, match="Invalid customer_id"):
            handle_list_campaigns({"customer_id": "not-valid"})

    def test_capability_denied_returns_error_dict(self):
        """handle_call_tool wraps CapabilityDenied as -32000 error."""
        from src.mcp.server import handle_call_tool

        mock_client = MagicMock()
        mock_client.list_campaigns.side_effect = CapabilityDenied("google_ads.list_campaigns")

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_call_tool("google_ads_list_campaigns", {"customer_id": "123-456-7890"})

        assert "error" in result
        assert result["error"]["code"] == -32000
        assert "Capability denied" in result["error"]["message"]

    def test_google_ads_client_error_returns_error_dict(self):
        """handle_call_tool wraps GoogleAdsClientError as -32001 error."""
        from src.mcp.server import handle_call_tool
        from src.mcp.google_ads_client import GoogleAdsClientError

        mock_client = MagicMock()
        mock_client.list_campaigns.side_effect = GoogleAdsClientError("list_campaigns failed: connection timeout")

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_call_tool("google_ads_list_campaigns", {"customer_id": "123-456-7890"})

        assert "error" in result
        assert result["error"]["code"] == -32001
        assert "Google Ads API error" in result["error"]["message"]


class TestHandleGetCampaign:
    """handle_get_campaign returns a single campaign dict."""

    def test_returns_campaign_dict(self):
        """handle_get_campaign returns campaign fields as dict."""
        from src.mcp.server import handle_get_campaign

        mock_campaign = MagicMock(spec=Campaign)
        mock_campaign.id = "111"
        mock_campaign.name = "Summer Sale"
        mock_campaign.status = "ENABLED"
        mock_campaign.campaign_type = "SEARCH"
        mock_campaign.budget_amount_micros = 5000000
        mock_campaign.start_date = "2024-01-01"
        mock_campaign.end_date = "2024-12-31"

        mock_client = MagicMock()
        mock_client.get_campaign.return_value = mock_campaign

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_get_campaign({"customer_id": "123-456-7890", "campaign_id": "111"})

        assert result["id"] == "111"
        assert result["name"] == "Summer Sale"
        assert result["status"] == "ENABLED"
        assert result["campaign_type"] == "SEARCH"
        assert result["budget_micros"] == 5000000
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-12-31"

    def test_raises_value_error_for_invalid_customer_id(self):
        """handle_get_campaign raises ValueError for malformed customer_id."""
        from src.mcp.server import handle_get_campaign

        with pytest.raises(ValueError, match="Invalid customer_id"):
            handle_get_campaign({"customer_id": "bad", "campaign_id": "111"})

    def test_not_found_returns_error_dict(self):
        """handle_call_tool returns error dict when get_campaign raises not-found."""
        from src.mcp.server import handle_call_tool
        from src.mcp.google_ads_client import GoogleAdsClientError

        mock_client = MagicMock()
        mock_client.get_campaign.side_effect = GoogleAdsClientError("Campaign '999' not found")

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_call_tool("google_ads_get_campaign", {"customer_id": "123-456-7890", "campaign_id": "999"})

        assert "error" in result
        assert result["error"]["code"] == -32001


class TestHandleListKeywords:
    """handle_list_keywords returns structured keyword list."""

    def test_returns_keywords_with_correct_structure(self):
        """handle_list_keywords returns dict with keywords list and total."""
        from src.mcp.server import handle_list_keywords

        mock_keyword = MagicMock(spec=Keyword)
        mock_keyword.id = "kw1"
        mock_keyword.text = "running shoes"
        mock_keyword.match_type = "EXACT"
        mock_keyword.ad_group_id = "ag1"
        mock_keyword.status = "ENABLED"

        mock_client = MagicMock()
        mock_client.list_keywords.return_value = [mock_keyword]

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_list_keywords({"customer_id": "123-456-7890", "campaign_id": "111"})

        assert "keywords" in result
        assert "total" in result
        assert result["total"] == 1
        assert result["keywords"][0]["text"] == "running shoes"
        assert result["keywords"][0]["match_type"] == "EXACT"
        assert result["keywords"][0]["status"] == "ENABLED"

    def test_returns_empty_when_no_keywords(self):
        """handle_list_keywords returns empty keywords list when none exist."""
        from src.mcp.server import handle_list_keywords

        mock_client = MagicMock()
        mock_client.list_keywords.return_value = []

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_list_keywords({"customer_id": "123-456-7890", "campaign_id": "111"})

        assert result["keywords"] == []
        assert result["total"] == 0

    def test_raises_value_error_for_invalid_customer_id(self):
        """handle_list_keywords raises ValueError for malformed customer_id."""
        from src.mcp.server import handle_list_keywords

        with pytest.raises(ValueError, match="Invalid customer_id"):
            handle_list_keywords({"customer_id": "bad", "campaign_id": "111"})


class TestHandleUpdateCampaignBudget:
    """handle_update_campaign_budget updates campaign budget."""

    def test_returns_success_dict(self):
        """handle_update_campaign_budget returns success: True with budget details."""
        from src.mcp.server import handle_update_campaign_budget

        mock_client = MagicMock()
        mock_client.update_campaign_budget.return_value = True

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_update_campaign_budget({
                "customer_id": "123-456-7890",
                "campaign_id": "111",
                "budget_amount_micros": 5000000,
            })

        assert result["success"] is True
        assert result["campaign_id"] == "111"
        assert result["budget_micros"] == 5000000
        mock_client.update_campaign_budget.assert_called_once_with("123-456-7890", "111", 5000000)

    def test_returns_false_when_no_results(self):
        """handle_update_campaign_budget returns success: False when mutation returns False."""
        from src.mcp.server import handle_update_campaign_budget

        mock_client = MagicMock()
        mock_client.update_campaign_budget.return_value = False

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_update_campaign_budget({
                "customer_id": "123-456-7890",
                "campaign_id": "111",
                "budget_amount_micros": 5000000,
            })

        assert result["success"] is False

    def test_raises_value_error_for_invalid_customer_id(self):
        """handle_update_campaign_budget raises ValueError for malformed customer_id."""
        from src.mcp.server import handle_update_campaign_budget

        with pytest.raises(ValueError, match="Invalid customer_id"):
            handle_update_campaign_budget({
                "customer_id": "bad",
                "campaign_id": "111",
                "budget_amount_micros": 5000000,
            })

    def test_negative_budget_passes_through(self):
        """Negative budget_amount_micros is passed through to the API (API validates)."""
        from src.mcp.server import handle_update_campaign_budget

        mock_client = MagicMock()
        mock_client.update_campaign_budget.return_value = False

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_update_campaign_budget({
                "customer_id": "123-456-7890",
                "campaign_id": "111",
                "budget_amount_micros": -100,
            })

        # Handler does not validate budget — passes through to API
        mock_client.update_campaign_budget.assert_called_once()
        assert result["success"] is False


class TestHandleAddKeywords:
    """handle_add_keywords adds keywords to an ad group."""

    def test_returns_resource_names(self):
        """handle_add_keywords returns count and resource names."""
        from src.mcp.server import handle_add_keywords

        mock_client = MagicMock()
        mock_client.add_keywords.return_value = [
            "customers/123/adGroupCriteria/456",
            "customers/123/adGroupCriteria/789",
        ]

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_add_keywords({
                "customer_id": "123-456-7890",
                "ad_group_id": "ag1",
                "keywords": ["running shoes", "marathon gear"],
            })

        assert result["ad_group_id"] == "ag1"
        assert result["keywords_added"] == 2
        assert len(result["resource_names"]) == 2

    def test_raises_value_error_for_invalid_customer_id(self):
        """handle_add_keywords raises ValueError for malformed customer_id."""
        from src.mcp.server import handle_add_keywords

        with pytest.raises(ValueError, match="Invalid customer_id"):
            handle_add_keywords({
                "customer_id": "bad",
                "ad_group_id": "ag1",
                "keywords": ["test"],
            })


class TestHandleListTools:
    """handle_list_tools returns the TOOLS list."""

    def test_returns_tools_list(self):
        """handle_list_tools returns the full tools list from TOOLS constant."""
        from src.mcp.server import handle_list_tools

        result = handle_list_tools()

        assert "tools" in result
        assert len(result["tools"]) > 0
        # Each tool should have name and description
        for tool in result["tools"]:
            assert "name" in tool
            assert "description" in tool


class TestHandleCallToolValidation:
    """handle_call_tool error handling for ValueError (validation errors)."""

    def test_validation_error_returns_minus_32002(self):
        """handle_call_tool converts ValueError to -32002 validation error."""
        from src.mcp.server import handle_call_tool

        # The handler will raise ValueError from _validate_customer_id
        mock_client = MagicMock()
        # No need to set up client — validation fails first

        with patch("src.mcp.server._make_client", return_value=mock_client):
            result = handle_call_tool("google_ads_list_campaigns", {"customer_id": "bad-format"})

        assert "error" in result
        assert result["error"]["code"] == -32002
        assert "Validation error" in result["error"]["message"]

    def test_unknown_tool_returns_error_dict(self):
        """handle_call_tool returns error for unknown tool names."""
        from src.mcp.server import handle_call_tool

        result = handle_call_tool("nonexistent_tool", {})

        assert "error" in result
        assert "Unknown tool" in result["error"]["message"]

