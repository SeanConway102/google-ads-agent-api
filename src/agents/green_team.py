"""
Green Team Agent — proposes optimizations for Google Ads campaigns.

Green Team's role is to analyze performance data and wiki research,
then propose specific, actionable changes. Proposals are challenged
by Red Team in the adversarial loop.
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Optional

from src.agents.prompts import GREEN_TEAM_SYSTEM_PROMPT

if TYPE_CHECKING:
    from src.llm.adapter import LLMProvider


class GreenTeamAgent:
    """
    Green Team Agent — proposes optimizations.

    Analyzes campaign data and wiki research, proposes actionable
    keyword/bid/match-type changes, and revises based on Red objections.
    """

    def __init__(self, llm: Optional[LLMProvider] = None) -> None:
        self._llm = llm

    async def propose(
        self,
        campaign_data: dict[str, Any],
        wiki_context: list[dict[str, Any]],
        previous_objections: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """
        Generate optimization proposals based on campaign data and wiki research.

        Args:
            campaign_data: Performance metrics (clicks, ctr, spend, conversions, etc.)
            wiki_context: Relevant wiki research entries
            previous_objections: Red Team's objections from prior round (if revising)

        Returns:
            List of proposal dicts with keys: type, target, change, priority, reasoning, evidence
        """
        from src.llm.adapter import Message

        messages = [
            Message(role="system", content=GREEN_TEAM_SYSTEM_PROMPT),
            Message(role="user", content=self._build_context(campaign_data, wiki_context, previous_objections or [])),
        ]

        if self._llm is not None:
            response_obj = await self._llm.chat_completion(messages=messages)
        else:
            from src.llm.adapter import chat_completion
            response_obj = await chat_completion(messages=messages)

        response_text = response_obj.choices[0].message.content
        return self._parse_response(response_text)

    def _build_context(
        self,
        campaign_data: dict[str, Any],
        wiki_context: list[dict[str, Any]],
        previous_objections: list[dict[str, Any]],
    ) -> str:
        lines = ["## Campaign Performance Data\n", json.dumps(campaign_data, indent=2, default=str)]
        lines.append("\n## Relevant Wiki Research\n")
        for entry in wiki_context:
            lines.append(f"### {entry.get('title', 'Untitled')}\n{entry.get('content', '')[:500]}")
        if previous_objections:
            lines.append("\n## Red Team's Previous Objections (must address these)\n")
            lines.append(json.dumps(previous_objections, indent=2, default=str))
        lines.append("\n\nProvide your proposals as a JSON array of proposal objects.")
        return "\n".join(lines)

    def _parse_response(self, response: str) -> list[dict[str, Any]]:
        """Extract JSON array from LLM response."""
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return [{"type": "raw", "content": response}]
