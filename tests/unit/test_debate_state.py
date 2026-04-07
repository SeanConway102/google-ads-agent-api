"""
RED: Write failing tests for debate state machine.
Tests DebateState dataclass, Phase enum, and DebateStateMachine transitions.
"""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from src.agents.debate_state import DebateState, Phase, DebateStateMachine


class TestDebateStateDataclass:
    """Test DebateState creation, serialization, and deserialization."""

    def test_debate_state_defaults_to_idle(self):
        cid = uuid4()
        state = DebateState(cycle_date="2026-04-06", campaign_id=cid)
        assert state.phase == Phase.IDLE
        assert state.round_number == 1
        assert state.consensus_reached is False
        assert state.compromise_proposed is False

    def test_debate_state_to_dict_serialization(self):
        cid = uuid4()
        state = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.GREEN_PROPOSES,
            round_number=2,
            green_proposals=[{"type": "keyword_add", "target": "shoes sale"}],
        )
        d = state.to_dict()
        assert d["phase"] == "green_proposes"
        assert d["campaign_id"] == str(cid)
        assert d["round_number"] == 2
        assert len(d["green_proposals"]) == 1
        assert d["green_proposals"][0]["type"] == "keyword_add"

    def test_debate_state_from_dict_round_trip(self):
        cid = uuid4()
        original = DebateState(
            cycle_date="2026-04-06",
            campaign_id=cid,
            phase=Phase.RED_CHALLENGES,
            round_number=3,
            green_proposals=[{"type": "bid_update"}],
            red_objections=[{"verdict": "object", "objection": "too risky"}],
        )
        d = original.to_dict()
        restored = DebateState.from_dict(d)
        assert restored.phase == Phase.RED_CHALLENGES
        assert restored.round_number == 3
        assert len(restored.green_proposals) == 1
        assert len(restored.red_objections) == 1

    def test_debate_state_compromise_flags_initially_false(self):
        state = DebateState(cycle_date="2026-04-06", campaign_id=uuid4())
        assert state.compromise_accepted_by_green is False
        assert state.compromise_accepted_by_red is False


class TestPhaseEnum:
    """Test Phase enum values."""

    def test_all_phases_exist(self):
        assert Phase.IDLE.value == "idle"
        assert Phase.PERFORMANCE_PULL.value == "performance_pull"
        assert Phase.GREEN_PROPOSES.value == "green_proposes"
        assert Phase.RED_CHALLENGES.value == "red_challenges"
        assert Phase.COORDINATOR_EVALUATES.value == "coordinator_evaluates"
        assert Phase.CONSENSUS_LOCKED.value == "consensus_locked"
        assert Phase.WIKI_UPDATE.value == "wiki_update"
        assert Phase.PENDING_MANUAL_REVIEW.value == "pending_manual_review"


class TestDebateStateMachine:
    """Test DebateStateMachine phase transitions and record operations."""

    def test_start_cycle_sets_phase_to_performance_pull(self):
        mock_db = MagicMock()
        mock_db.save_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "performance_pull",
            "round_number": 1,
            "green_proposals": [],
            "red_objections": [],
            "coordinator_decision": None,
            "consensus_reached": False,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = sm.start_cycle("2026-04-06", cid)
        assert state.phase == Phase.PERFORMANCE_PULL
        mock_db.save_debate_state.assert_called_once()

    def test_advance_phase_performance_pull_to_green_proposes(self):
        mock_db = MagicMock()
        mock_db.save_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "green_proposes",
            "round_number": 1,
            "green_proposals": [],
            "red_objections": [],
            "coordinator_decision": None,
            "consensus_reached": False,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.PERFORMANCE_PULL)
        next_state = sm.advance_phase(state)
        assert next_state.phase == Phase.GREEN_PROPOSES

    def test_advance_phase_green_proposes_to_red_challenges(self):
        mock_db = MagicMock()
        mock_db.save_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "red_challenges",
            "round_number": 1,
            "green_proposals": [],
            "red_objections": [],
            "coordinator_decision": None,
            "consensus_reached": False,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.GREEN_PROPOSES)
        next_state = sm.advance_phase(state)
        assert next_state.phase == Phase.RED_CHALLENGES

    def test_advance_phase_red_challenges_to_coordinator_evaluates(self):
        mock_db = MagicMock()
        mock_db.save_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "coordinator_evaluates",
            "round_number": 1,
            "green_proposals": [],
            "red_objections": [],
            "coordinator_decision": None,
            "consensus_reached": False,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.RED_CHALLENGES)
        next_state = sm.advance_phase(state)
        assert next_state.phase == Phase.COORDINATOR_EVALUATES

    def test_record_proposals_updates_state_and_persists(self):
        mock_db = MagicMock()
        mock_db.save_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "green_proposes",
            "round_number": 1,
            "green_proposals": [{"type": "keyword_add", "target": "running shoes"}],
            "red_objections": [],
            "coordinator_decision": None,
            "consensus_reached": False,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.GREEN_PROPOSES)
        proposals = [{"type": "keyword_add", "target": "running shoes"}]
        updated = sm.record_proposals(state, proposals)
        assert len(updated.green_proposals) == 1
        assert updated.green_proposals[0]["target"] == "running shoes"

    def test_record_objections_updates_state_and_persists(self):
        mock_db = MagicMock()
        mock_db.save_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "red_challenges",
            "round_number": 1,
            "green_proposals": [],
            "red_objections": [{"verdict": "object", "objection": "seasonality"}],
            "coordinator_decision": None,
            "consensus_reached": False,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.RED_CHALLENGES)
        objections = [{"verdict": "object", "objection": "seasonality"}]
        updated = sm.record_objections(state, objections)
        assert len(updated.red_objections) == 1
        assert updated.red_objections[0]["verdict"] == "object"

    def test_evaluate_consensus_sets_consensus_locked(self):
        mock_db = MagicMock()
        mock_db.save_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "consensus_locked",
            "round_number": 2,
            "green_proposals": [],
            "red_objections": [],
            "coordinator_decision": {"verdict": "consensus"},
            "consensus_reached": True,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.COORDINATOR_EVALUATES)
        decision = {"verdict": "consensus", "raw_response": "All agree"}
        updated = sm.evaluate_consensus(state, decision)
        assert updated.consensus_reached is True
        assert updated.phase == Phase.CONSENSUS_LOCKED

    def test_evaluate_consensus_compromise_proposed_does_not_increment_round(self):
        mock_db = MagicMock()

        def capture_save(data):
            return {
                "cycle_date": data["cycle_date"],
                "campaign_id": str(data["campaign_id"]),
                "phase": data["phase"],
                "round_number": data["round_number"],
                "green_proposals": data.get("green_proposals", []),
                "red_objections": data.get("red_objections", []),
                "coordinator_decision": data.get("coordinator_decision"),
                "consensus_reached": data.get("consensus_reached", False),
                "compromise_proposed": data.get("compromise_proposed", False),
                "compromise_accepted_by_green": False,
                "compromise_accepted_by_red": False,
            }

        mock_db.save_debate_state.side_effect = capture_save
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(
            cycle_date="2026-04-06", campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES, round_number=1
        )
        decision = {"verdict": "compromise_proposed", "compromise": {"type": "reduce_budget_by_half"}}
        updated = sm.evaluate_consensus(state, decision)
        assert updated.compromise_proposed is True
        assert updated.round_number == 1  # compromise does NOT increment round
        assert updated.phase == Phase.GREEN_PROPOSES

    def test_evaluate_consensus_escalate_sets_pending_manual_review(self):
        mock_db = MagicMock()
        mock_db.save_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "pending_manual_review",
            "round_number": 5,
            "green_proposals": [],
            "red_objections": [],
            "coordinator_decision": {"verdict": "escalate"},
            "consensus_reached": False,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(
            cycle_date="2026-04-06", campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES, round_number=5
        )
        decision = {"verdict": "escalate"}
        updated = sm.evaluate_consensus(state, decision)
        assert updated.phase == Phase.PENDING_MANUAL_REVIEW

    def test_evaluate_consensus_continue_debate_increments_round(self):
        mock_db = MagicMock()
        saved_states = []

        def capture_save(data):
            saved_states.append(data)
            return {
                "cycle_date": data["cycle_date"],
                "campaign_id": str(data["campaign_id"]),
                "phase": "green_proposes",
                "round_number": data["round_number"],
                "green_proposals": data.get("green_proposals", []),
                "red_objections": data.get("red_objections", []),
                "coordinator_decision": data.get("coordinator_decision"),
                "consensus_reached": False,
                "compromise_proposed": False,
                "compromise_accepted_by_green": False,
                "compromise_accepted_by_red": False,
            }

        mock_db.save_debate_state.side_effect = capture_save
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(
            cycle_date="2026-04-06", campaign_id=cid,
            phase=Phase.COORDINATOR_EVALUATES, round_number=2
        )
        decision = {"verdict": "continue_debate"}
        updated = sm.evaluate_consensus(state, decision)
        assert updated.round_number == 3
        assert updated.phase == Phase.GREEN_PROPOSES

    def test_load_or_init_returns_existing_active_state(self):
        mock_db = MagicMock()
        mock_db.get_latest_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "green_proposes",
            "round_number": 2,
            "green_proposals": [{"type": "keyword_add"}],
            "red_objections": [],
            "coordinator_decision": None,
            "consensus_reached": False,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = sm.load_or_init("2026-04-06", cid)
        assert state.phase == Phase.GREEN_PROPOSES
        assert state.round_number == 2
        mock_db.get_latest_debate_state.assert_called_once_with("2026-04-06", cid)

    def test_load_or_init_starts_new_cycle_when_idle(self):
        mock_db = MagicMock()
        mock_db.get_latest_debate_state.return_value = None
        mock_db.save_debate_state.return_value = {
            "cycle_date": "2026-04-06",
            "campaign_id": str(uuid4()),
            "phase": "performance_pull",
            "round_number": 1,
            "green_proposals": [],
            "red_objections": [],
            "coordinator_decision": None,
            "consensus_reached": False,
            "compromise_proposed": False,
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = sm.load_or_init("2026-04-06", cid)
        assert state.phase == Phase.PERFORMANCE_PULL
        mock_db.start_cycle.assert_not_called()  # uses save internally

    def test_evaluate_consensus_with_consensus_reached_verdict_from_coordinator(self):
        """
        RED: evaluate_consensus should accept verdict 'consensus_reached'
        (what CoordinatorAgent._apply_decision produces) not just 'consensus'.
        
        CoordinatorAgent._parse_decision extracts [CONSENSUS_REACHED] → verdict='consensus_reached'
        CoordinatorAgent._apply_decision checks for 'consensus_reached'
        But DebateStateMachine.evaluate_consensus checks for 'consensus' — mismatch.
        
        When a coordinator decision with verdict='consensus_reached' flows into the
        state machine's evaluate_consensus, the consensus is NOT applied.
        """
        mock_db = MagicMock()
        mock_db.save_debate_state.side_effect = lambda data: {
            "cycle_date": data["cycle_date"],
            "campaign_id": str(data["campaign_id"]),
            "phase": data["phase"],
            "round_number": data["round_number"],
            "green_proposals": data.get("green_proposals", []),
            "red_objections": data.get("red_objections", []),
            "coordinator_decision": data.get("coordinator_decision"),
            "consensus_reached": data.get("consensus_reached", False),
            "compromise_proposed": data.get("compromise_proposed", False),
            "compromise_accepted_by_green": False,
            "compromise_accepted_by_red": False,
        }
        sm = DebateStateMachine(mock_db)
        cid = uuid4()
        state = DebateState(
            cycle_date="2026-04-06", campaign_id=cid, phase=Phase.COORDINATOR_EVALUATES
        )
        # This is the verdict string CoordinatorAgent._apply_decision produces
        coordinator_decision = {"verdict": "consensus_reached", "raw_response": "All agents agree"}
        updated = sm.evaluate_consensus(state, coordinator_decision)
        # The bug: evaluate_consensus checks for 'consensus' not 'consensus_reached'
        # So consensus_reached stays False and phase stays COORDINATOR_EVALUATES
        assert updated.consensus_reached is True, (
            f"verdict='consensus_reached' from CoordinatorAgent should set consensus_reached=True, "
            f"got consensus_reached={updated.consensus_reached}, phase={updated.phase}"
        )
        assert updated.phase == Phase.CONSENSUS_LOCKED
