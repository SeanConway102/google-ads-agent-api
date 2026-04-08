"""
HITL proposal routes — list proposals and manually decide on them.
GET /campaigns/{uuid}/hitl/proposals
POST /campaigns/{uuid}/hitl/proposals/{proposal_id}/decide
"""
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status

from src.api.schemas import (
    HitlProposalResponse,
    HitlDecisionRequest,
    HitlDecisionResponse,
)
from src.db.postgres_adapter import PostgresAdapter

router = APIRouter(prefix="/campaigns/{campaign_id}/hitl", tags=["hitl"])


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


def _proposal_to_response(row: dict) -> HitlProposalResponse:
    """Convert a DB row dict to a HitlProposalResponse Pydantic model."""
    return HitlProposalResponse(
        id=row["id"],
        campaign_id=row["campaign_id"],
        proposal_type=row["proposal_type"],
        impact_summary=row["impact_summary"],
        reasoning=row["reasoning"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        decided_at=row.get("decided_at"),
        replier_response=row.get("replier_response"),
    )


@router.get("/proposals", response_model=list[HitlProposalResponse])
def list_hitl_proposals(
    campaign_id: Annotated[UUID, Path(description="Campaign UUID")],
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status (pending, approved, rejected, expired)"),
) -> list[HitlProposalResponse]:
    """List HITL proposals for a campaign, optionally filtered by status."""
    adapter = _adapter()
    campaign = adapter.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if not campaign.get("hitl_enabled"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HITL is not enabled for this campaign",
        )

    rows = adapter.list_hitl_proposals(campaign_id, status=status_filter)
    return [_proposal_to_response(row) for row in rows]


@router.get("/proposals/{proposal_id}", response_model=HitlProposalResponse)
def get_hitl_proposal(
    campaign_id: Annotated[UUID, Path(description="Campaign UUID")],
    proposal_id: Annotated[UUID, Path(description="Proposal UUID")],
) -> HitlProposalResponse:
    """Get a single HITL proposal by ID."""
    adapter = _adapter()
    campaign = adapter.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if not campaign.get("hitl_enabled"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HITL is not enabled for this campaign",
        )

    row = adapter.get_hitl_proposal(proposal_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if str(row["campaign_id"]) != str(campaign_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found for this campaign")

    return _proposal_to_response(row)


@router.post("/proposals/{proposal_id}/decide", response_model=HitlDecisionResponse)
def decide_hitl_proposal(
    campaign_id: Annotated[UUID, Path(description="Campaign UUID")],
    proposal_id: Annotated[UUID, Path(description="Proposal UUID")],
    body: HitlDecisionRequest,
) -> HitlDecisionResponse:
    """
    Manually decide a HITL proposal (approve or reject).
    Updates the proposal status and records the replier response.
    """
    adapter = _adapter()
    campaign = adapter.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if not campaign.get("hitl_enabled"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HITL is not enabled for this campaign",
        )

    row = adapter.get_hitl_proposal(proposal_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if str(row["campaign_id"]) != str(campaign_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found for this campaign")

    if row["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Proposal is already {row['status']}, not pending",
        )

    if body.decision not in ("approved", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Decision must be 'approved' or 'rejected'",
        )

    updated_row = adapter.update_hitl_proposal_status(
        proposal_id=proposal_id,
        status=body.decision,
        replier_response=body.notes,
    )
    return HitlDecisionResponse(
        id=updated_row["id"],
        status=updated_row["status"],
        decided_at=updated_row.get("decided_at"),
    )
