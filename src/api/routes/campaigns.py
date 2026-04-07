"""
Campaign CRUD routes — GET /campaigns, POST /campaigns, GET /campaigns/{id}, DELETE /campaigns/{id}.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status

from src.api.schemas import (
    CampaignCreate,
    CampaignInsights,
    CampaignListResponse,
    CampaignResponse,
    CampaignStatus,
)
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
        round_number=int(debate_row["round_number"]) if debate_row else None,
        green_proposals=debate_row["green_proposals"] if debate_row else None,
        red_objections=debate_row["red_objections"] if debate_row else None,
        coordinator_decision=debate_row.get("coordinator_decision") if debate_row else None,
        consensus_reached=bool(debate_row["consensus_reached"]) if debate_row else None,
    )
