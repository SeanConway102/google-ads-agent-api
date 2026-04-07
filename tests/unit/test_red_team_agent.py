"""
RED: Failing tests for RedTeamAgent.
Tests that RedTeamAgent correctly builds context and parses objections from LLM.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from src.agents.red_team import RedTeamAgent


class TestRedTeamAgent:
    """Test RedTeamAgent.challenge() method."""

    @pytest.mark.asyncio
    async def test_challenge_returns_list_of_assessments(self):
        """challenge returns a list of assessment dicts from parsed LLM response."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='[{"proposal_id": "0", "verdict": "object", "objections": [{"objection": "CTR too low for this keyword", "evidence": "data shows 0.1% CTR", "suggested_fix": "remove keyword"}], "reasoning": "low engagement risk"}]'
                        )
                    )
                ]
            )
        )
        agent = RedTeamAgent(llm=mock_llm)
        result = await agent.challenge(
            green_proposals=[{"type": "keyword_add", "target": "luxury cars"}],
            campaign_data={"clicks": 50, "ctr": 0.001},
            wiki_context=[{"title": "CTR Benchmarks", "content": "Average CTR is 1-2%"}],
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["verdict"] == "object"
        assert "CTR" in result[0]["objections"][0]["objection"]

    @pytest.mark.asyncio
    async def test_challenge_builds_context_with_green_proposals(self):
        """Context includes the green proposals."""
        mock_llm = MagicMock()
        captured_messages = []

        async def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="[]"))]
            )

        mock_llm.chat_completion = AsyncMock(side_effect=capture_chat)
        agent = RedTeamAgent(llm=mock_llm)
        proposals = [{"type": "keyword_add", "target": "running shoes", "priority": "high"}]
        await agent.challenge(
            green_proposals=proposals,
            campaign_data={},
            wiki_context=[],
        )
        context = captured_messages[1].content
        assert "running shoes" in context
        assert "keyword_add" in context

    @pytest.mark.asyncio
    async def test_challenge_builds_context_with_campaign_data(self):
        """Context includes campaign performance data."""
        mock_llm = MagicMock()
        captured_messages = []

        async def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="[]"))]
            )

        mock_llm.chat_completion = AsyncMock(side_effect=capture_chat)
        agent = RedTeamAgent(llm=mock_llm)
        await agent.challenge(
            green_proposals=[],
            campaign_data={"clicks": 10, "ctr": 0.001, "spend": 500.00, "conversions": 0},
            wiki_context=[],
        )
        context = captured_messages[1].content
        assert "clicks" in context
        assert "10" in context
        assert "conversions" in context

    @pytest.mark.asyncio
    async def test_challenge_builds_context_with_wiki_context(self):
        """Context includes wiki research entries."""
        mock_llm = MagicMock()
        captured_messages = []

        async def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="[]"))]
            )

        mock_llm.chat_completion = AsyncMock(side_effect=capture_chat)
        agent = RedTeamAgent(llm=mock_llm)
        await agent.challenge(
            green_proposals=[],
            campaign_data={},
            wiki_context=[{"title": "Negative Keywords", "content": "Use negatives to filter low-intent traffic"}],
        )
        context = captured_messages[1].content
        assert "Negative Keywords" in context

    @pytest.mark.asyncio
    async def test_challenge_returns_raw_on_parse_failure(self):
        """If JSON parsing fails, returns a dict with raw content."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content="Red Team assessment: needs more data before proceeding."))
                ]
            )
        )
        agent = RedTeamAgent(llm=mock_llm)
        result = await agent.challenge(
            green_proposals=[{"type": "bid_update"}],
            campaign_data={},
            wiki_context=[],
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].get("type") == "raw"

    @pytest.mark.asyncio
    async def test_challenge_returns_approve_verdict_for_solid_proposal(self):
        """LLM can return an approve verdict when proposal is solid."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='[{"proposal_id": "0", "verdict": "approve", "objections": [], "reasoning": "well-supported by data and wiki research"}]'
                        )
                    )
                ]
            )
        )
        agent = RedTeamAgent(llm=mock_llm)
        result = await agent.challenge(
            green_proposals=[{"type": "keyword_add", "target": "proven term"}],
            campaign_data={"ctr": 0.05},
            wiki_context=[{"title": "Matching", "content": "proven term has strong conversion history"}],
        )
        assert result[0]["verdict"] == "approve"
        assert len(result[0]["objections"]) == 0
