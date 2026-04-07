"""
MCP Capability Guard — restricts which Google Ads operations the agent can invoke.

Implements a deny-by-default capability matrix. The agent may only call
operations explicitly listed in ALLOWED_OPERATIONS. All write, delete, and
high-risk operations require explicit allow-listing.

Usage:
    guard = CapabilityGuard()
    guard.check("google_ads.create_campaign")  # raises CapabilityDenied if not allowed
"""
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Capability(str, Enum):
    """Google Ads operations that the agent is permitted to call."""
    # ─── Read operations (allowed by default) ───────────────────────────────
    LIST_CAMPAIGNS = "google_ads.list_campaigns"
    GET_CAMPAIGN = "google_ads.get_campaign"
    LIST_KEYWORDS = "google_ads.list_keywords"
    GET_KEYWORD = "google_ads.get_keyword"
    GET_AD_GROUP = "google_ads.get_ad_group"
    LIST_AD_GROUPS = "google_ads.list_ad_groups"
    GET_PERFORMANCE_REPORT = "google_ads.get_performance_report"
    GET_ACCOUNT_HIERARCHY = "google_ads.get_account_hierarchy"

    # ─── Write operations (require explicit allow-list) ─────────────────────
    CREATE_CAMPAIGN = "google_ads.create_campaign"
    UPDATE_CAMPAIGN_BUDGET = "google_ads.update_campaign_budget"
    UPDATE_CAMPAIGN_STATUS = "google_ads.update_campaign_status"
    ADD_KEYWORDS = "google_ads.add_keywords"
    REMOVE_KEYWORDS = "google_ads.remove_keywords"
    UPDATE_BIDDING_STRATEGY = "google_ads.update_bidding_strategy"

    # ─── Delete operations (always denied) ──────────────────────────────────
    DELETE_CAMPAIGN = "google_ads.delete_campaign"
    DELETE_AD_GROUP = "google_ads.delete_ad_group"
    DELETE_KEYWORD = "google_ads.delete_keyword"

    # ─── Admin operations (always denied) ───────────────────────────────────
    TRANSFER_ANOTHER_ACCOUNT = "google_ads.transfer_another_account"
    UPDATE_PAYMENT_INSTRUMENT = "google_ads.update_payment_instrument"
    CHANGE_DAILY_BUDGET_BY_PERCENT = "google_ads.change_daily_budget_by_percent"


class Permission(Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class CapabilityRule:
    """A single capability rule: which operations are allowed/denied."""
    pattern: str  # e.g. "google_ads.list_*" or "google_ads.delete_*"
    permission: Permission


class CapabilityDenied(Exception):
    """Raised when the agent attempts a capability that is not permitted."""
    def __init__(self, operation: str, reason: str | None = None):
        self.operation = operation
        self.reason = reason
        detail = f"Capability denied: {operation}"
        if reason:
            detail += f" — {reason}"
        super().__init__(detail)


class CapabilityGuard:
    """
    Deny-by-default capability guard for Google Ads MCP operations.

    Rules are evaluated in order. The first matching rule wins.
    Operations not matching any rule are DENIED.
    """

    # Default rules — deny-by-default.
    # Order matters: first matching rule wins. Read operations explicitly allowed;
    # everything else (write, delete, admin) is denied unless explicitly allowed.
    DEFAULT_RULES: list[CapabilityRule] = [
        # Deny dangerous admin/write operations first
        CapabilityRule("google_ads.delete_*", Permission.DENY),
        CapabilityRule("google_ads.transfer_*", Permission.DENY),
        CapabilityRule("google_ads.update_payment_*", Permission.DENY),
        CapabilityRule("google_ads.change_daily_budget_*", Permission.DENY),
        # Explicitly allow safe read operations
        CapabilityRule("google_ads.list_*", Permission.ALLOW),
        CapabilityRule("google_ads.get_*", Permission.ALLOW),
        CapabilityRule("google_ads.get_performance_report", Permission.ALLOW),
        CapabilityRule("google_ads.get_account_hierarchy", Permission.ALLOW),
        # Allow specific safe keyword operations
        CapabilityRule("google_ads.add_*", Permission.ALLOW),
        CapabilityRule("google_ads.remove_*", Permission.ALLOW),
        # Deny all other operations (no catchall allow)
    ]

    def __init__(
        self,
        rules: list[CapabilityRule] | None = None,
        allowed_operations: set[str] | None = None,
        denied_operations: set[str] | None = None,
    ) -> None:
        """
        Configure the capability guard.

        Args:
            rules: Override default rules. If None, uses DEFAULT_RULES.
            allowed_operations: Explicit set of operation names to allow
                (in addition to rules, highest priority).
            denied_operations: Explicit set of operation names to deny
                (overrides rules).
        """
        self._rules = rules if rules is not None else self.DEFAULT_RULES
        self._allowed = allowed_operations or set()
        self._denied = denied_operations or set()

    def check(self, operation: str) -> None:
        """
        Check if an operation is permitted. Raises CapabilityDenied if denied.

        Args:
            operation: The full operation name, e.g. "google_ads.create_campaign"

        Raises:
            CapabilityDenied: If the operation is not permitted.
        """
        # Explicit deny always wins
        if operation in self._denied:
            logger.warning("capability_denied", extra={"operation": operation, "reason": "explicit_deny"})
            raise CapabilityDenied(operation, "explicitly denied in guard config")

        # Explicit allow overrides everything
        if operation in self._allowed:
            logger.info("capability_allowed", extra={"operation": operation, "source": "explicit_allow"})
            return

        # Evaluate rules
        for rule in self._rules:
            if self._matches_pattern(operation, rule.pattern):
                if rule.permission == Permission.ALLOW:
                    logger.info("capability_allowed", extra={"operation": operation, "source": "rule", "pattern": rule.pattern})
                    return
                else:
                    logger.warning("capability_denied", extra={"operation": operation, "pattern": rule.pattern})
                    raise CapabilityDenied(operation, f"matched deny pattern: {rule.pattern}")

        # No match = deny
        logger.warning("capability_denied", extra={"operation": operation, "reason": "no_matching_rule"})
        raise CapabilityDenied(operation, "no matching capability rule")

    def can(self, operation: str) -> bool:
        """Return True if the operation is permitted, False otherwise."""
        try:
            self.check(operation)
            return True
        except CapabilityDenied:
            return False

    @staticmethod
    def _matches_pattern(operation: str, pattern: str) -> bool:
        """Check if operation matches a glob-like pattern (supports * wildcard)."""
        import fnmatch
        return fnmatch.fnmatch(operation, pattern)

    def require_write_permission(self, operation: str) -> None:
        """
        Verify the operation is a write operation and is allowed.
        Write operations are defined as those whose capability name starts with
        create_, update_, add_, or remove_.
        """
        write_prefixes = ("google_ads.create_", "google_ads.update_", "google_ads.add_", "google_ads.remove_")
        if any(operation.startswith(pref) for pref in write_prefixes):
            logger.info("write_operation_check", extra={"operation": operation})
            self.check(operation)
