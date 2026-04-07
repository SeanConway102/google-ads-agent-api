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
    async def test_max_rounds_defaults_to_10_when_coordinator_has_no_max_rounds(self):
        """When coordinator has no max_rounds attribute, defaults to 10."""
        cid = uuid4()
        mock_state_machine = MagicMock()
        mock_state_machine.load_or_init.return_value = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES,
            green_proposals=[],
            red_objections=[],
            consensus_reached=False,
            round_number=10,
        )
        mock_state_machine.save.return_value = None  # simulate save returning None

        # coordinator with no max_rounds attribute
        mock_coordinator = MagicMock()
        del mock_coordinator.max_rounds  # remove the attribute

        mock_green = MagicMock()
        mock_red = MagicMock()
        validator = AdversarialValidator(
            green=mock_green,
            red=mock_red,
            coordinator=mock_coordinator,
            state_machine=mock_state_machine,
        )
        # Should use max_rounds = 10 and return early when round_number >= 10
        result = await validator.run_cycle(
            cycle_date="2026-04-06",
            campaign_id=cid,
            campaign_data={},
            wiki_context=[],
        )
        # Should return the state (max rounds reached)
        assert result is not None

    @pytest.mark.asyncio
    async def test_coordinator_returns_pending_manual_review_saves_and_returns(self):
        """When coordinator.evaluate() returns PENDING_MANUAL_REVIEW, state is saved and returned."""
        cid = uuid4()
        pending_state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.PENDING_MANUAL_REVIEW,
            consensus_reached=False,
            round_number=5,
            green_proposals=[{"type": "keyword_add"}],
            red_objections=[{"objection": "cost"}],
        )

        mock_state_machine = MagicMock()
        mock_state_machine.load_or_init.return_value = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES,
            green_proposals=[],
            red_objections=[],
            consensus_reached=False,
            round_number=4,
        )
        mock_state_machine.save.return_value = pending_state

        mock_coordinator = MagicMock()
        mock_coordinator.evaluate = AsyncMock(return_value=pending_state)
        mock_green = MagicMock()
        mock_red = MagicMock()

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
        mock_state_machine.save.assert_called_once()
        assert result.phase == Phase.PENDING_MANUAL_REVIEW
        assert result.consensus_reached is False

    @pytest.mark.asyncio
    async def test_green_propose_raises_exception_causes_early_return(self):
        """When green.propose() raises, run_cycle returns the current state."""
        cid = uuid4()
        mock_state_machine = MagicMock()
        mock_state_machine.load_or_init.return_value = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.GREEN_PROPOSES,
            green_proposals=[],
            red_objections=[],
            consensus_reached=False,
            round_number=1,
        )
        mock_state_machine.advance_phase.side_effect = [
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.GREEN_PROPOSES),
        ]

        mock_green = MagicMock()
        mock_green.propose = AsyncMock(side_effect=RuntimeError("Green failed"))
        mock_red = MagicMock()
        mock_coordinator = MagicMock()

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
        # Should return the current state without crashing
        assert result.phase == Phase.GREEN_PROPOSES

    @pytest.mark.asyncio
    async def test_red_challenge_raises_exception_causes_early_return(self):
        """When red.challenge() raises, run_cycle returns the current state."""
        cid = uuid4()
        mock_state_machine = MagicMock()
        mock_state_machine.load_or_init.return_value = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.RED_CHALLENGES,
            green_proposals=[{"type": "keyword_add"}],
            red_objections=[],
            consensus_reached=False,
            round_number=1,
        )
        mock_state_machine.advance_phase.side_effect = [
            DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.RED_CHALLENGES),
        ]

        mock_green = MagicMock()
        mock_red = MagicMock()
        mock_red.challenge = AsyncMock(side_effect=RuntimeError("Red failed"))
        mock_coordinator = MagicMock()

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
        assert result.phase == Phase.RED_CHALLENGES

    @pytest.mark.asyncio
    async def test_coordinator_evaluate_raises_exception_causes_early_return(self):
        """When coordinator.evaluate() raises, run_cycle returns the current state."""
        cid = uuid4()
        mock_state_machine = MagicMock()
        mock_state_machine.load_or_init.return_value = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES,
            green_proposals=[{"type": "keyword_add"}],
            red_objections=[],
            consensus_reached=False,
            round_number=1,
        )
        mock_state_machine.save.side_effect = lambda s: s

        mock_coordinator = MagicMock()
        mock_coordinator.evaluate = AsyncMock(side_effect=RuntimeError("Coordinator failed"))
        mock_green = MagicMock()
        mock_red = MagicMock()

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
        # Should return the current state without crashing
        assert result.phase == Phase.COORDINATOR_EVALUATES

    @pytest.mark.asyncio
    async def test_unhandled_phase_returns_current_state(self):
        """When state.phase is an unhandled value, loop breaks and returns current state."""
        cid = uuid4()
        mock_state_machine = MagicMock()
        # Start in a phase not handled in the loop (e.g., CONSENSUS_LOCKED which is handled differently)
        mock_state_machine.load_or_init.return_value = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.CONSENSUS_LOCKED,
            consensus_reached=True,
            round_number=1,
        )

        mock_green = MagicMock()
        mock_red = MagicMock()
        mock_coordinator = MagicMock()

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
        # CONSENSUS_LOCKED is handled in COORDINATOR_EVALUATES branch, not the else
        # This test covers the else branch for truly unhandled phases
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