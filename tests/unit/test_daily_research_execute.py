"""
RED: Tests for _execute_allowed_actions — proposal execution in daily research cycle.
These tests verify that ALL allowed proposal types are wired up to client calls.

The capability guard allows: keyword_add, keyword_remove, keyword_bid_update, keyword_match_type_update.
If any of these are missing from the execution path, consensus-reached proposals silently do nothing.
"""
import pytest
from unittest.mock import MagicMock
from src.mcp.capability_guard import CapabilityGuard


class TestExecuteAllowedActionsKeywordRemove:
    """Test that keyword_remove proposals actually call gads_client.remove_keywords()."""

    def test_keyword_remove_calls_gads_client_remove_keywords(self):
        """keyword_remove proposal should call gads_client.remove_keywords with resource names."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        mock_gads.remove_keywords = MagicMock(return_value=[
            "customers/123/adGroups/456/criteria/789"
        ])
        guard = CapabilityGuard()
        campaign = {"customer_id": "123", "ad_group_id": "456"}

        proposals = [{
            "type": "keyword_remove",
            "resource_names": [
                "customers/123/adGroups/456/criteria/789",
                "customers/123/adGroups/456/criteria/790",
            ],
        }]

        _execute_allowed_actions(proposals, campaign, mock_gads, guard)

        mock_gads.remove_keywords.assert_called_once_with(
            customer_id="123",
            keyword_resource_names=[
                "customers/123/adGroups/456/criteria/789",
                "customers/123/adGroups/456/criteria/790",
            ],
        )

    def test_keyword_remove_empty_list_returns_early(self):
        """keyword_remove with empty resource_names should return early without calling client."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        guard = CapabilityGuard()
        campaign = {"customer_id": "123"}

        _execute_allowed_actions([{"type": "keyword_remove", "resource_names": []}], campaign, mock_gads, guard)

        mock_gads.remove_keywords.assert_not_called()


class TestExecuteAllowedActionsBidUpdate:
    """Test that keyword_bid_update proposals call gads_client.update_keyword_bids()."""

    def test_bid_update_calls_gads_client_update_keyword_bids(self):
        """keyword_bid_update proposal should call gads_client.update_keyword_bids."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        mock_gads.update_keyword_bids = MagicMock(return_value=[
            "customers/123/adGroups/456/criteria/789"
        ])
        guard = CapabilityGuard()
        campaign = {"customer_id": "123"}

        proposals = [{
            "type": "keyword_bid_update",
            "updates": [
                {"resource_name": "customers/123/adGroups/456/criteria/789", "cpc_bid_micros": 150000},
                {"resource_name": "customers/123/adGroups/456/criteria/790", "cpc_bid_micros": 200000},
            ],
        }]

        _execute_allowed_actions(proposals, campaign, mock_gads, guard)

        mock_gads.update_keyword_bids.assert_called_once_with(
            customer_id="123",
            updates=[
                {"resource_name": "customers/123/adGroups/456/criteria/789", "cpc_bid_micros": 150000},
                {"resource_name": "customers/123/adGroups/456/criteria/790", "cpc_bid_micros": 200000},
            ],
        )

    def test_bid_update_empty_updates_returns_early(self):
        """keyword_bid_update with empty updates should return early without calling client."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        guard = CapabilityGuard()
        campaign = {"customer_id": "123"}

        _execute_allowed_actions([{"type": "keyword_bid_update", "updates": []}], campaign, mock_gads, guard)

        mock_gads.update_keyword_bids.assert_not_called()


class TestExecuteAllowedActionsMatchTypeUpdate:
    """Test that keyword_match_type_update proposals call gads_client.update_keyword_match_types()."""

    def test_match_type_update_calls_gads_client_update_keyword_match_types(self):
        """keyword_match_type_update proposal should call gads_client.update_keyword_match_types."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        mock_gads.update_keyword_match_types = MagicMock(return_value=[
            "customers/123/adGroups/456/criteria/789"
        ])
        guard = CapabilityGuard()
        campaign = {"customer_id": "123"}

        proposals = [{
            "type": "keyword_match_type_update",
            "updates": [
                {"resource_name": "customers/123/adGroups/456/criteria/789", "match_type": "PHRASE"},
            ],
        }]

        _execute_allowed_actions(proposals, campaign, mock_gads, guard)

        mock_gads.update_keyword_match_types.assert_called_once_with(
            customer_id="123",
            updates=[
                {"resource_name": "customers/123/adGroups/456/criteria/789", "match_type": "PHRASE"},
            ],
        )


class TestExecuteAllowedActionsCapabilityDenied:
    """Test that blocked operations are blocked by capability guard."""

    def test_blocked_proposal_raises_capability_denied(self):
        """Proposal type not in allowed operations should raise CapabilityDenied."""
        from src.cron.daily_research import _execute_allowed_actions
        from src.mcp.capability_guard import CapabilityDenied

        # Create a guard with NO allowed operations (deny-by-default)
        guard = CapabilityGuard(allowed_operations=set(), denied_operations=set())
        # Override to deny everything
        guard._rules = []
        guard._allowed = set()
        guard._denied = set()

        mock_gads = MagicMock()
        campaign = {"customer_id": "123"}

        # This should be caught by the try/except and print "Blocked by capability guard"
        _execute_allowed_actions([{"type": "keyword_add"}], campaign, mock_gads, guard)

        # Client should NOT be called because the guard denies it
        mock_gads.add_keywords.assert_not_called()


class TestExecuteAllowedActionsMixedProposals:
    """Test that mixed proposal types each call the right client methods."""

    def test_mixed_proposals_all_execute_correctly(self):
        """Multiple proposal types in one batch should each call their respective client methods."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        mock_gads.add_keywords = MagicMock(return_value=["customers/123/adGroupCriteria/999"])
        mock_gads.remove_keywords = MagicMock(return_value=["customers/123/adGroups/456/criteria/789"])
        mock_gads.update_keyword_bids = MagicMock(return_value=["customers/123/adGroups/456/criteria/789"])
        mock_gads.update_keyword_match_types = MagicMock(return_value=["customers/123/adGroups/456/criteria/789"])
        guard = CapabilityGuard()
        campaign = {"customer_id": "123", "ad_group_id": "456"}

        proposals = [
            {"type": "keyword_add", "keywords": ["summer sale"], "ad_group_id": "456"},
            {"type": "keyword_remove", "resource_names": ["customers/123/adGroups/456/criteria/789"]},
            {"type": "keyword_bid_update", "updates": [{"resource_name": "r1", "cpc_bid_micros": 100000}]},
            {"type": "keyword_match_type_update", "updates": [{"resource_name": "r1", "match_type": "PHRASE"}]},
        ]

        _execute_allowed_actions(proposals, campaign, mock_gads, guard)

        mock_gads.add_keywords.assert_called_once()
        mock_gads.remove_keywords.assert_called_once()
        mock_gads.update_keyword_bids.assert_called_once()
        mock_gads.update_keyword_match_types.assert_called_once()


class TestExecuteAllowedActionsBidUpdateAlias:
    """Test that 'bid_update' (coordinator naming) also calls update_keyword_bids."""

    def test_bid_update_alias_calls_gads_client_update_keyword_bids(self):
        """bid_update (coordinator output name) should call gads_client.update_keyword_bids."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        mock_gads.update_keyword_bids = MagicMock(return_value=["customers/123/adGroups/456/criteria/789"])
        guard = CapabilityGuard()
        campaign = {"customer_id": "123"}

        proposals = [{
            "type": "bid_update",
            "updates": [
                {"resource_name": "customers/123/adGroups/456/criteria/789", "cpc_bid_micros": 150000},
            ],
        }]

        _execute_allowed_actions(proposals, campaign, mock_gads, guard)

        mock_gads.update_keyword_bids.assert_called_once_with(
            customer_id="123",
            updates=[{"resource_name": "customers/123/adGroups/456/criteria/789", "cpc_bid_micros": 150000}],
        )

    def test_bid_update_alias_empty_updates_returns_early(self):
        """bid_update with empty updates should return early without calling client."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        guard = CapabilityGuard()
        campaign = {"customer_id": "123"}

        _execute_allowed_actions([{"type": "bid_update", "updates": []}], campaign, mock_gads, guard)

        mock_gads.update_keyword_bids.assert_not_called()


class TestExecuteAllowedActionsMatchTypeUpdateAlias:
    """Test that 'match_type_update' (coordinator naming) also calls update_keyword_match_types."""

    def test_match_type_update_alias_calls_gads_client_update_keyword_match_types(self):
        """match_type_update (coordinator output name) should call gads_client.update_keyword_match_types."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        mock_gads.update_keyword_match_types = MagicMock(return_value=["customers/123/adGroups/456/criteria/789"])
        guard = CapabilityGuard()
        campaign = {"customer_id": "123"}

        proposals = [{
            "type": "match_type_update",
            "updates": [
                {"resource_name": "customers/123/adGroups/456/criteria/789", "match_type": "BROAD"},
            ],
        }]

        _execute_allowed_actions(proposals, campaign, mock_gads, guard)

        mock_gads.update_keyword_match_types.assert_called_once_with(
            customer_id="123",
            updates=[{"resource_name": "customers/123/adGroups/456/criteria/789", "match_type": "BROAD"}],
        )

    def test_match_type_update_alias_empty_updates_returns_early(self):
        """match_type_update with empty updates should return early without calling client."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        guard = CapabilityGuard()
        campaign = {"customer_id": "123"}

        _execute_allowed_actions([{"type": "match_type_update", "updates": []}], campaign, mock_gads, guard)

        mock_gads.update_keyword_match_types.assert_not_called()


class TestExecuteAllowedActionsUnknownType:
    """Unknown proposal types are silently skipped (no error raised)."""

    def test_unknown_proposal_type_does_not_raise(self):
        """An unrecognized proposal type should silently skip without raising."""
        from src.cron.daily_research import _execute_allowed_actions

        mock_gads = MagicMock()
        guard = CapabilityGuard()
        campaign = {"customer_id": "123"}

        # Should not raise — silently skipped
        _execute_allowed_actions([{"type": "campaign_budget_update"}], campaign, mock_gads, guard)

        # No client methods should be called
        assert not mock_gads.add_keywords.called
        assert not mock_gads.remove_keywords.called
        assert not mock_gads.update_keyword_bids.called



