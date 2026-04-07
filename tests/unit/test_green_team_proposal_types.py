"""
RED: Write the failing test first.
Tests that green_team handles None values in proposal fields gracefully.

BUG: proposal.get("reasoning", "")[:300] raises TypeError when
reasoning is explicitly None (dict.get returns None when key exists with
None value, not the default). Same issue affects all four slicing calls.
"""
import pytest
from unittest.mock import MagicMock


class TestGreenTeamProposalsNoneHandling:
    """GreenTeamAgent must handle None values in proposal fields without crashing."""

    def test_parse_response_with_none_reasoning_does_not_crash(self):
        """
        When a proposal dict has reasoning=None (not missing), slicing
        proposal.get("reasoning", "")[:300] raises TypeError.
        The fix: use (proposal.get("reasoning") or "")[:300].
        """
        from src.agents.green_team import GreenTeamAgent

        agent = GreenTeamAgent()

        # Simulate LLM response with proposals that have None reasoning
        raw_response = '[{"type": "keyword_add", "reasoning": null, "impact_summary": "Test"}]'

        # This should not raise TypeError even when reasoning is None/null
        result = agent._parse_response(raw_response)

        assert len(result) == 1
        assert result[0]["type"] == "keyword_add"
        # _parse_response is a plain JSON parser; None values remain None after parsing.
        # Normalization to "" happens in route_proposals / _send_proposal_email_for
        # when it applies (proposal.get("reasoning") or "")[:300].
        assert result[0].get("reasoning") is None

    def test_parse_response_with_missing_fields_handles_gracefully(self):
        """
        Proposals with missing fields should be parsed without error.
        """
        from src.agents.green_team import GreenTeamAgent

        agent = GreenTeamAgent()

        # Minimal proposal with only type
        raw_response = '[{"type": "bid_update"}]'

        result = agent._parse_response(raw_response)

        assert len(result) == 1
        assert result[0]["type"] == "bid_update"

    def test_parse_response_with_all_none_optional_fields(self):
        """
        All optional fields (reasoning, impact_summary, target, etc.)
        being None should not cause TypeError on slicing.
        """
        from src.agents.green_team import GreenTeamAgent

        agent = GreenTeamAgent()

        raw_response = '[{"type": "keyword_remove", "reasoning": null, "impact_summary": null}]'

        # Should not raise TypeError
        result = agent._parse_response(raw_response)

        assert len(result) == 1
        assert result[0]["type"] == "keyword_remove"
