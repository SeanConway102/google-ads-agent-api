"""
RED: Failing tests for GreenTeamAgent.
Tests that GreenTeamAgent correctly builds context and parses proposals from LLM.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from src.agents.green_team import GreenTeamAgent


class TestGreenTeamAgent:
    """Test GreenTeamAgent.propose() method."""

    @pytest.mark.asyncio
    async def test_propose_returns_list_of_proposals(self):
        """propose returns a list of proposal dicts from parsed LLM response."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='[{"type": "keyword_add", "target": "running shoes", "change": "add EXACT keyword", "priority": "high", "reasoning": "high search volume", "evidence": [], "campaign_id": "123"}]'
                        )
                    )
                ]
            )
        )
        agent = GreenTeamAgent(llm=mock_llm)
        result = await agent.propose(
            campaign_data={"clicks": 100, "ctr": 0.02},
            wiki_context=[{"title": "Keyword Research", "content": "Running shoes converts well"}],
            previous_objections=[],
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "keyword_add"
        assert result[0]["target"] == "running shoes"

    @pytest.mark.asyncio
    async def test_propose_builds_context_with_campaign_data(self):
        """Context includes campaign performance data."""
        mock_llm = MagicMock()
        captured_messages = []

        async def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="[]"))]
            )

        mock_llm.chat_completion = AsyncMock(side_effect=capture_chat)
        agent = GreenTeamAgent(llm=mock_llm)
        await agent.propose(
            campaign_data={"clicks": 500, "ctr": 0.05, "spend": 100.00},
            wiki_context=[],
            previous_objections=[],
        )
        context = captured_messages[1].content
        assert "clicks" in context
        assert "500" in context
        assert "ctr" in context

    @pytest.mark.asyncio
    async def test_propose_builds_context_with_wiki_entries(self):
        """Context includes wiki research entries."""
        mock_llm = MagicMock()
        captured_messages = []

        async def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="[]"))]
            )

        mock_llm.chat_completion = AsyncMock(side_effect=capture_chat)
        agent = GreenTeamAgent(llm=mock_llm)
        await agent.propose(
            campaign_data={},
            wiki_context=[
                {"title": "Broad Match Best Practices", "content": "Use broad match for discovery"},
                {"title": "Exact Match", "content": "Exact match has highest CTR"},
            ],
            previous_objections=[],
        )
        context = captured_messages[1].content
        assert "Broad Match Best Practices" in context
        assert "Exact Match" in context

    @pytest.mark.asyncio
    async def test_propose_includes_previous_objections_when_provided(self):
        """When previous_objections is non-empty, context includes them."""
        mock_llm = MagicMock()
        captured_messages = []

        async def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="[]"))]
            )

        mock_llm.chat_completion = AsyncMock(side_effect=capture_chat)
        agent = GreenTeamAgent(llm=mock_llm)
        objections = [{"verdict": "object", "objection": "seasonality — Q1 is low season"}]
        await agent.propose(
            campaign_data={},
            wiki_context=[],
            previous_objections=objections,
        )
        context = captured_messages[1].content
        assert "seasonality" in context
        assert "previous" in context.lower() or "objection" in context.lower()

    @pytest.mark.asyncio
    async def test_propose_parses_multiple_proposals(self):
        """LLM can return multiple proposals in a JSON array."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='['
                            '{"type": "keyword_add", "target": "winter boots", "priority": "high"},'
                            '{"type": "bid_update", "target": "existing keyword", "priority": "medium"}'
                            ']'
                        )
                    )
                ]
            )
        )
        agent = GreenTeamAgent(llm=mock_llm)
        result = await agent.propose(campaign_data={}, wiki_context=[], previous_objections=[])
        assert len(result) == 2
        assert result[0]["type"] == "keyword_add"
        assert result[1]["type"] == "bid_update"

    @pytest.mark.asyncio
    async def test_propose_returns_raw_content_on_json_parse_failure(self):
        """If JSON parsing fails, returns a dict with raw content."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content="The Green Team proposes the following changes: ..."))
                ]
            )
        )
        agent = GreenTeamAgent(llm=mock_llm)
        result = await agent.propose(campaign_data={}, wiki_context=[], previous_objections=[])
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].get("type") == "raw"
