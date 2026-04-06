"""
Webhook routes — register, list, delete webhook subscriptions.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status

from src.api.schemas import WebhookRegister, WebhookResponse, WebhookEvent
from src.db.postgres_adapter import PostgresAdapter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


def _webhook_to_response(row: dict) -> WebhookResponse:
    """Convert a DB row dict to a WebhookResponse Pydantic model."""
    return WebhookResponse(
        id=row["id"],
        url=row["url"],
        events=[WebhookEvent(e) for e in row.get("events", [])],
        active=row.get("active", True),
        created_at=row["created_at"],
    )


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
def register_webhook(body: WebhookRegister) -> WebhookResponse:
    """Register a new webhook subscription for agent events."""
    row = _adapter().register_webhook(body.model_dump())
    return _webhook_to_response(row)


@router.get("", response_model=list[WebhookResponse])
def list_webhooks() -> list[WebhookResponse]:
    """List all active webhook subscriptions."""
    rows = _adapter().list_webhooks()
    return [_webhook_to_response(row) for row in rows]


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(webhook_id: Annotated[UUID, Path(description="Webhook UUID")]) -> None:
    """Delete a webhook subscription. Returns 404 if not found."""
    rows = _adapter().list_webhooks()
    if not any(row["id"] == webhook_id for row in rows):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    _adapter().delete_webhook(webhook_id)
