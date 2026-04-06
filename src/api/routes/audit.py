"""
Audit log routes — query audit log with filters.
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Query
from uuid import UUID

from src.api.schemas import AuditLogResponse, AuditAction
from src.db.postgres_adapter import PostgresAdapter

router = APIRouter(prefix="/audit", tags=["audit"])


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


@router.get("", response_model=list[AuditLogResponse])
def query_audit_log(
    campaign_id: Annotated[Optional[UUID], Query(description="Filter by campaign UUID")] = None,
    action_type: Annotated[Optional[str], Query(description="Filter by action type")] = None,
    cycle_date: Annotated[Optional[str], Query(description="Filter by cycle date (YYYY-MM-DD)")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[AuditLogResponse]:
    """
    Query the audit log with optional filters.
    Returns entries ordered by performed_at descending.
    """
    rows = _adapter().query_audit_log(
        campaign_id=campaign_id,
        action_type=action_type,
        cycle_date=cycle_date,
        limit=limit,
    )
    return [_audit_to_response(row) for row in rows]


def _audit_to_response(row: dict) -> AuditLogResponse:
    """Convert a DB row dict to an AuditLogResponse Pydantic model."""
    return AuditLogResponse(
        id=row["id"],
        cycle_date=row.get("cycle_date"),
        campaign_id=row.get("campaign_id"),
        action_type=AuditAction(row["action_type"]),
        target=row.get("target"),
        green_proposal=row.get("green_proposal"),
        red_objections=row.get("red_objections"),
        coordinator_note=row.get("coordinator_note"),
        debate_rounds=row.get("debate_rounds"),
        performed_at=row["performed_at"],
    )
