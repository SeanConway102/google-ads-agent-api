"""
Campaign CRUD routes — GET /campaigns, POST /campaigns, GET /campaigns/{id}, DELETE /campaigns/{id}.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status

from src.api.schemas import CampaignCreate, CampaignListResponse, CampaignResponse, CampaignStatus
from src.db.postgres_adapter import PostgresAdapter

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


def _campaign_to_response(row: dict) -> CampaignResponse:
    """Convert a DB row dict to a CampaignResponse Pydantic model."""
    return CampaignResponse(
        id=row["id"],
        campaign_id=row["campaign_id"],
        customer_id=row["customer_id"],
        name=row["name"],
        status=CampaignStatus(row["status"]),
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Campaign with ID {body.campaign_id!r} already exists",
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
    """Delete a campaign by its UUID. Returns 204 even if not found."""
    _adapter().delete_campaign(campaign_id)
