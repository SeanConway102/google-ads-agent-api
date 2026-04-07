"""
Weekly digest cron — sends performance summary emails to HITL-enabled campaign owners.

Triggered by HITL_WEEKLY_CRON (default: every 5 minutes).
For each campaign with hitl_enabled=true and owner_email set:
  1. Expires stale pending HITL proposals
  2. Counts pending/approved/rejected hitl_proposals
  3. Sends weekly digest email via Resend
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from src.config import get_settings
from src.db.postgres_adapter import PostgresAdapter
from src.services.email_service import send_weekly_digest


def _adapter() -> PostgresAdapter:
    return PostgresAdapter()


def _collect_active_hitl_campaigns() -> list[dict[str, Any]]:
    """Return campaigns that have hitl_enabled=true and an owner_email."""
    campaigns = _adapter().list_campaigns()
    return [
        c for c in campaigns
        if c.get("hitl_enabled") and c.get("owner_email")
    ]


def _build_digest_data(
    campaign: dict[str, Any],
    performance_data: dict[str, Any] | None,
    pending_count: int,
    approved_count: int,
    rejected_count: int,
) -> dict[str, Any]:
    """
    Build the digest data dict for a single campaign.

    performance_data is typically the campaign insights dict from
    Google Ads (impressions, clicks, cost_micros fields).
    cost_micros is in microdollars — convert to dollars by dividing by 1_000_000.
    """
    impressions = performance_data.get("impressions", 0) if performance_data else 0
    clicks = performance_data.get("clicks", 0) if performance_data else 0
    # cost_micros: divide by 1_000_000 to get dollars
    cost_micros = performance_data.get("cost_micros", 0) if performance_data else 0
    spend = cost_micros / 1_000_000 if cost_micros else 0.0

    # CTR = clicks / impressions * 100, avoid zero division
    ctr = (clicks / impressions * 100) if impressions > 0 else 0.0

    return {
        "campaign_name": campaign.get("name", "Unknown Campaign"),
        "impressions": impressions,
        "clicks": clicks,
        "spend": round(spend, 2),
        "ctr": round(ctr, 1),
        "n_pending": pending_count,
        "n_approved": approved_count,
        "n_rejected": rejected_count,
    }


def _count_proposals_by_status(campaign_id: str) -> tuple[int, int, int]:
    """Return (pending_count, approved_count, rejected_count) for a campaign."""
    adapter = _adapter()
    all_proposals = adapter.list_hitl_proposals(campaign_id)
    pending = sum(1 for p in all_proposals if p["status"] == "pending")
    approved = sum(1 for p in all_proposals if p["status"] == "approved")
    rejected = sum(1 for p in all_proposals if p["status"] == "rejected")
    return pending, approved, rejected


def _expire_old_proposals(ttl_days: int) -> dict[str, int]:
    """
    Mark pending HITL proposals older than ttl_days as expired.

    Returns {"expired": N} with the count of proposals expired.
    """
    adapter = _adapter()
    campaigns = adapter.list_campaigns()
    expired = 0

    for campaign in campaigns:
        proposals = adapter.list_hitl_proposals(str(campaign["id"]))
        cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
        for proposal in proposals:
            if proposal.get("status") != "pending":
                continue
            created_at_str = proposal.get("created_at")
            if not created_at_str:
                continue
            # Handle both aware (with timezone) and naive (no timezone) datetimes
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except ValueError:
                created_at = datetime.fromisoformat(created_at_str)
            if not created_at.tzinfo:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at < cutoff:
                adapter.update_hitl_proposal_status(str(proposal["id"]), "expired")
                expired += 1

    return {"expired": expired}


def send_weekly_digests() -> dict[str, int]:
    """
    Send weekly digest emails to all HITL-enabled campaign owners.
    Also expires stale pending proposals older than HITL_PROPOSAL_TTL_DAYS.

    Returns {"sent": N, "failed": M} with counts of successful and failed sends.
    """
    settings = get_settings()
    ttl_days = settings.HITL_PROPOSAL_TTL_DAYS

    # Expire old pending proposals before sending digests
    _expire_old_proposals(ttl_days=ttl_days)

    campaigns = _collect_active_hitl_campaigns()
    sent = 0
    failed = 0

    for campaign in campaigns:
        owner_email = campaign.get("owner_email")
        if not owner_email:
            continue

        # Get proposal counts
        pending, approved, rejected = _count_proposals_by_status(str(campaign["id"]))

        # Get performance data (placeholder — real impl would call Google Ads API)
        performance_data = None

        data = _build_digest_data(
            campaign=campaign,
            performance_data=performance_data,
            pending_count=pending,
            approved_count=approved,
            rejected_count=rejected,
        )

        try:
            send_weekly_digest(
                to_email=owner_email,
                campaign_name=data["campaign_name"],
                impressions=data["impressions"],
                clicks=data["clicks"],
                spend=data["spend"],
                ctr=data["ctr"],
                n_approved=data["n_approved"],
                n_rejected=data["n_rejected"],
                n_pending=data["n_pending"],
            )
            sent += 1
        except Exception:
            failed += 1

    return {"sent": sent, "failed": failed}


if __name__ == "__main__":
    # Allow running directly: python -m src.cron.weekly_digest
    result = send_weekly_digests()
    print(f"Weekly digests: {result['sent']} sent, {result['failed']} failed")
