"""
Campaign CRUD routes — GET /campaigns, POST /campaigns, GET /campaigns/{id}, DELETE /campaigns/{id}.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status

from src.api.schemas import (
    ActionPayload,
    ApproveResponse,
    CampaignCreate,
    CampaignInsights,
    CampaignListResponse,
    CampaignResponse,
    CampaignStatus,
    CampaignType,
    CampaignUpdate,
    OverrideResponse,
)
from src.agents.debate_state import Phase
from src.db.postgres_adapter import PostgresAdapter
from src.mcp.capability_guard import CapabilityDenied, CapabilityGuard
from src.mcp.google_ads_client import GoogleAdsClient
from src.services.webhook_service import WebhookService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


def _campaign_to_response(row: dict) -> CampaignResponse:
    """Convert a DB row dict to a CampaignResponse Pydantic model."""
    try:
        campaign_status = CampaignStatus(row["status"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Campaign has unknown status: {row['status']!r}",
        )

    # Convert campaign_type string to enum; None is allowed
    campaign_type_val = None
    if row.get("campaign_type") is not None:
        try:
            campaign_type_val = CampaignType(row["campaign_type"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Campaign has unknown campaign_type: {row['campaign_type']!r}",
            )

    return CampaignResponse(
        id=row["id"],
        campaign_id=row["campaign_id"],
        customer_id=row["customer_id"],
        name=row["name"],
        status=campaign_status,
        campaign_type=campaign_type_val,
        owner_tag=row.get("owner_tag"),
        created_at=row["created_at"],
        last_synced_at=row.get("last_synced_at"),
        last_reviewed_at=row.get("last_reviewed_at"),
        hitl_enabled=row.get("hitl_enabled", False),
        owner_email=row.get("owner_email"),
        hitl_threshold=row.get("hitl_threshold", "budget>20pct,keyword_add>5"),
    )


@router.get("", response_model=CampaignListResponse)
def list_campaigns() -> CampaignListResponse:
    """List all campaigns, ordered by creation date descending."""
    rows = _adapter().list_campaigns()
    return CampaignListResponse(
        campaigns=[_campaign_to_response(row) for row in rows],
        total=len(rows),
    )


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(body: CampaignCreate) -> CampaignResponse:
    """Register a new Google Ads campaign in the system."""
    try:
        row = _adapter().create_campaign(body.model_dump())
    except Exception as exc:
        error_msg = str(exc)
        if "UNIQUE constraint" in error_msg or "duplicate key" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Campaign with ID {body.campaign_id!r} already exists",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while creating campaign",
        ) from exc
    WebhookService().dispatch("campaign_created", {
        "id": str(row["id"]),
        "campaign_id": row["campaign_id"],
        "customer_id": row["customer_id"],
        "name": row["name"],
    })
    return _campaign_to_response(row)


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: Annotated[UUID, Path(description="Campaign UUID")]) -> CampaignResponse:
    """Get a single campaign by its UUID."""
    row = _adapter().get_campaign(campaign_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return _campaign_to_response(row)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: Annotated[UUID, Path(description="Campaign UUID")]) -> None:
    """Delete a campaign by its UUID. Returns 204 if deleted, 404 if not found."""
    row = _adapter().get_campaign(campaign_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    _adapter().delete_campaign(campaign_id)
    WebhookService().dispatch("campaign_deleted", {
        "id": str(row["id"]),
        "campaign_id": row["campaign_id"],
        "customer_id": row["customer_id"],
        "name": row["name"],
    })


@router.patch("/{campaign_id}", response_model=CampaignResponse)
def update_campaign(
    campaign_id: Annotated[UUID, Path(description="Campaign UUID")],
    body: CampaignUpdate,
) -> CampaignResponse:
    """Update mutable campaign fields. Currently supports HITL settings."""
    row = _adapter().get_campaign(campaign_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # Build dynamic UPDATE
    updates = {}
    if body.hitl_enabled is not None:
        updates["hitl_enabled"] = body.hitl_enabled
    if body.owner_email is not None:
        updates["owner_email"] = body.owner_email
    if body.hitl_threshold is not None:
        updates["hitl_threshold"] = body.hitl_threshold

    if updates:
        set_clauses = ", ".join(f"{k} = %s" for k in updates)
        values = tuple(updates.values())
        _adapter().execute(
            f"UPDATE campaigns SET {set_clauses}, updated_at = NOW() WHERE id = %s",
            values + (str(campaign_id),),
        )

    # Re-fetch and return updated row
    updated_row = _adapter().get_campaign(campaign_id)
    return _campaign_to_response(updated_row)


@router.get("/{campaign_id}/insights", response_model=CampaignInsights)
def get_campaign_insights(
    campaign_id: Annotated[UUID, Path(description="Campaign UUID")],
) -> CampaignInsights:
    """
    Get current optimization insights for a campaign.

    Returns the campaign data along with the latest debate state:
    green proposals, red objections, phase, and round number.
    Returns null debate fields if no debate has run yet.
    """
    row = _adapter().get_campaign(campaign_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    debate_row = _adapter().get_latest_debate_state_any_cycle(campaign_id)

    try:
        campaign_status = CampaignStatus(row["status"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Campaign has unknown status: {row['status']!r}",
        )

    return CampaignInsights(
        id=row["id"],
        campaign_id=row["campaign_id"],
        customer_id=row["customer_id"],
        name=row["name"],
        status=campaign_status,
        campaign_type=row["campaign_type"],
        owner_tag=row.get("owner_tag"),
        created_at=row["created_at"],
        last_synced_at=row.get("last_synced_at"),
        last_reviewed_at=row.get("last_reviewed_at"),
        phase=str(debate_row["phase"]) if debate_row else None,
        round_number=int(debate_row["round_number"]) if debate_row and debate_row.get("round_number") is not None else None,
        green_proposals=debate_row["green_proposals"] if debate_row else None,
        red_objections=debate_row["red_objections"] if debate_row else None,
        coordinator_decision=debate_row.get("coordinator_decision") if debate_row else None,
        consensus_reached=bool(debate_row["consensus_reached"]) if debate_row else None,
    )


@router.post("/{campaign_id}/approve", response_model=ApproveResponse)
def approve_campaign_action(
    campaign_id: Annotated[UUID, Path(description="Campaign UUID")],
) -> ApproveResponse:
    """
    Mark a pending agent action as approved (human-in-the-loop checkpoint).

    Only works when the campaign's debate state is in PENDING_MANUAL_REVIEW phase.
    Transitions the debate state to operator-approved and executes allowed proposals.
    Returns 404 if the campaign doesn't exist or has no pending action.
    """
    row = _adapter().get_campaign(campaign_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    debate_row = _adapter().get_latest_debate_state_any_cycle(campaign_id)
    if debate_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending action to approve for this campaign",
        )
    try:
        phase = Phase(debate_row["phase"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending action to approve for this campaign",
        )
    if phase != Phase.PENDING_MANUAL_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending action to approve for this campaign",
        )

    # Execute approved proposals FIRST, transition phase ONLY if all succeed.
    # If any proposal is blocked by CapabilityGuard or raises from gads_client,
    # the phase stays PENDING_MANUAL_REVIEW and the operator is notified.
    guard = CapabilityGuard()
    gads_client = GoogleAdsClient(customer_id=row["customer_id"])
    blocked_proposals = []
    executed_proposals = []
    execution_error = None

    for proposal in (debate_row.get("green_proposals") or []):
        ptype = proposal.get("type", "")
        try:
            if ptype == "keyword_add":
                guard.check("google_ads.add_keywords")
                gads_client.add_keywords(
                    customer_id=row["customer_id"],
                    ad_group_id=proposal.get("ad_group_id", ""),
                    keywords=proposal.get("keywords", []),
                )
                executed_proposals.append(ptype)
            elif ptype == "keyword_remove":
                guard.check("google_ads.remove_keywords")
                gads_client.remove_keywords(
                    customer_id=row["customer_id"],
                    keyword_resource_names=proposal.get("resource_names", []),
                )
                executed_proposals.append(ptype)
            elif ptype == "bid_update":
                guard.check("google_ads.update_keyword_bids")
                gads_client.update_keyword_bids(
                    customer_id=row["customer_id"],
                    updates=proposal.get("updates", []),
                )
                executed_proposals.append(ptype)
            elif ptype == "match_type_update":
                guard.check("google_ads.update_keyword_match_types")
                gads_client.update_keyword_match_types(
                    customer_id=row["customer_id"],
                    updates=proposal.get("updates", []),
                )
                executed_proposals.append(ptype)
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unknown proposal type: {ptype!r}",
                )
        except CapabilityDenied:
            blocked_proposals.append(ptype)
        except HTTPException:
            raise
        except Exception as exc:
            execution_error = exc
            break

    # If execution failed, do NOT transition to APPROVED — operator must retry
    if execution_error is not None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Google Ads execution failed: {execution_error}",
        )

    # If ANY proposals were blocked, return 403 — partial execution is not approved.
    # The operator must review and retry with adjusted capabilities.
    if blocked_proposals:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Action blocked by capability guard: {blocked_proposals}. "
                   f"{len(executed_proposals)} proposal(s) executed, {len(blocked_proposals)} blocked.",
        )

    # Only transition to APPROVED after all proposals execute successfully
    updated = dict(debate_row)
    updated["phase"] = Phase.APPROVED.value
    _adapter().save_debate_state(updated)

    return ApproveResponse(status="approved", campaign_id=campaign_id)


@router.post("/{campaign_id}/override", response_model=OverrideResponse)
def override_campaign_action(
    campaign_id: Annotated[UUID, Path(description="Campaign UUID")],
    body: ActionPayload,
) -> OverrideResponse:
    """
    Force a direct action on a campaign bypassing the adversarial debate.

    Executes the action via MCP capability guard and writes manual_override to audit_log.
    Does NOT invoke green/red team debate.
    For emergency use only.
    """
    row = _adapter().get_campaign(campaign_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # Attempt execution via MCP guard first — fail before auditing if blocked
    guard = CapabilityGuard()
    gads_client = GoogleAdsClient(customer_id=row["customer_id"])
    try:
        if body.action_type == "keyword_add":
            guard.check("google_ads.add_keywords")
            gads_client.add_keywords(
                customer_id=row["customer_id"],
                ad_group_id=body.ad_group_id or "",
                keywords=body.keywords or [],
            )
        elif body.action_type == "keyword_remove":
            guard.check("google_ads.remove_keywords")
            gads_client.remove_keywords(
                customer_id=row["customer_id"],
                keyword_resource_names=body.keywords or [],
            )
        elif body.action_type == "bid_update":
            guard.check("google_ads.update_keyword_bids")
            gads_client.update_keyword_bids(
                customer_id=row["customer_id"],
                updates=body.updates or [],
            )
        elif body.action_type == "match_type_update":
            guard.check("google_ads.update_keyword_match_types")
            gads_client.update_keyword_match_types(
                customer_id=row["customer_id"],
                updates=body.updates or [],
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown action type: {body.action_type!r}",
            )
    except CapabilityDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Action {body.action_type!r} is not allowed by capability guard",
        )

    audit_row = _adapter().write_audit_log({
        "cycle_date": "",
        "campaign_id": campaign_id,
        "action_type": "manual_override",
        "target": {
            "campaign_name": row["name"],
            "campaign_id": row["campaign_id"],
            "action_type": body.action_type,
        },
        "green_proposal": {
            "type": body.action_type,
            "keywords": body.keywords,
            "bid_adjustment": body.bid_adjustment,
            "ad_group_id": body.ad_group_id,
        },
        "red_objections": [],
        "coordinator_note": "Manual override by api-operator",
        "debate_rounds": 0,
    })

    return OverrideResponse(status="override_applied", audit_id=audit_row["id"])
