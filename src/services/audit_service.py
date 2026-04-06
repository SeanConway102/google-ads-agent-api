"""
Audit service — centralizes all audit log writes across the agent system.
Called by agents and routes whenever state changes that must be recorded.
"""
import logging
from datetime import date
from typing import Any
from uuid import UUID

from src.api.schemas import AuditAction
from src.db.postgres_adapter import PostgresAdapter

logger = logging.getLogger(__name__)


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


def log_campaign_created(campaign_id: UUID, target: dict[str, Any]) -> dict:
    """Log a CAMPAIGN_CREATED event."""
    row = _adapter().write_audit_log({
        "cycle_date": date.today().isoformat(),
        "campaign_id": campaign_id,
        "action_type": AuditAction.CAMPAIGN_CREATED.value,
        "target": target,
    })
    logger.info("audit_logged", extra={"action": AuditAction.CAMPAIGN_CREATED.value, "campaign_id": str(campaign_id)})
    return row


def log_campaign_deleted(campaign_id: UUID, target: dict[str, Any]) -> dict:
    """Log a CAMPAIGN_DELETED event."""
    row = _adapter().write_audit_log({
        "cycle_date": date.today().isoformat(),
        "campaign_id": campaign_id,
        "action_type": AuditAction.CAMPAIGN_DELETED.value,
        "target": target,
    })
    logger.info("audit_logged", extra={"action": AuditAction.CAMPAIGN_DELETED.value, "campaign_id": str(campaign_id)})
    return row


def log_wiki_created(wiki_entry_id: UUID, target: dict[str, Any]) -> dict:
    """Log a WIKI_CREATED event."""
    row = _adapter().write_audit_log({
        "cycle_date": date.today().isoformat(),
        "campaign_id": target.get("campaign_id"),
        "action_type": AuditAction.WIKI_CREATED.value,
        "target": target,
    })
    logger.info("audit_logged", extra={"action": AuditAction.WIKI_CREATED.value, "wiki_id": str(wiki_entry_id)})
    return row


def log_wiki_invalidated(wiki_entry_id: UUID, campaign_id: UUID | None = None) -> dict:
    """Log a WIKI_INVALIDATED event."""
    row = _adapter().write_audit_log({
        "cycle_date": date.today().isoformat(),
        "campaign_id": campaign_id,
        "action_type": AuditAction.WIKI_INVALIDATED.value,
        "target": {"wiki_id": str(wiki_entry_id)},
    })
    logger.info("audit_logged", extra={"action": AuditAction.WIKI_INVALIDATED.value, "wiki_id": str(wiki_entry_id)})
    return row


def log_debate_state_saved(
    campaign_id: UUID,
    cycle_date: str,
    green_proposal: dict[str, Any] | None = None,
    red_objections: list[dict[str, Any]] | None = None,
    coordinator_note: str | None = None,
    debate_rounds: int | None = None,
) -> dict:
    """Log a DEBATE_STATE_SAVED event."""
    row = _adapter().write_audit_log({
        "cycle_date": cycle_date,
        "campaign_id": campaign_id,
        "action_type": AuditAction.DEBATE_STATE_SAVED.value,
        "green_proposal": green_proposal,
        "red_objections": red_objections or [],
        "coordinator_note": coordinator_note,
        "debate_rounds": debate_rounds,
    })
    logger.info(
        "audit_logged",
        extra={"action": AuditAction.DEBATE_STATE_SAVED.value, "campaign_id": str(campaign_id), "cycle": cycle_date},
    )
    return row


def log_consensus_reached(
    campaign_id: UUID,
    cycle_date: str,
    green_proposal: dict[str, Any],
    red_objections: list[dict[str, Any]],
    debate_rounds: int,
) -> dict:
    """Log a CONSENSUS_REACHED event."""
    row = _adapter().write_audit_log({
        "cycle_date": cycle_date,
        "campaign_id": campaign_id,
        "action_type": AuditAction.CONSENSUS_REACHED.value,
        "green_proposal": green_proposal,
        "red_objections": red_objections,
        "debate_rounds": debate_rounds,
    })
    logger.info(
        "audit_logged",
        extra={"action": AuditAction.CONSENSUS_REACHED.value, "campaign_id": str(campaign_id), "cycle": cycle_date},
    )
    return row


def log_action_executed(
    campaign_id: UUID,
    cycle_date: str,
    action: dict[str, Any],
    debate_rounds: int,
) -> dict:
    """Log an ACTION_EXECUTED event."""
    row = _adapter().write_audit_log({
        "cycle_date": cycle_date,
        "campaign_id": campaign_id,
        "action_type": AuditAction.ACTION_EXECUTED.value,
        "target": action,
        "debate_rounds": debate_rounds,
    })
    logger.info(
        "audit_logged",
        extra={"action": AuditAction.ACTION_EXECUTED.value, "campaign_id": str(campaign_id)},
    )
    return row
