"""
Debate state machine — manages phase transitions and persistence for the
three-agent adversarial debate system.

Phase transitions:
  IDLE -> PERFORMANCE_PULL -> GREEN_PROPOSES -> RED_CHALLENGES
    -> COORDINATOR_EVALUATES -> CONSENSUS_LOCKED | PENDING_MANUAL_REVIEW

A "continue_debate" verdict increments round_number and returns to GREEN_PROPOSES.
A "compromise_proposed" verdict sets compromise_proposed=True and returns to GREEN_PROPOSES.
A "consensus" verdict sets consensus_reached=True and transitions to CONSENSUS_LOCKED.
An "escalate" verdict transitions to PENDING_MANUAL_REVIEW.
"""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from src.db.postgres_adapter import PostgresAdapter


class Phase(str, Enum):
    IDLE = "idle"
    PERFORMANCE_PULL = "performance_pull"
    GREEN_PROPOSES = "green_proposes"
    RED_CHALLENGES = "red_challenges"
    COORDINATOR_EVALUATES = "coordinator_evaluates"
    CONSENSUS_LOCKED = "consensus_locked"
    WIKI_UPDATE = "wiki_update"
    PENDING_MANUAL_REVIEW = "pending_manual_review"


@dataclass
class DebateState:
    """Debate state for a single campaign in a single research cycle."""
    cycle_date: str
    campaign_id: UUID
    phase: Phase = Phase.IDLE
    round_number: int = 1
    green_proposals: list[dict[str, Any]] = field(default_factory=list)
    red_objections: list[dict[str, Any]] = field(default_factory=list)
    coordinator_decision: Optional[dict[str, Any]] = None
    consensus_reached: bool = False
    compromise_proposed: bool = False
    compromise_accepted_by_green: bool = False
    compromise_accepted_by_red: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["phase"] = self.phase.value
        # Serialize UUID as string for JSONB storage
        if isinstance(d["campaign_id"], UUID):
            d["campaign_id"] = str(d["campaign_id"])
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DebateState":
        phase_val = data.get("phase", "idle")
        phase = Phase(phase_val) if isinstance(phase_val, str) else phase_val
        # Remove keys that aren't dataclass fields (e.g. 'id', 'created_at' from DB rows)
        field_names = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in field_names}
        filtered["phase"] = phase
        return cls(**filtered)


class DebateStateMachine:
    """
    Manages debate state transitions and persistence.

    The state machine ensures debate proceeds in phases:
    1. PERFORMANCE_PULL — gather campaign data
    2. GREEN_PROPOSES — Green Team proposes optimizations
    3. RED_CHALLENGES — Red Team reviews and raises objections
    4. COORDINATOR_EVALUATES — Coordinator decides consensus/continue/escalate
    """

    def __init__(self, db: PostgresAdapter) -> None:
        self._db = db

    def start_cycle(self, cycle_date: str, campaign_id: UUID) -> DebateState:
        """Begin a new debate cycle for a campaign."""
        state = DebateState(
            cycle_date=cycle_date,
            campaign_id=campaign_id,
            phase=Phase.PERFORMANCE_PULL,
        )
        return self._save(state)

    def save(self, state: DebateState) -> DebateState:
        """Persist the current state and return the saved copy."""
        return self._save(state)

    def _save(self, state: DebateState) -> DebateState:
        result = self._db.save_debate_state(state.to_dict())
        return DebateState.from_dict(dict(result))

    def load_or_init(self, cycle_date: str, campaign_id: UUID) -> DebateState:
        """
        Load an existing active debate state, or start a new cycle if none exists.
        """
        existing = self._db.get_latest_debate_state(cycle_date, campaign_id)
        if existing:
            state = DebateState.from_dict(dict(existing))
            # Only resume if not already concluded
            if state.phase not in (Phase.IDLE, Phase.CONSENSUS_LOCKED):
                return state
        return self.start_cycle(cycle_date, campaign_id)

    def advance_phase(self, state: DebateState) -> DebateState:
        """
        Advance the debate to the next phase.

        Transitions:
          PERFORMANCE_PULL -> GREEN_PROPOSES
          GREEN_PROPOSES -> RED_CHALLENGES
          RED_CHALLENGES -> COORDINATOR_EVALUATES
          Other phases: no transition (already terminal or handled by evaluate_consensus)
        """
        transitions = {
            Phase.PERFORMANCE_PULL: Phase.GREEN_PROPOSES,
            Phase.GREEN_PROPOSES: Phase.RED_CHALLENGES,
            Phase.RED_CHALLENGES: Phase.COORDINATOR_EVALUATES,
        }
        next_phase = transitions.get(state.phase, state.phase)
        state.phase = next_phase
        return self._save(state)

    def record_proposals(self, state: DebateState, proposals: list[dict[str, Any]]) -> DebateState:
        """Record Green Team's proposals and persist."""
        state.green_proposals = proposals
        return self._save(state)

    def record_objections(self, state: DebateState, objections: list[dict[str, Any]]) -> DebateState:
        """Record Red Team's objections and persist."""
        state.red_objections = objections
        return self._save(state)

    def evaluate_consensus(
        self,
        state: DebateState,
        coordinator_decision: Optional[dict[str, Any]],
    ) -> DebateState:
        """
        Process the Coordinator's decision and transition the state accordingly.

        Verdict outcomes:
          consensus     -> CONSENSUS_LOCKED, consensus_reached=True
          compromise    -> GREEN_PROPOSES (teams must ratify), compromise_proposed=True
          escalate      -> PENDING_MANUAL_REVIEW
          continue_debate -> GREEN_PROPOSES, round_number += 1
        """
        if coordinator_decision is None:
            coordinator_decision = {"verdict": "continue_debate"}
        state.coordinator_decision = coordinator_decision
        verdict = coordinator_decision.get("verdict", "continue_debate")

        if verdict == "consensus":
            state.consensus_reached = True
            state.phase = Phase.CONSENSUS_LOCKED
        elif verdict == "compromise_proposed":
            state.compromise_proposed = True
            state.phase = Phase.GREEN_PROPOSES
            # No round increment — compromise is not a new debate round
        elif verdict == "escalate":
            state.phase = Phase.PENDING_MANUAL_REVIEW
        else:
            # continue_debate or unknown — increment round, return to green
            state.round_number += 1
            state.phase = Phase.GREEN_PROPOSES

        return self._save(state)
