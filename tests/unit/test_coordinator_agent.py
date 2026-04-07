"""
RED: Failing tests for CoordinatorAgent.
Tests that the coordinator correctly builds context, calls the LLM, and applies decisions.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from src.agents.debate_state import DebateState, Phase
from src.agents.coordinator import CoordinatorAgent


class TestCoordinatorAgent:
    """Test CoordinatorAgent.evaluate() method."""

    @pytest.mark.asyncio
    async def test_evaluate_returns_debate_state(self):
        """Coordinator.evaluate returns the updated DebateState."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="[CONSENSUS_REACHED] All agents agree."))]
            )
        )
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=uuid4(),
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=2,
            green_proposals=[{"type": "keyword_add", "target": "running shoes"}],
            red_objections=[],
        )
        result = await agent.evaluate(state, {}, [])
        assert isinstance(result, DebateState)
        assert result.consensus_reached is True

    @pytest.mark.asyncio
    async def test_evaluate_extracts_consensus_reached_verdict(self):
        """[CONSENSUS_REACHED] sets consensus_reached=True and phase to CONSENSUS_LOCKED."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="The proposal is sound.\n[CONSENSUS_REACHED] All agents agree — proceed."))]
            )
        )
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=uuid4(),
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=1,
            green_proposals=[{"type": "bid_update", "target": "keyword 123"}],
            red_objections=[{"verdict": "approve", "reasoning": "solid data"}],
        )
        result = await agent.evaluate(state, {}, [])
        assert result.consensus_reached is True
        assert result.phase == Phase.CONSENSUS_LOCKED

    @pytest.mark.asyncio
    async def test_evaluate_extracts_continue_debate_verdict(self):
        """[CONTINUE_DEBATE] increments round and returns to GREEN_PROPOSES."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Red raises valid concerns.\n[CONTINUE_DEBATE] Green should revise."))]
            )
        )
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=uuid4(),
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=2,
            green_proposals=[{"type": "keyword_add"}],
            red_objections=[{"verdict": "object", "objection": "seasonality concern"}],
        )
        result = await agent.evaluate(state, {}, [])
        assert result.round_number == 3
        assert result.phase == Phase.GREEN_PROPOSES
        assert result.consensus_reached is False

    @pytest.mark.asyncio
    async def test_evaluate_extracts_escalate_verdict(self):
        """[ESCALATE] sets phase to PENDING_MANUAL_REVIEW."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Unresolved conflict after max rounds.\n[ESCALATE] Max rounds reached."))]
            )
        )
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=uuid4(),
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=5,
            green_proposals=[{"type": "keyword_add"}],
            red_objections=[{"verdict": "object"}],
        )
        result = await agent.evaluate(state, {}, [])
        assert result.phase == Phase.PENDING_MANUAL_REVIEW

    @pytest.mark.asyncio
    async def test_evaluate_extracts_compromise_proposed_verdict(self):
        """[COMPROMISE_PROPOSED] sets compromise_proposed=True, phase back to GREEN_PROPOSES."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="I propose a middle ground.\n[COMPROMISE_PROPOSED] Both teams must ratify."))]
            )
        )
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=uuid4(),
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=3,
            green_proposals=[{"type": "bid_update", "change": "increase by 20%"}],
            red_objections=[{"verdict": "object", "objection": "too aggressive"}],
        )
        result = await agent.evaluate(state, {}, [])
        assert result.compromise_proposed is True
        assert result.phase == Phase.GREEN_PROPOSES
        assert result.round_number == 3  # no increment on compromise

    @pytest.mark.asyncio
    async def test_evaluate_builds_context_with_round_and_phase(self):
        """Context passed to LLM includes round number and max_rounds."""
        mock_llm = MagicMock()
        captured_messages = []

        async def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return MagicMock(choices=[MagicMock(message=MagicMock(content="[CONSENSUS_REACHED]"))])

        mock_llm.chat_completion = AsyncMock(side_effect=capture_chat)
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)
        cid = uuid4()
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=3,
            green_proposals=[],
            red_objections=[],
        )
        await agent.evaluate(state, {"clicks": 100}, [])
        assert len(captured_messages) == 2  # system prompt + user context
        context = captured_messages[1].content
        assert '"round": 3' in context or '"round": 3,' in context
        assert '"max_rounds": 5' in context

    @pytest.mark.asyncio
    async def test_evaluate_passes_no_llm_response_defaults_to_continue(self):
        """If LLM returns no recognizable verdict tag, defaults to continue_debate."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="The proposal needs more work."))]
            )
        )
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=uuid4(),
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=1,
            green_proposals=[{"type": "keyword_add"}],
            red_objections=[],
        )
        result = await agent.evaluate(state, {}, [])
        # No verdict tag → defaults to continue_debate
        assert result.round_number == 2
        assert result.phase == Phase.GREEN_PROPOSES

    @pytest.mark.asyncio
    async def test_evaluate_uses_settings_max_rounds_when_not_provided(self):
        """When max_rounds is not passed, _resolve_max_rounds falls back to settings."""
        from unittest.mock import patch

        mock_settings = MagicMock()
        mock_settings.MAX_DEBATE_ROUNDS = 12

        cid = uuid4()
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="[CONTINUE_DEBATE] Keep going."))]
            )
        )

        with patch("src.agents.coordinator.get_settings", return_value=mock_settings):
            agent = CoordinatorAgent(llm=mock_llm)  # no max_rounds
            state = DebateState(
                cycle_date="2026-04-06",
                campaign_id=cid,
                phase=Phase.COORDINATOR_EVALUATES,
                round_number=11,
                green_proposals=[{"type": "keyword_add"}],
                red_objections=[],
            )
            result = await agent.evaluate(state, {}, [])
            # max_rounds=12, round 11 < 12 → should continue (not escalate)
            assert result.phase == Phase.GREEN_PROPOSES
            assert result.round_number == 12

    @pytest.mark.asyncio
    async def test_evaluate_uses_chat_completion_when_llm_is_none(self):
        """When no LLM is injected, evaluate() calls chat_completion from adapter."""
        from unittest.mock import patch

        mock_settings = MagicMock()
        mock_settings.MAX_DEBATE_ROUNDS = 5

        async def fake_chat_completion(messages, **kwargs):
            return MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content="[CONSENSUS_REACHED] All good."))
                ]
            )

        with patch("src.llm.adapter.chat_completion", fake_chat_completion), \
             patch("src.agents.coordinator.get_settings", return_value=mock_settings), \
             patch("src.config.get_settings", return_value=mock_settings):
            agent = CoordinatorAgent()  # no llm
            cid = uuid4()
            state = DebateState(
                cycle_date="2026-04-06",
                campaign_id=cid,
                phase=Phase.COORDINATOR_EVALUATES,
                round_number=1,
                green_proposals=[{"type": "keyword_add"}],
                red_objections=[],
            )
            result = await agent.evaluate(state, {}, [])
            assert result.consensus_reached is True

    @pytest.mark.asyncio
    async def test_evaluate_raises_when_llm_returns_empty_choices(self):
        """When LLM returns no choices, raises RuntimeError."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(return_value=MagicMock(choices=[]))
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)  # avoid get_settings() call
        cid = uuid4()
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=1,
            green_proposals=[],
            red_objections=[],
        )

        with pytest.raises(RuntimeError, match="LLM returned empty response"):
            await agent.evaluate(state, {}, [])

    @pytest.mark.asyncio
    async def test_evaluate_raises_when_message_is_none(self):
        """When LLM choice has no message, raises RuntimeError."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=None)])
        )
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)
        cid = uuid4()
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=1,
            green_proposals=[],
            red_objections=[],
        )

        with pytest.raises(RuntimeError, match="LLM returned choice with no message"):
            await agent.evaluate(state, {}, [])

    @pytest.mark.asyncio
    async def test_evaluate_raises_when_content_is_none(self):
        """When LLM message content is None, raises RuntimeError."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=MagicMock(content=None))])
        )
        agent = CoordinatorAgent(llm=mock_llm, max_rounds=5)
        cid = uuid4()
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES,
            round_number=1,
            green_proposals=[],
            red_objections=[],
        )

        with pytest.raises(RuntimeError, match="LLM returned None content"):
            await agent.evaluate(state, {}, [])
