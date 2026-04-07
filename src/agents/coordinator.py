"""
Coordinator Agent — orchestrates the three-agent adversarial debate loop.

The Coordinator receives Green proposals + Red objections, evaluates consensus,
and drives the state machine through its phases.
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Optional

from src.agents.debate_state import DebateState, Phase
from src.agents.prompts import COORDINATOR_SYSTEM_PROMPT
from src.config import get_settings

if TYPE_CHECKING:
    from src.llm.adapter import LLMProvider


class CoordinatorAgent:
    """
    Coordinator Agent — decides consensus, escalation, or continuation.

    Reads Green proposals and Red objections from the DebateState,
    queries the LLM for a verdict, and applies the decision to the state.
    """

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        max_rounds: int | None = None,
    ) -> None:
        self._llm = llm
        self._max_rounds = max_rounds  # resolved lazily in evaluate()

    def _resolve_max_rounds(self) -> int:
        if self._max_rounds is not None:
            return self._max_rounds
        return get_settings().MAX_DEBATE_ROUNDS

    async def evaluate(
        self,
        state: DebateState,
        campaign_data: dict[str, Any],
        wiki_context: list[dict[str, Any]],
    ) -> DebateState:
        """
        Evaluate the current debate and return an updated state.

        Calls the LLM with the full context, parses the verdict tag,
        and applies the decision to the state.
        """
        from src.llm.adapter import Message

        messages = [
            Message(role="system", content=COORDINATOR_SYSTEM_PROMPT),
            Message(role="user", content=self._build_context(state, campaign_data, wiki_context)),
        ]

        if self._llm is not None:
            response_obj = await self._llm.chat_completion(messages=messages)
        else:
            from src.llm.adapter import chat_completion
            response_obj = await chat_completion(messages=messages)
        response_text = response_obj.choices[0].message.content
        decision = self._parse_decision(response_text)
        return self._apply_decision(state, decision)

    def _build_context(
        self,
        state: DebateState,
        campaign_data: dict[str, Any],
        wiki_context: list[dict[str, Any]],
    ) -> str:
        context: dict[str, Any] = {
            "round": state.round_number,
            "max_rounds": self._resolve_max_rounds(),
            "phase": state.phase.value,
            "green_proposals": state.green_proposals,
            "red_objections": state.red_objections,
            "campaign_data_summary": campaign_data,
            "wiki_entries_used": [e.get("id") for e in wiki_context[:5]],
        }
        return json.dumps(context, indent=2, default=str)

    def _parse_decision(self, response: str) -> dict[str, Any]:
        """Extract verdict tag and compromise from LLM response."""
        verdict_match = re.search(
            r'\[(CONTINUE_DEBATE|CONSENSUS_REACHED|COMPROMISE_PROPOSED|ESCALATE)\]',
            response,
        )
        verdict = verdict_match.group(1).lower() if verdict_match else "continue_debate"
        compromise_match = re.search(r'\[COMPROMISE_PROPOSED\]\s*(.+)', response, re.DOTALL)
        compromise = compromise_match.group(1).strip() if compromise_match else None
        return {
            "verdict": verdict,
            "raw_response": response,
            "compromise": compromise,
        }

    def _apply_decision(self, state: DebateState, decision: dict[str, Any]) -> DebateState:
        verdict = decision["verdict"]
        if verdict == "consensus_reached":
            state.consensus_reached = True
            state.phase = Phase.CONSENSUS_LOCKED
        elif verdict == "compromise_proposed":
            state.compromise_proposed = True
            state.phase = Phase.GREEN_PROPOSES
        elif verdict == "escalate":
            state.phase = Phase.PENDING_MANUAL_REVIEW
        else:
            # continue_debate or unknown — increment round, return to green
            state.round_number += 1
            state.phase = Phase.GREEN_PROPOSES
        state.coordinator_decision = decision
        return state
