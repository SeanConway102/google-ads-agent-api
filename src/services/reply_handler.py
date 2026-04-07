"""
Reply Handler — parses inbound email replies and persists question replies.

Interpretation:
  - "approve", "yes", "sounds good", "do it", "go ahead"  → approved
  - "reject", "no", "not this time", "decline", "skip"       → rejected
  - anything else                                             → question (stored in hitl_proposals)
"""
import re
from uuid import UUID

from src.db.postgres_adapter import PostgresAdapter


_APPROVE_PATTERNS = re.compile(
    r"^\s*(approve|yes|yeah|sounds good|sounds great|do it|go ahead|sure|ok|looks good|lgtm)\s*$",
    re.IGNORECASE,
)
_REJECT_PATTERNS = re.compile(
    r"^\s*(reject|no|not this time|decline|skip|not now|don.?t)\s*$",
    re.IGNORECASE,
)


def parse_reply(body: str) -> str:
    """
    Parse the email body and return: 'approved', 'rejected', or 'question'.
    """
    stripped = body.strip()
    if _APPROVE_PATTERNS.match(stripped):
        return "approved"
    if _REJECT_PATTERNS.match(stripped):
        return "rejected"
    return "question"


def handle_inbound_reply(
    from_email: str,
    to_email: str,
    subject: str,
    body: str,
) -> None:
    """
    Handle an inbound email reply from Resend webhook.

    Finds the campaign by owner email, finds pending debate state,
    and routes the reply as approved/rejected/question.
    """
    # Extract the email address from the "from" field (format: "Name <email@domain.com>")
    match = re.search(r"<(.+?)>|^(.+?@.+?)$", from_email)
    if not match:
        print(f"    Warning: malformed from_email discarded: {from_email!r}")
        return
    sender_email = match.group(1) if match.group(1) else match.group(2)

    db = PostgresAdapter()

    # Find campaign by owner email (must have HITL enabled)
    campaign_row = db.get_campaign_by_owner_email(sender_email)
    if not campaign_row or not campaign_row.get("hitl_enabled"):
        return

    # Find pending debate state
    debate_row = db.get_latest_debate_state_any_cycle(campaign_row["id"])
    if not debate_row:
        return

    from src.agents.debate_state import Phase

    try:
        phase = Phase(debate_row.get("phase", ""))
    except ValueError:
        return  # invalid phase in DB — ignore silently

    if phase != Phase.PENDING_MANUAL_REVIEW:
        return

    decision = parse_reply(body)

    if decision == "question":
        db.create_hitl_proposal({
            "campaign_id": campaign_row["id"],
            "proposal_type": "question",
            "impact_summary": body[:200],
            "reasoning": body,
        })
