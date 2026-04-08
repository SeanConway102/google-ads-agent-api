"""
RED: Test that send_weekly_digest raises on Resend API error.

The send_proposal_email error path is tested, but send_weekly_digest
was not tested — its except block (lines 126-127) is uncovered.
"""
from unittest.mock import MagicMock, patch
import pytest


class TestSendWeeklyDigestError:
    """send_weekly_digest must raise when Resend API fails."""

    def test_send_weekly_digest_raises_on_api_error(self):
        """
        When Emails.send() raises in send_weekly_digest, the error must
        propagate (not silently swallowed). The caller (weekly_digest cron)
        must know the email failed so it can retry or alert.
        """
        with patch("resend.Emails") as mock_emails_cls:
            mock_emails_cls.send.side_effect = RuntimeError("Resend rate limit exceeded")

            from src.services.email_service import send_weekly_digest
            with pytest.raises(Exception, match="Resend API error"):
                send_weekly_digest(
                    to_email="owner@example.com",
                    campaign_name="Test Campaign",
                    impressions=10000,
                    clicks=500,
                    spend=100.0,
                    ctr=5.0,
                    n_approved=2,
                    n_rejected=1,
                    n_pending=0,
                )

    def test_send_weekly_digest_error_message_contains_cause(self):
        """
        The raised exception must contain the original error message so
        callers can log it for debugging.
        """
        with patch("resend.Emails") as mock_emails_cls:
            mock_emails_cls.send.side_effect = RuntimeError("connection timeout")

            from src.services.email_service import send_weekly_digest
            with pytest.raises(Exception) as exc_info:
                send_weekly_digest(
                    to_email="owner@example.com",
                    campaign_name="Test Campaign",
                    impressions=10000,
                    clicks=500,
                    spend=100.0,
                    ctr=5.0,
                    n_approved=2,
                    n_rejected=1,
                    n_pending=0,
                )

            # Original error must be in the raised exception
            assert "connection timeout" in str(exc_info.value) or "Resend API error" in str(exc_info.value)
