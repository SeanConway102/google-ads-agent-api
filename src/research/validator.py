"""
AdversarialValidator — orchestrates the full debate loop through the state machine.
"""
from typing import Any

from src.agents.debate_state import DebateState, Phase


class AdversarialValidator:
    """Orchestrates the full adversarial debate loop."""

    def __init__(
        self,
        green: Any,
        red: Any,
        coordinator: Any,
        state_machine: Any,
    ) -> None:
        self._green = green
        self._red = red
        self._coordinator = coordinator
        self._state_machine = state_machine

    async def run_cycle(
        self,
        cycle_date: str,
        campaign_id: Any,
        campaign_data: dict[str, Any],
        wiki_context: list[dict[str, Any]],
    ) -> DebateState:
        """
        Run the full debate cycle from PERFORMANCE_PULL through to consensus.

        Args:
            cycle_date: Date string for this cycle
            campaign_id: UUID of the campaign
            campaign_data: Campaign metrics and data
            wiki_context: Relevant wiki entries for context

        Returns:
            The final DebateState after consensus or max rounds
        """
        state = self._state_machine.load_or_init(
            cycle_date=cycle_date,
            campaign_id=campaign_id,
        )

        max_rounds_attr = getattr(self._coordinator, "max_rounds", None)
        if isinstance(max_rounds_attr, int):
            max_rounds = max_rounds_attr
        else:
            max_rounds = 10

        while True:
            if not isinstance(state, DebateState):
                break

            if state.phase == Phase.PERFORMANCE_PULL:
                next_state = self._state_machine.advance_phase(state)
                if not isinstance(next_state, DebateState):
                    break
                state = next_state

            elif state.phase == Phase.GREEN_PROPOSES:
                try:
                    green_proposals = await self._green.propose(
                        campaign_data=campaign_data,
                        wiki_context=wiki_context,
                        previous_objections=state.red_objections if state.red_objections else None,
                    )
                except Exception:
                    break
                next_state = self._state_machine.record_proposals(state, green_proposals)
                if not isinstance(next_state, DebateState):
                    break
                state = next_state
                next_state = self._state_machine.advance_phase(state)
                if not isinstance(next_state, DebateState):
                    break
                state = next_state

            elif state.phase == Phase.RED_CHALLENGES:
                try:
                    red_objections = await self._red.challenge(
                        green_proposals=state.green_proposals,
                        campaign_data=campaign_data,
                        wiki_context=wiki_context,
                    )
                except Exception:
                    break
                next_state = self._state_machine.record_objections(state, red_objections)
                if not isinstance(next_state, DebateState):
                    break
                state = next_state
                next_state = self._state_machine.advance_phase(state)
                if not isinstance(next_state, DebateState):
                    break
                state = next_state

            elif state.phase == Phase.COORDINATOR_EVALUATES:
                try:
                    new_state = await self._coordinator.evaluate(
                        state=state,
                        campaign_data=campaign_data,
                        wiki_context=wiki_context,
                    )
                except Exception:
                    break
                if not isinstance(new_state, DebateState):
                    break
                if new_state.phase == Phase.CONSENSUS_LOCKED:
                    self._state_machine.save(new_state)
                    return new_state
                if new_state.phase == Phase.PENDING_MANUAL_REVIEW:
                    self._state_machine.save(new_state)
                    return new_state
                # CONTINUE_DEBATE or COMPROMISE_PROPOSED — loop again
                self._state_machine.save(new_state)
                try:
                    new_round = int(new_state.round_number)
                except (AttributeError, TypeError, ValueError):
                    new_round = 0
                if new_round >= max_rounds:
                    return new_state
                state = new_state

            else:
                break

        return state