"""
Wiki routes — search, create, get, invalidate.
"""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from uuid import UUID

from src.api.schemas import (
    WikiEntryCreate,
    WikiEntryResponse,
    WikiSearchResponse,
)
from src.db.postgres_adapter import PostgresAdapter

router = APIRouter(prefix="/wiki", tags=["wiki"])


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


def _entry_to_response(row: dict) -> WikiEntryResponse:
    """Convert a DB row dict to a WikiEntryResponse Pydantic model."""
    return WikiEntryResponse(
        id=row["id"],
        title=row["title"],
        slug=row["slug"],
        content=row["content"],
        sources=row.get("sources", []),
        green_rationale=row.get("green_rationale"),
        red_objections=row.get("red_objections", []),
        consensus_note=row.get("consensus_note"),
        tags=row.get("tags", []),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        verified_at=row.get("verified_at"),
        invalidated_at=row.get("invalidated_at"),
    )


@router.get("/search", response_model=WikiSearchResponse)
def search_wiki(
    query: Annotated[str, Query(min_length=1, description="Search query")],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> WikiSearchResponse:
    """
    Full-text search wiki entries using PostgreSQL tsvector.
    Returns entries ordered by relevance (ts_rank).
    """
    rows = _adapter().search_wiki(query, limit=limit)
    entries = [_entry_to_response(row) for row in rows]
    return WikiSearchResponse(entries=entries, query=query, limit=limit)


@router.post("", response_model=WikiEntryResponse, status_code=status.HTTP_201_CREATED)
def create_wiki_entry(body: WikiEntryCreate) -> WikiEntryResponse:
    """Create a new wiki entry from validated research."""
    row = _adapter().create_wiki_entry(body.model_dump())
    return _entry_to_response(row)


@router.get("/{entry_id}", response_model=WikiEntryResponse)
def get_wiki_entry(entry_id: Annotated[UUID, Path(description="Wiki entry UUID")]) -> WikiEntryResponse:
    """Get a wiki entry by UUID."""
    row = _adapter().get_wiki_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wiki entry not found")
    return _entry_to_response(row)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def invalidate_wiki_entry(
    entry_id: Annotated[UUID, Path(description="Wiki entry UUID")],
    reason: Annotated[str, Query(min_length=1, description="Reason for invalidation")],
) -> None:
    """Invalidate a wiki entry (soft-delete — preserves audit trail)."""
    row = _adapter().get_wiki_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wiki entry not found")
    _adapter().invalidate_wiki_entry(entry_id, reason)
