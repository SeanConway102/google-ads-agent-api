"""
Green Team Agent — proposes optimizations for Google Ads campaigns.

Green Team's role is to analyze performance data and wiki research,
then propose specific, actionable changes. Proposals are challenged
by Red Team in the adversarial loop.

When HITL is enabled and a proposal is above threshold, it is held
for email approval instead of auto-executing.
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

    # ─── HITL routing ─────────────────────────────────────────────────────────

    async def route_proposals(
        self,
        proposals: list[dict[str, Any]],
        campaign: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Route each proposal to either HITL approval or auto-execution.

        Above-threshold proposals with hitl_enabled=true are routed to HITL.
        Below-threshold proposals, or HITL disabled, go directly to auto-execution.

        Args:
            proposals: List of Green Team proposal dicts
            campaign: Full campaign record from the database

        Returns:
            Tuple of (needs_approval_proposals, auto_execute_proposals)
        """
        from src.services.impact_assessor import should_require_approval
        from src.services.email_service import send_proposal_email

        needs_approval: list[dict[str, Any]] = []
        auto_execute: list[dict[str, Any]] = []

        for proposal in proposals:
            ptype = proposal.get("type", "")
            hitl_needed = should_require_approval(
                proposal_type=ptype,
                current_value=proposal.get("current_value"),
                proposed_value=proposal.get("proposed_value"),
                count=proposal.get("count"),
            )

            if hitl_needed and campaign.get("hitl_enabled"):
                needs_approval.append(proposal)
                # Create HITL proposal record in DB
                await self._create_hitl_proposal(proposal, campaign)
                # Send approval email
                await self._send_proposal_email_for(proposal, campaign)
            else:
                auto_execute.append(proposal)

        return needs_approval, auto_execute

    async def _create_hitl_proposal(
        self,
        proposal: dict[str, Any],
        campaign: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a HITL proposal record in the database."""
        from uuid import UUID
        from src.db.postgres_adapter import PostgresAdapter
        from src.services.email_service import send_proposal_email

        adapter = PostgresAdapter()
        row = adapter.execute_returning(
            """INSERT INTO hitl_proposals
               (campaign_id, proposal_type, impact_summary, reasoning, status)
               VALUES (%s, %s, %s, %s, 'pending')
               RETURNING *""",
            (
                str(campaign["id"]),
                proposal.get("type", "unknown"),
                proposal.get("impact_summary", proposal.get("change", "")) or "",
                proposal.get("reasoning", proposal.get("evidence", "")) or "",
            ),
        )
        return dict(row)

    async def _send_proposal_email_for(
        self,
        proposal: dict[str, Any],
        campaign: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a proposal approval email for a single proposal."""
        from src.services.email_service import send_proposal_email
        from src.config import get_settings

        settings = get_settings()
        owner_email = campaign.get("owner_email") or settings.HITL_DEFAULT_EMAIL
        if not owner_email:
            return {"id": "no_emailConfigured"}

        return send_proposal_email(
            to_email=owner_email,
            campaign_name=campaign.get("name", "Unknown Campaign"),
            proposal_type=proposal.get("type", "unknown"),
            impact_summary=proposal.get("impact_summary", proposal.get("change", "")) or "",
            reasoning=(proposal.get("reasoning") or "")[:300],
        )
