"""
Email reply webhook — receives inbound email replies from Resend inbound webhook.
Processes owner approve/reject/question responses to HITL proposal emails.
"""
from fastapi import APIRouter, HTTPException, status

from src.api.schemas import EmailReplyPayload, EmailReplyResponse
from src.agents.debate_state import Phase
from src.db.postgres_adapter import PostgresAdapter
from src.mcp.capability_guard import CapabilityGuard
from src.mcp.google_ads_client import GoogleAdsClient
from src.services.webhook_service import dispatch_event

router = APIRouter(prefix="/email-replies", tags=["email_replies"])

# Keywords that constitute an approval response
_APPROVE_WORDS = {"approve", "yes", "sounds good", "sounds great", "go ahead", "do it"}
# Keywords that constitute a rejection response
_REJECT_WORDS = {"reject", "no", "not this time", "not now", "don't"}


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


def _determine_intent(body: str) -> str:
    """
    Classify the reply body as 'approve', 'reject', or 'question'.
    Strips leading/trailing whitespace and does case-insensitive matching.
    """
    text = body.strip().lower()
    # Check for approve signals
    for word in _APPROVE_WORDS:
        if word in text:
            return "approve"
    # Check for reject signals
    for word in _REJECT_WORDS:
        if word in text:
            return "reject"
    # Default: owner is asking a question
    return "question"


@router.post("", response_model=EmailReplyResponse)
def handle_email_reply(body: EmailReplyPayload) -> EmailReplyResponse:
    """
    Receive an inbound email reply from Resend and process the owner's response.

    Parses the reply body to determine intent (approve / reject / question),
    finds the campaign by owner email, and transitions the pending debate state.

    Returns 404 if no matching campaign or no pending proposal.
    Returns 200 for all three intent types (approve, reject, question).
    """
    # Find campaign by owner email
    campaign_row = _adapter().get_campaign_by_owner_email(body.email_from)
    if campaign_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No campaign registered for email address: {body.email_from}",
        )
    if not campaign_row.get("hitl_enabled"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HITL is not enabled for this campaign",
        )

    # Find pending debate state
    debate_row = _adapter().get_latest_debate_state_any_cycle(campaign_row["id"])
    if debate_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending proposal to act on for this campaign",
        )
    try:
        phase = Phase(debate_row.get("phase", ""))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending proposal to act on for this campaign",
        )
    if phase != Phase.PENDING_MANUAL_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending proposal to act on for this campaign",
        )

    intent = _determine_intent(body.body)

    if intent == "approve":
        # Execute approved proposals BEFORE saving APPROVED phase.
        # If execution fails, we must NOT mark the debate as approved —
        # otherwise the owner believes their approval was applied when it wasn't.
        guard = CapabilityGuard()
        gads_client = GoogleAdsClient(customer_id=campaign_row["customer_id"])
        proposals = debate_row.get("green_proposals") or []
        for proposal in proposals:
            ptype = proposal.get("type", "")
            if ptype == "keyword_add":
                guard.check("google_ads.add_keywords")
                gads_client.add_keywords(
                    customer_id=campaign_row["customer_id"],
                    ad_group_id=proposal.get("ad_group_id", ""),
                    keywords=proposal.get("keywords", []),
                )
            elif ptype == "keyword_remove":
                guard.check("google_ads.remove_keywords")
                gads_client.remove_keywords(
                    customer_id=campaign_row["customer_id"],
                    keyword_resource_names=proposal.get("resource_names", []),
                )
            elif ptype == "bid_update":
                guard.check("google_ads.update_keyword_bids")
                gads_client.update_keyword_bids(
                    customer_id=campaign_row["customer_id"],
                    updates=proposal.get("updates", []),
                )
            elif ptype == "match_type_update":
                guard.check("google_ads.update_keyword_match_types")
                gads_client.update_keyword_match_types(
                    customer_id=campaign_row["customer_id"],
                    updates=proposal.get("updates", []),
                )

        # Only mark as approved after all proposals execute successfully
        updated = dict(debate_row)
        updated["phase"] = Phase.APPROVED.value
        _adapter().save_debate_state(updated)

        return EmailReplyResponse(
            status="approved",
            campaign_id=campaign_row["id"],
        )

    elif intent == "reject":
        updated = dict(debate_row)
        updated["phase"] = Phase.REJECTED.value
        _adapter().save_debate_state(updated)
        return EmailReplyResponse(
            status="rejected",
            campaign_id=campaign_row["id"],
        )

    else:
        # intent == "question": fire webhook and return 200 without changing phase
        _dispatch_question_asked(campaign_row, body.body, debate_row.get("green_proposals", []))
        return EmailReplyResponse(
            status="question_asked",
            campaign_id=campaign_row["id"],
        )


def _dispatch_question_asked(campaign_row: dict, question_body: str, proposals: list) -> None:
    """Fire question_asked webhook event to notify operator of owner question."""
    import asyncio

    asyncio.run(dispatch_event(
        event_type="question_asked",
        payload={
            "campaign_id": str(campaign_row["id"]),
            "owner_email": campaign_row.get("owner_email"),
            "question": question_body,
            "proposals": proposals,
        },
    ))
