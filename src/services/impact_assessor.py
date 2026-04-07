"""
Impact assessor — determines if a Green Team proposal is above HITL threshold.

Threshold rules (from HITL spec):
  budget_update     : budget change >20%
  keyword_add      : >5 keywords at once
  keyword_remove   : any removal (always above)
  match_type_change: any broad→exact change (always above)
"""
from src.config import get_settings


def is_above_threshold(*, proposal_type: str, **kwargs) -> bool:
    """
    Returns True if the proposal is above the impact threshold.
    False otherwise.
    """
    if proposal_type == "budget_update":
        current = kwargs.get("current_value", 0)
        proposed = kwargs.get("proposed_value", 0)
        if current <= 0:
            return False
        pct_change = abs(proposed - current) / current
        return pct_change > 0.20

    if proposal_type == "keyword_add":
        count = kwargs.get("count", 0)
        return count > 5

    if proposal_type == "keyword_remove":
        return True  # any removal is above threshold

    if proposal_type == "match_type_change":
        return True  # any match type change is above threshold

    # Unknown proposal types default to below threshold
    return False


def should_require_approval(*, proposal_type: str, **kwargs) -> bool:
    """
    Returns True if HITL approval is required before executing this proposal.

    Requires BOTH:
    1. hitl_enabled=true on the campaign
    2. The proposal is above the impact threshold
    """
    settings = get_settings()
    if not settings.HITL_ENABLED:
        return False
    return is_above_threshold(proposal_type=proposal_type, **kwargs)
