"""
Red Team Agent — challenges and validates Green Team proposals.

Red Team's role is adversarial quality control: find flaws, missing context,
and counter-evidence. Approves solid proposals. Objects to risky or
unsupported ones with specific suggested fixes.
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Optional

from src.agents.prompts import RED_TEAM_SYSTEM_PROMPT

if TYPE_CHECKING:
    from src.llm.adapter import LLMProvider


class RedTeamAgent:
    """
    Red Team Agent — challenges proposals.

    Reviews Green proposals against performance data and wiki research,
    identifies flaws and risks, and suggests revisions.
    """

    def __init__(self, llm: Optional[LLMProvider] = None) -> None:
        self._llm = llm

    async def challenge(
        self,
        green_proposals: list[dict[str, Any]],
        campaign_data: dict[str, Any],
        wiki_context: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Challenge Green Team's proposals.

        Args:
            green_proposals: Proposals from Green Team to review
            campaign_data: Current campaign performance data
            wiki_context: Relevant wiki research

        Returns:
            List of assessment dicts with verdict, objections, and reasoning
        """
        from src.llm.adapter import Message

        messages = [
            Message(role="system", content=RED_TEAM_SYSTEM_PROMPT),
            Message(role="user", content=self._build_context(green_proposals, campaign_data, wiki_context)),
        ]

        if self._llm is not None:
            response_obj = await self._llm.chat_completion(messages=messages)
        else:
            from src.llm.adapter import chat_completion
            response_obj = await chat_completion(messages=messages)

        if response_obj is None or not response_obj.choices:
            raise RuntimeError("LLM returned empty response")
        first_choice = response_obj.choices[0]
        if not hasattr(first_choice, "message") or first_choice.message is None:
            raise RuntimeError("LLM returned choice with no message")
        response_text = first_choice.message.content
        if response_text is None:
            raise RuntimeError("LLM returned None content")
        return self._parse_response(response_text)

    def _build_context(
        self,
        green_proposals: list[dict[str, Any]],
        campaign_data: dict[str, Any],
        wiki_context: list[dict[str, Any]],
    ) -> str:
        lines = ["## Green Team Proposals\n", json.dumps(green_proposals, indent=2, default=str)]
        lines.append("\n## Campaign Performance Data\n")
        lines.append(json.dumps(campaign_data, indent=2, default=str))
        lines.append("\n## Wiki Research\n")
        for entry in wiki_context[:5]:
            lines.append(f"### {entry.get('title', 'Untitled')}\n{entry.get('content', '')[:300]}")
        lines.append("\n\nProvide your verdict and objections as a JSON array of assessment objects.")
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
