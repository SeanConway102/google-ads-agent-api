"""
Tests for src/mcp/server.py — MCP stdio transport, tool routing, error handling.
"""
from unittest.mock import patch, MagicMock, AsyncMock
from io import StringIO

import pytest

from src.mcp.server import (
    TOOL_HANDLERS,
    handle_list_tools,
    handle_call_tool,
    handle_list_campaigns,
    handle_get_campaign,
    handle_get_performance_report,
    handle_list_keywords,
    handle_update_campaign_budget,
    handle_update_campaign_status,
    handle_add_keywords,
    handle_remove_keywords,
    handle_update_keyword_bids,
    handle_update_keyword_match_types,
    handle_get_keyword_performance,
    handle_get_ad_copy,
    _validate_customer_id,
    _validate_date,
    _make_client,
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

    def test_generic_exception_returns_error(self):
        """
        Unexpected exceptions (not CapabilityDenied, GoogleAdsClientError, or ValueError)
        are caught by the generic except Exception handler and returned as error.
        """
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.list_campaigns.side_effect = RuntimeError("unexpected error")
            mock_make.return_value = mock_client
            result = handle_call_tool("google_ads_list_campaigns", {"customer_id": "123-456-7890"})
            assert "error" in result
            assert isinstance(result["error"], dict)
            assert "code" in result["error"]
            assert result["error"]["code"] == -32603  # Unexpected error code

    def test_value_error_returns_validation_error(self):
        """
        ValueError raised by _validate_customer_id or _validate_date is caught
        by the ValueError handler and returned as validation error with code -32002.
        """
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            # _validate_customer_id raises ValueError on invalid format
            mock_client.list_campaigns.side_effect = ValueError("Invalid customer_id format")
            mock_make.return_value = mock_client
            result = handle_call_tool("google_ads_list_campaigns", {"customer_id": "bad-format"})
            assert "error" in result
            assert result["error"]["code"] == -32002
            assert "Validation error" in result["error"]["message"]


class TestToolHandlersExist:

    def test_all_tools_have_handlers(self):
        """Every tool in TOOL_HANDLERS has a corresponding handler function."""
        from src.mcp.server import TOOLS
        tool_names = [t["name"] for t in TOOLS]
        for name in tool_names:
            assert name in TOOL_HANDLERS, f"No handler for tool: {name}"


class TestValidateCustomerId:
    """Tests for _validate_customer_id()."""

    def test_accepts_dashed_format(self):
        """XXX-XXX-XXXX format is accepted."""
        _validate_customer_id("123-456-7890")

    def test_accepts_10digit_format(self):
        """XXXXXXXXXX format is accepted."""
        _validate_customer_id("1234567890")

    def test_rejects_invalid_format(self):
        """Invalid customer_id format raises ValueError."""
        import pytest
        with pytest.raises(ValueError, match="Invalid customer_id"):
            _validate_customer_id("123-45-7890")

    def test_rejects_empty_string(self):
        """Empty string raises ValueError."""
        import pytest
        with pytest.raises(ValueError):
            _validate_customer_id("")


class TestValidateDate:
    """Tests for _validate_date()."""

    def test_accepts_valid_iso_date(self):
        """YYYY-MM-DD format is accepted."""
        _validate_date("2026-01-15")

    def test_rejects_invalid_date(self):
        """Invalid date raises ValueError."""
        import pytest
        with pytest.raises(ValueError, match="Invalid date"):
            _validate_date("2026-13-45")

    def test_rejects_wrong_format(self):
        """MM/DD/YYYY format is rejected."""
        import pytest
        with pytest.raises(ValueError, match="Invalid date"):
            _validate_date("01/15/2026")


class TestMakeClient:
    """Tests for _make_client()."""

    def test_returns_google_ads_client_instance(self):
        """_make_client creates a GoogleAdsClient with a CapabilityGuard."""
        with patch("src.mcp.server.GoogleAdsClient") as mock_gads_class:
            client = _make_client()
            mock_gads_class.assert_called_once()
            call_kwargs = mock_gads_class.call_args.kwargs
            assert "guard" in call_kwargs


class TestHandleListCampaigns:
    """Tests for handle_list_campaigns()."""

    def test_returns_campaigns_list(self):
        """handle_list_campaigns returns a dict with campaigns and total."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_campaign = MagicMock()
            mock_campaign.id = "cmp_1"
            mock_campaign.name = "Test Campaign"
            mock_campaign.status = "ENABLED"
            mock_campaign.campaign_type = "SEARCH"
            mock_campaign.budget_amount_micros = 500000000
            mock_client.list_campaigns.return_value = [mock_campaign]
            mock_make.return_value = mock_client

            result = handle_list_campaigns({"customer_id": "123-456-7890"})

            assert "campaigns" in result
            assert result["total"] == 1
            assert result["campaigns"][0]["name"] == "Test Campaign"

    def test_validates_customer_id(self):
        """Invalid customer_id format raises ValueError."""
        import pytest
        with pytest.raises(ValueError, match="Invalid customer_id"):
            handle_list_campaigns({"customer_id": "invalid"})


class TestHandleGetCampaign:
    """Tests for handle_get_campaign()."""

    def test_returns_campaign_details(self):
        """handle_get_campaign returns campaign details dict."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_campaign = MagicMock()
            mock_campaign.id = "cmp_1"
            mock_campaign.name = "Test Campaign"
            mock_campaign.status = "ENABLED"
            mock_campaign.campaign_type = "SEARCH"
            mock_campaign.budget_amount_micros = 500000000
            mock_campaign.start_date = "2026-01-01"
            mock_campaign.end_date = "2026-12-31"
            mock_client.get_campaign.return_value = mock_campaign
            mock_make.return_value = mock_client

            result = handle_get_campaign({"customer_id": "123-456-7890", "campaign_id": "cmp_1"})

            assert result["name"] == "Test Campaign"
            assert result["start_date"] == "2026-01-01"
            assert result["end_date"] == "2026-12-31"

    def test_validates_customer_id_format(self):
        """Invalid customer_id raises ValueError."""
        import pytest
        with pytest.raises(ValueError, match="Invalid customer_id"):
            handle_get_campaign({"customer_id": "bad", "campaign_id": "123"})


class TestHandleGetPerformanceReport:
    """Tests for handle_get_performance_report()."""

    def test_returns_performance_metrics(self):
        """handle_get_performance_report returns full metrics dict."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_report = MagicMock()
            mock_report.campaign_id = "cmp_1"
            mock_report.date_range = "2026-01-01_2026-01-31"
            mock_report.impressions = 50000
            mock_report.clicks = 1250
            mock_report.spend_micros = 250000000
            mock_report.conversions = 50
            mock_report.ctr = 2.5
            mock_report.avg_cpc_micros = 200000
            mock_client.get_performance_report.return_value = mock_report
            mock_make.return_value = mock_client

            result = handle_get_performance_report({
                "customer_id": "123-456-7890",
                "campaign_id": "cmp_1",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            })

            assert result["impressions"] == 50000
            assert result["clicks"] == 1250
            assert result["ctr"] == 2.5

    def test_rejects_invalid_date_format(self):
        """Invalid date string raises ValueError."""
        import pytest
        with pytest.raises(ValueError, match="Invalid date"):
            handle_get_performance_report({
                "customer_id": "123-456-7890",
                "campaign_id": "cmp_1",
                "start_date": "not-a-date",
                "end_date": "2026-01-31",
            })


class TestHandleListKeywords:
    """Tests for handle_list_keywords()."""

    def test_returns_keywords_list(self):
        """handle_list_keywords returns keywords with correct structure."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_kw = MagicMock()
            mock_kw.id = "kw_1"
            mock_kw.text = "summer sale"
            mock_kw.match_type = "EXACT"
            mock_kw.ad_group_id = "ag_1"
            mock_kw.status = "ENABLED"
            mock_client.list_keywords.return_value = [mock_kw]
            mock_make.return_value = mock_client

            result = handle_list_keywords({"customer_id": "123-456-7890", "campaign_id": "cmp_1"})

            assert result["total"] == 1
            assert result["keywords"][0]["text"] == "summer sale"


class TestHandleUpdateCampaignBudget:
    """Tests for handle_update_campaign_budget()."""

    def test_returns_success_response(self):
        """handle_update_campaign_budget returns success dict."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.update_campaign_budget.return_value = True
            mock_make.return_value = mock_client

            result = handle_update_campaign_budget({
                "customer_id": "123-456-7890",
                "campaign_id": "cmp_1",
                "budget_amount_micros": 750000000,
            })

            assert result["success"] is True
            assert result["budget_micros"] == 750000000


class TestHandleUpdateCampaignStatus:
    """Tests for handle_update_campaign_status()."""

    def test_returns_success_with_status(self):
        """handle_update_campaign_status returns success with new status."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.update_campaign_status.return_value = True
            mock_make.return_value = mock_client

            result = handle_update_campaign_status({
                "customer_id": "123-456-7890",
                "campaign_id": "cmp_1",
                "status": "PAUSED",
            })

            assert result["success"] is True
            assert result["status"] == "PAUSED"


class TestHandleAddKeywords:
    """Tests for handle_add_keywords()."""

    def test_returns_resource_names(self):
        """handle_add_keywords returns resource names for added keywords."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.add_keywords.return_value = [
                "customers/123/adGroups/456/criteria/789"
            ]
            mock_make.return_value = mock_client

            result = handle_add_keywords({
                "customer_id": "123-456-7890",
                "ad_group_id": "ag_1",
                "keywords": ["summer sale"],
            })

            assert result["keywords_added"] == 1
            assert "resource_names" in result


class TestHandleRemoveKeywords:
    """Tests for handle_remove_keywords()."""

    def test_returns_removed_count(self):
        """handle_remove_keywords returns count of removed keywords."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.remove_keywords.return_value = [
                "customers/123/adGroups/456/criteria/789",
                "customers/123/adGroups/456/criteria/790",
            ]
            mock_make.return_value = mock_client

            result = handle_remove_keywords({
                "customer_id": "123-456-7890",
                "keyword_resource_names": [
                    "customers/123/adGroups/456/criteria/789",
                    "customers/123/adGroups/456/criteria/790",
                ],
            })

            assert result["keywords_removed"] == 2


class TestHandleUpdateKeywordBids:
    """Tests for handle_update_keyword_bids()."""

    def test_returns_updated_count(self):
        """handle_update_keyword_bids returns count of updated keywords."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.update_keyword_bids.return_value = [
                "customers/123/adGroups/456/criteria/789"
            ]
            mock_make.return_value = mock_client

            result = handle_update_keyword_bids({
                "customer_id": "123-456-7890",
                "updates": [
                    {"resource_name": "customers/123/adGroups/456/criteria/789", "cpc_bid_micros": 150000}
                ],
            })

            assert result["keywords_updated"] == 1


class TestHandleUpdateKeywordMatchTypes:
    """Tests for handle_update_keyword_match_types()."""

    def test_returns_updated_count(self):
        """handle_update_keyword_match_types returns count of updated keywords."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.update_keyword_match_types.return_value = [
                "customers/123/adGroups/456/criteria/789"
            ]
            mock_make.return_value = mock_client

            result = handle_update_keyword_match_types({
                "customer_id": "123-456-7890",
                "updates": [
                    {"resource_name": "customers/123/adGroups/456/criteria/789", "match_type": "PHRASE"}
                ],
            })

            assert result["keywords_updated"] == 1


class TestHandleGetKeywordPerformance:
    """Tests for handle_get_keyword_performance()."""

    def test_returns_performance_results(self):
        """handle_get_keyword_performance returns keyword performance list."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.get_keyword_performance.return_value = [
                {"keyword_id": "kw_1", "impressions": 10000, "clicks": 250}
            ]
            mock_make.return_value = mock_client

            result = handle_get_keyword_performance({"customer_id": "123-456-7890", "campaign_id": "cmp_1"})

            assert result["total"] == 1
            assert result["keywords"][0]["impressions"] == 10000


class TestHandleGetAdCopy:
    """Tests for handle_get_ad_copy()."""

    def test_returns_ads_list(self):
        """handle_get_ad_copy returns ad copy list."""
        with patch("src.mcp.server._make_client") as mock_make:
            mock_client = MagicMock()
            mock_ad = MagicMock()
            mock_ad.id = "ad_1"
            mock_ad.ad_group_id = "ag_1"
            mock_ad.headline_part1 = "Summer Sale"
            mock_ad.headline_part2 = "Up to 50% Off"
            mock_ad.headline_part3 = "Limited Time"
            mock_ad.description1 = "Shop now"
            mock_ad.description2 = "Free shipping"
            mock_ad.status = "ENABLED"
            mock_client.get_ad_copy.return_value = [mock_ad]
            mock_make.return_value = mock_client

            result = handle_get_ad_copy({"customer_id": "123-456-7890", "campaign_id": "cmp_1"})

            assert result["total"] == 1
            assert result["ads"][0]["headline_part1"] == "Summer Sale"


class TestCapabilityDeniedError:

    def test_capability_denied_raises_with_operation_name(self):
        """CapabilityDenied includes the operation name for logging."""
        from src.mcp.capability_guard import CapabilityDenied
        exc = CapabilityDenied("google_ads.delete_campaign", "explicit deny")
        assert "google_ads.delete_campaign" in str(exc)
        assert exc.operation == "google_ads.delete_campaign"


class TestMainLoop:
    """Tests for main() and _write_response() — stdio transport."""

    def test_main_reads_stdin_and_responds_to_tools_list(self):
        """main() reads JSON from stdin and responds to tools/list."""
        from src.mcp.server import main, _write_response
        import sys
        from io import StringIO

        # Simulate stdin with a tools/list request
        request = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
        stdin_mock = StringIO(request + "\n")
        stdout_capture = StringIO()

        with patch.object(sys, "stdin", stdin_mock), \
             patch.object(sys, "stdout", stdout_capture), \
             patch("sys.stderr"):
            main()

        output = stdout_capture.getvalue().strip()
        assert output
        # Response is JSON-RPC 2.0: tools are at top level (spread by _write_response)
        import json
        resp = json.loads(output)
        assert resp["id"] == 1
        assert resp["jsonrpc"] == "2.0"
        assert "tools" in resp  # handle_list_tools returns {"tools": [...]}, spread to top level

    def test_main_handles_initialize_request(self):
        """main() responds to initialize method with protocol info."""
        from src.mcp.server import main
        import sys
        from io import StringIO

        request = '{"jsonrpc":"2.0","id":2,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}'
        stdin_mock = StringIO(request + "\n")
        stdout_capture = StringIO()

        with patch.object(sys, "stdin", stdin_mock), \
             patch.object(sys, "stdout", stdout_capture), \
             patch("sys.stderr"):
            main()

        output = stdout_capture.getvalue().strip()
        import json
        resp = json.loads(output)
        assert resp["id"] == 2
        assert resp["protocolVersion"] == "2024-11-05"  # initialize response fields at top level

    def test_main_handles_tools_call_request(self):
        """main() routes tools/call to handle_call_tool."""
        from src.mcp.server import main
        import sys
        from io import StringIO

        with patch("src.mcp.server.handle_call_tool") as mock_handle:
            mock_handle.return_value = {"result": {"campaigns": [], "total": 0}}
            request = '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"google_ads_list_campaigns","arguments":{"customer_id":"123-456-7890"}}}'
            stdin_mock = StringIO(request + "\n")
            stdout_capture = StringIO()

            with patch.object(sys, "stdin", stdin_mock), \
                 patch.object(sys, "stdout", stdout_capture), \
                 patch("sys.stderr"):
                main()

            output = stdout_capture.getvalue().strip()
            import json
            resp = json.loads(output)
            assert resp["id"] == 3
            mock_handle.assert_called_once()

    def test_main_skips_empty_lines(self):
        """main() skips blank lines without processing."""
        from src.mcp.server import main
        import sys
        from io import StringIO

        with patch("src.mcp.server.handle_call_tool") as mock_handle:
            request = '\n\n{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"google_ads_list_campaigns","arguments":{"customer_id":"123-456-7890"}}}\n\n'
            stdin_mock = StringIO(request)
            stdout_capture = StringIO()

            with patch.object(sys, "stdin", stdin_mock), \
                 patch.object(sys, "stdout", stdout_capture), \
                 patch("sys.stderr"):
                main()

            import json
            output = stdout_capture.getvalue().strip()
            resp = json.loads(output)
            assert resp["id"] == 4

    def test_main_ignores_invalid_json(self):
        """main() skips lines that aren't valid JSON."""
        from src.mcp.server import main
        import sys
        from io import StringIO

        with patch("src.mcp.server.handle_call_tool") as mock_handle:
            mock_handle.return_value = {"result": {}}
            # First line is invalid JSON, second is valid tools/list
            request = 'not json\n{"jsonrpc":"2.0","id":5,"method":"tools/list"}\n'
            stdin_mock = StringIO(request)
            stdout_capture = StringIO()

            with patch.object(sys, "stdin", stdin_mock), \
                 patch.object(sys, "stdout", stdout_capture), \
                 patch("sys.stderr"):
                main()

            import json
            output = stdout_capture.getvalue().strip()
            resp = json.loads(output)
            assert resp["id"] == 5

    def test_main_handles_notifications_initialized(self):
        """main() handles notifications/initialized (no response needed)."""
        from src.mcp.server import main
        import sys
        from io import StringIO

        request = '{"jsonrpc":"2.0","method":"notifications/initialized"}'
        stdin_mock = StringIO(request + "\n")
        stdout_capture = StringIO()

        with patch.object(sys, "stdin", stdin_mock), \
             patch.object(sys, "stdout", stdout_capture), \
             patch("sys.stderr"):
            main()

        # No output expected for notifications
        output = stdout_capture.getvalue()
        assert output == ""

    def test_main_responds_with_error_for_unknown_method(self):
        """main() writes an error response for unrecognized methods."""
        from src.mcp.server import main
        import sys
        from io import StringIO

        request = '{"jsonrpc":"2.0","id":6,"method":"unknown/method"}'
        stdin_mock = StringIO(request + "\n")
        stdout_capture = StringIO()

        with patch.object(sys, "stdin", stdin_mock), \
             patch.object(sys, "stdout", stdout_capture), \
             patch("sys.stderr"):
            main()

        import json
        output = stdout_capture.getvalue().strip()
        resp = json.loads(output)
        assert resp["id"] == 6
        assert "error" in resp

    def test_write_response_includes_jsonrpc_id(self):
        """_write_response writes a valid JSON-RPC 2.0 response with id."""
        from src.mcp.server import _write_response
        import sys
        from io import StringIO

        stdout_capture = StringIO()
        with patch.object(sys, "stdout", stdout_capture):
            _write_response(42, {"result": {"value": 123}})

        import json
        output = stdout_capture.getvalue().strip()
        resp = json.loads(output)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 42
        assert resp["result"]["value"] == 123