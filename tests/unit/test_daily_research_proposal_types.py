"""
RED: Write the failing test first.
Tests that daily research _execute_allowed_actions correctly handles all green team
proposal types with the names the coordinator actually outputs.

BUG: Green team LLM outputs bid_update and match_type_update.
But _execute_allowed_actions checks keyword_bid_update and keyword_match_type_update.
The name mismatch causes these proposals to be silently skipped after consensus.
"""
import pytest
from unittest.mock import MagicMock
from src.mcp.capability_guard import CapabilityGuard


class TestExecuteAllowedActionsCoordinatorOutputTypes:
    """
    Coordinator green_proposals contain types from green team LLM output:
      keyword_add, keyword_remove, bid_update, match_type_update

    The action names in green_proposals MUST match what _execute_allowed_actions checks.
    """

    def test_bid_update_is_executed_not_silently_skipped(self):
        """
        bid_update proposals (from coordinator) must call update_keyword_bids.
        If the type check is keyword_bid_update instead, this silently skips.
        """
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        mock_gads.update_keyword_bids = MagicMock(return_value=["kw1"])
        guard = CapabilityGuard()
        campaign = {"customer_id": "cust_001"}

        # Coordinator outputs bid_update (matching green team LLM output)
        proposals = [{
            "type": "bid_update",
            "updates": [{"resource_name": "kw1", "cpc_bid_micros": 150000}],
        }]

        _execute_allowed_actions(proposals, campaign, mock_gads, guard)

        # If this fails, bid_update was silently skipped
        mock_gads.update_keyword_bids.assert_called_once()

    def test_match_type_update_is_executed_not_silently_skipped(self):
        """
        match_type_update proposals (from coordinator) must call update_keyword_match_types.
        If the type check is keyword_match_type_update instead, this silently skips.
        """
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        mock_gads.update_keyword_match_types = MagicMock(return_value=["kw1"])
        guard = CapabilityGuard()
        campaign = {"customer_id": "cust_001"}

        # Coordinator outputs match_type_update (matching green team LLM output)
        proposals = [{
            "type": "match_type_update",
            "updates": [{"resource_name": "kw1", "match_type": "PHRASE"}],
        }]

        _execute_allowed_actions(proposals, campaign, mock_gads, guard)

        # If this fails, match_type_update was silently skipped
        mock_gads.update_keyword_match_types.assert_called_once()

    def test_keyword_add_still_works(self):
        """keyword_add is the same in both naming conventions."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        mock_gads.add_keywords = MagicMock(return_value=["kw1"])
        guard = CapabilityGuard()
        campaign = {"customer_id": "cust_001", "ad_group_id": "ag_001"}

        proposals = [{
            "type": "keyword_add",
            "keywords": ["new keyword"],
            "ad_group_id": "ag_001",
        }]

        _execute_allowed_actions(proposals, campaign, mock_gads, guard)

        mock_gads.add_keywords.assert_called_once()
