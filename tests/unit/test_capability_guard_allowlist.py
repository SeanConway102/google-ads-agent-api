"""
RED: Test that the CapabilityGuard default rules match the documented security model.
The README incorrectly states only add_keywords is allowed. The guard must allow
all read operations (list_*, get_*) and safe keyword write operations.
"""
from src.mcp.capability_guard import CapabilityGuard, CapabilityDenied


class TestCapabilityGuardDefaultAllowlist:
    """Verify the default CapabilityGuard allows the expected operations."""

    def test_read_operations_are_allowed(self):
        """All list_* and get_* operations must pass without raising."""
        guard = CapabilityGuard()
        read_ops = [
            "google_ads.list_campaigns",
            "google_ads.get_campaign",
            "google_ads.list_keywords",
            "google_ads.get_keyword",
            "google_ads.list_ad_groups",
            "google_ads.get_ad_group",
            "google_ads.get_performance_report",
            "google_ads.get_account_hierarchy",
        ]
        for op in read_ops:
            guard.check(op)  # Must not raise

    def test_keyword_write_operations_are_allowed(self):
        """Safe keyword write operations must pass without raising."""
        guard = CapabilityGuard()
        write_ops = [
            "google_ads.add_keywords",
            "google_ads.remove_keywords",
            "google_ads.update_keyword_bids",
            "google_ads.update_keyword_match_types",
        ]
        for op in write_ops:
            guard.check(op)  # Must not raise

    def test_dangerous_operations_are_denied(self):
        """Budget changes, deletions, and admin operations must be denied."""
        guard = CapabilityGuard()
        denied_ops = [
            "google_ads.delete_campaign",
            "google_ads.delete_ad_group",
            "google_ads.delete_keyword",
            "google_ads.update_campaign_budget",
            "google_ads.update_campaign_status",
            "google_ads.transfer_another_account",
            "google_ads.update_payment_instrument",
            "google_ads.change_daily_budget_by_percent",
        ]
        for op in denied_ops:
            try:
                guard.check(op)
                assert False, f"{op} should have been denied"
            except CapabilityDenied:
                pass  # expected
