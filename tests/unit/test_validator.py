"""
RED: Failing tests for AdversarialValidator.
Tests the full debate loop orchestration through the state machine.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, Mock
from uuid import uuid4

from src.agents.debate_state import DebateState, Phase
from src.research.validator import AdversarialValidator


class TestAdversarialValidatorRunCycle:
    """Test AdversarialValidator.run_cycle()."""

    @pytest.mark.asyncio
    async def test_run_cycle_pulls_performance_and_proposes(self):
        """run_cycle advances from PERFORMANCE_PULL to GREEN_PROPOSES."""
        cid = uuid4()

        advance_fn = Mock(side_effect=[
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.GREEN_PROPOSES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.RED_CHALLENGES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.COORDINATOR_EVALUATES),
        ])
        record_proposals_fn = Mock(side_effect=lambda state, proposals: state)
        record_objections_fn = Mock(side_effect=lambda state, obj: state)

        mock_state_machine = MagicMock()
        mock_state_machine.load_or_init.return_value = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.PERFORMANCE_PULL,
        )
        mock_state_machine.advance_phase = advance_fn
        mock_state_machine.record_proposals = record_proposals_fn
        mock_state_machine.record_objections = record_objections_fn

        mock_green = MagicMock()
        mock_green.propose = AsyncMock(return_value=[{"type": "keyword_add", "target": "shoes"}])
        mock_red = MagicMock()
        mock_red.challenge = AsyncMock(return_value=[])
        mock_coordinator = MagicMock()
        mock_coordinator.evaluate = AsyncMock(
            return_value=DebateState(
                cycle_date="2026-04-06",
                campaign_id=cid,
                phase=Phase.CONSENSUS_LOCKED,
                consensus_reached=True,
            )
        )

        validator = AdversarialValidator(
            green=mock_green,
            red=mock_red,
            coordinator=mock_coordinator,
            state_machine=mock_state_machine,
        )
        await validator.run_cycle(
            cycle_date="2026-04-06",
            campaign_id=cid,
            campaign_data={"clicks": 100},
            wiki_context=[],
        )
        mock_green.propose.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_cycle_records_green_proposals(self):
        """After green proposes, proposals are recorded in state."""
        cid = uuid4()
        mock_state_machine = MagicMock()

        initial_state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.PERFORMANCE_PULL,
        )
        green_proposals = [{"type": "keyword_add", "target": "running shoes"}]

        advance_fn = Mock(side_effect=[
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.GREEN_PROPOSES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.RED_CHALLENGES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.COORDINATOR_EVALUATES),
        ])

        def record_proposals(state, proposals):
            state.green_proposals = proposals
            return state

        mock_state_machine.load_or_init.return_value = initial_state
        mock_state_machine.advance_phase = advance_fn
        mock_state_machine.record_proposals.side_effect = record_proposals
        mock_state_machine.record_objections.side_effect = lambda state, objections: state
        mock_state_machine.save.side_effect = lambda s: s

        mock_green = MagicMock()
        mock_green.propose = AsyncMock(return_value=green_proposals)
        mock_red = MagicMock()
        mock_red.challenge = AsyncMock(return_value=[])
        mock_coordinator = MagicMock()
        mock_coordinator.evaluate = AsyncMock(
            return_value=DebateState(
                cycle_date="2026-04-06",
                campaign_id=cid,
                phase=Phase.CONSENSUS_LOCKED,
                consensus_reached=True,
            )
        )

        validator = AdversarialValidator(
            green=mock_green,
            red=mock_red,
            coordinator=mock_coordinator,
            state_machine=mock_state_machine,
        )
        await validator.run_cycle(
            cycle_date="2026-04-06",
            campaign_id=cid,
            campaign_data={},
            wiki_context=[],
        )
        mock_state_machine.record_proposals.assert_called_once()
        call_args = mock_state_machine.record_proposals.call_args
        assert call_args[0][1] == green_proposals

    @pytest.mark.asyncio
    async def test_run_cycle_returns_final_state(self):
        """run_cycle returns the final DebateState after consensus."""
        cid = uuid4()
        final_state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.CONSENSUS_LOCKED,
            consensus_reached=True,
            round_number=2,
        )

        advance_fn = Mock(side_effect=[
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.GREEN_PROPOSES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.RED_CHALLENGES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.COORDINATOR_EVALUATES),
        ])

        mock_state_machine = MagicMock()
        mock_state_machine.load_or_init.return_value = DebateState(
            cycle_date="2026-04-06", campaign_id=cid, phase=Phase.PERFORMANCE_PULL
        )
        mock_state_machine.save.return_value = final_state
        mock_state_machine.advance_phase = advance_fn
        mock_state_machine.record_proposals.side_effect = lambda state, proposals: state
        mock_state_machine.record_objections.side_effect = lambda state, objections: state

        mock_green = MagicMock()
        mock_green.propose = AsyncMock(return_value=[])
        mock_red = MagicMock()
        mock_red.challenge = AsyncMock(return_value=[])
        mock_coordinator = MagicMock()
        mock_coordinator.evaluate = AsyncMock(return_value=final_state)

        validator = AdversarialValidator(
            green=mock_green,
            red=mock_red,
            coordinator=mock_coordinator,
            state_machine=mock_state_machine,
        )
        result = await validator.run_cycle(
            cycle_date="2026-04-06",
            campaign_id=cid,
            campaign_data={},
            wiki_context=[],
        )
        assert result.consensus_reached is True
        assert result.phase == Phase.CONSENSUS_LOCKED

    @pytest.mark.asyncio
    async def test_run_cycle_loops_until_consensus_or_max_rounds(self):
        """run_cycle continues looping while phase is GREEN_PROPOSES or RED_CHALLENGES."""
        cid = uuid4()

        advance_fn = Mock(side_effect=[
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.GREEN_PROPOSES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.RED_CHALLENGES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.COORDINATOR_EVALUATES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.GREEN_PROPOSES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.RED_CHALLENGES),
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.COORDINATOR_EVALUATES),
        ])

        def fake_record_proposals(state, proposals):
            state.green_proposals = proposals
            return state

        def fake_record_objections(state, objections):
            state.red_objections = objections
            return state

        record_proposals_fn = Mock(side_effect=fake_record_proposals)
        record_objections_fn = Mock(side_effect=fake_record_objections)

        mock_state_machine = MagicMock()
        mock_state_machine.load_or_init.return_value = DebateState(
            cycle_date="2026-04-06", campaign_id=cid, phase=Phase.PERFORMANCE_PULL
        )
        mock_state_machine.advance_phase = advance_fn
        mock_state_machine.record_proposals = record_proposals_fn
        mock_state_machine.record_objections = record_objections_fn
        mock_state_machine.save.side_effect = lambda s: s

        # Round 1: coordinator returns GREEN_PROPOSES (no consensus)
        # Round 2: coordinator returns CONSENSUS_LOCKED
        eval_calls = {"count": 0}

        async def fake_evaluate(state, campaign_data, wiki_context):
            eval_calls["count"] += 1
            if eval_calls["count"] == 1:
                return DebateState(
                    cycle_date="2026-04-06", campaign_id=cid,
                    phase=Phase.GREEN_PROPOSES, round_number=2,
                    green_proposals=[{"type": "keyword_add"}],
                    red_objections=[],
                )
            else:
                return DebateState(
                    cycle_date="2026-04-06", campaign_id=cid,
                    phase=Phase.CONSENSUS_LOCKED, consensus_reached=True, round_number=3,
                )

        mock_green = MagicMock()
        mock_green.propose = AsyncMock(return_value=[{"type": "keyword_add"}])
        mock_red = MagicMock()
        mock_red.challenge = AsyncMock(return_value=[])
        mock_coordinator = MagicMock()
        mock_coordinator.evaluate = AsyncMock(side_effect=fake_evaluate)

        validator = AdversarialValidator(
            green=mock_green,
            red=mock_red,
            coordinator=mock_coordinator,
            state_machine=mock_state_machine,
        )
        result = await validator.run_cycle(
            cycle_date="2026-04-06",
            campaign_id=cid,
            campaign_data={},
            wiki_context=[],
        )
        assert eval_calls["count"] == 2  # Two evaluate calls (two rounds)