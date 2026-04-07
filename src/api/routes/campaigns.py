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
    OverrideResponse,
)
from src.agents.debate_state import Phase
from src.db.postgres_adapter import PostgresAdapter

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
    return CampaignResponse(
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
    Transitions the debate state to operator-approved.
    Returns 404 if the campaign doesn't exist or has no pending action.
    """
    row = _adapter().get_campaign(campaign_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    debate_row = _adapter().get_latest_debate_state_any_cycle(campaign_id)
    if debate_row is None or Phase(debate_row["phase"]) != Phase.PENDING_MANUAL_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending action to approve for this campaign",
        )

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

    Writes directly to audit_log with action_type 'manual_override'.
    Does NOT invoke green/red team debate or modify debate_state.
    For emergency use only.
    """
    row = _adapter().get_campaign(campaign_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

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
