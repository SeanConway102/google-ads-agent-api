"""
Research trigger routes — manual research cycle activation.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status

from src.api.schemas import TriggerResponse
from src.cron.daily_research import run_daily_research
from src.db.postgres_adapter import PostgresAdapter

router = APIRouter(prefix="/research", tags=["research"])


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


@router.post(
    "/trigger",
    response_model=TriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_research_cycle(
    campaign_id: Annotated[UUID | None, Query(description="Campaign UUID to run (omit for all)")] = None,
) -> TriggerResponse:
    """
    Manually trigger the research cycle.

    Omit campaign_id to run all active campaigns.
    Provide campaign_id to run a single campaign.
    Returns immediately — research runs asynchronously.
    """
    if campaign_id is not None:
        # Verify the campaign exists
        row = _adapter().get_campaign(campaign_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {campaign_id} not found",
            )

    # Run the research cycle (async — returns immediately)
    run_daily_research(target_campaign_id=str(campaign_id) if campaign_id else None)

    return TriggerResponse(
        status="triggered",
        campaign_id=str(campaign_id) if campaign_id else None,
    )
