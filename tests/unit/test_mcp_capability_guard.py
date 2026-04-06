"""
RED: Write the failing test first.
Tests for src/mcp/capability_guard.py — capability enforcement.
"""
import pytest

from src.mcp.capability_guard import (
    Capability,
    CapabilityDenied,
    CapabilityGuard,
    CapabilityRule,
    Permission,
)


class TestCapabilityGuardDefaults:

    def test_read_operations_allowed_by_default(self):
        """List, get, and report operations are allowed by default."""
        guard = CapabilityGuard()
        assert guard.can("google_ads.list_campaigns") is True
        assert guard.can("google_ads.get_campaign") is True
        assert guard.can("google_ads.get_performance_report") is True

    def test_delete_operations_denied_by_default(self):
        """Delete operations are always denied."""
        guard = CapabilityGuard()
        assert guard.can("google_ads.delete_campaign") is False
        assert guard.can("google_ads.delete_ad_group") is False
        assert guard.can("google_ads.delete_keyword") is False

    def test_transfer_operations_denied(self):
        """Account transfer operations are always denied."""
        guard = CapabilityGuard()
        assert guard.can("google_ads.transfer_another_account") is False

    def test_change_budget_by_percent_denied(self):
        """Aggressive budget changes are always denied."""
        guard = CapabilityGuard()
        assert guard.can("google_ads.change_daily_budget_by_percent") is False

    def test_update_budget_requires_explicit_allow(self):
        """update_campaign_budget is denied unless explicitly allowed."""
        guard = CapabilityGuard()
        assert guard.can("google_ads.update_campaign_budget") is False

    def test_check_raises_capability_denied(self):
        """check() raises CapabilityDenied instead of returning."""
        guard = CapabilityGuard()
        with pytest.raises(CapabilityDenied) as exc_info:
            guard.check("google_ads.delete_campaign")
        assert exc_info.value.operation == "google_ads.delete_campaign"

    def test_check_silent_for_allowed(self):
        """check() does not raise for allowed operations."""
        guard = CapabilityGuard()
        guard.check("google_ads.list_campaigns")  # should not raise


class TestCapabilityGuardExplicitAllow:

    def test_explicit_allowed_overrides_default_deny(self):
        """An explicitly allowed operation is permitted even if default would deny."""
        guard = CapabilityGuard(allowed_operations={"google_ads.update_campaign_budget"})
        assert guard.can("google_ads.update_campaign_budget") is True

    def test_explicit_denied_overrides_default_allow(self):
        """An explicitly denied operation is blocked even if default would allow."""
        guard = CapabilityGuard(denied_operations={"google_ads.get_campaign"})
        assert guard.can("google_ads.get_campaign") is False


class TestCapabilityGuardCustomRules:

    def test_custom_rules_override_defaults(self):
        """Custom rules are used when provided."""
        guard = CapabilityGuard(rules=[
            CapabilityRule("google_ads.delete_campaign", Permission.ALLOW),
        ])
        assert guard.can("google_ads.delete_campaign") is True

    def test_wildcard_pattern_matching(self):
        """Patterns with * wildcard match operation names correctly."""
        guard = CapabilityGuard(rules=[
            CapabilityRule("google_ads.list_*", Permission.ALLOW),
            CapabilityRule("google_ads.delete_*", Permission.DENY),
        ])
        assert guard.can("google_ads.list_campaigns") is True
        assert guard.can("google_ads.list_keywords") is True
        assert guard.can("google_ads.delete_campaign") is False


class TestCapabilityGuardCapabilityDenied:

    def test_exception_includes_operation_name(self):
        """CapabilityDenied exception includes the operation that was denied."""
        guard = CapabilityGuard()
        with pytest.raises(CapabilityDenied) as exc_info:
            guard.check("google_ads.delete_campaign")
        assert "google_ads.delete_campaign" in str(exc_info.value)

    def test_exception_includes_reason(self):
        """CapabilityDenied includes the denial reason when provided."""
        guard = CapabilityGuard()
        try:
            guard.check("google_ads.delete_campaign")
        except CapabilityDenied as exc:
            assert exc.operation == "google_ads.delete_campaign"
            assert exc.reason is not None  # has a reason from the rule

    def test_can_returns_false_for_denied(self):
        """can() returns False without raising for denied operations."""
        guard = CapabilityGuard()
        assert guard.can("google_ads.delete_campaign") is False


class TestCapabilityGuardWritePermission:

    def test_require_write_permission_allows_write_ops(self):
        """require_write_permission passes for allowed write operations."""
        guard = CapabilityGuard(allowed_operations={"google_ads.create_campaign"})
        # Should not raise
        guard.require_write_permission("google_ads.create_campaign")

    def test_require_write_permission_raises_for_denied(self):
        """require_write_permission raises CapabilityDenied for blocked write ops."""
        guard = CapabilityGuard(allowed_operations=set())  # deny all
        with pytest.raises(CapabilityDenied):
            guard.require_write_permission("google_ads.create_campaign")
