"""
RED: Write the failing test first.
Tests for src/services/email_service.py — Resend SDK wrapper.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestEmailServiceSendProposalEmail:
    """Tests for send_proposal_email()."""

    def test_send_proposal_email_calls_resend_with_correct_params(self):
        """send_proposal_email sends email via Resend with proposal details."""
        with patch("resend.Emails") as mock_emails_cls:
            mock_emails_cls.send.return_value = {"id": "msg_abc123"}

            from src.services.email_service import send_proposal_email
            send_proposal_email(
                to_email="owner@example.com",
                campaign_name="Test Campaign",
                proposal_type="budget_update",
                impact_summary="Increase daily budget from $50 to $75",
                reasoning="CTR has been 4.2% over past 30 days, suggesting headroom.",
            )

            mock_emails_cls.send.assert_called_once()
            params = mock_emails_cls.send.call_args[0][0]
            assert params["to"] == ["owner@example.com"]
            assert "[AdsAgent] Action required" in params["subject"]
            assert "budget_update" in params["subject"]
            assert "Test Campaign" in params["html"]
            assert "Increase daily budget" in params["html"]
            assert "CTR has been 4.2%" in params["html"]
            assert "approve" in params["html"].lower()
            assert "reject" in params["html"].lower()

    def test_send_proposal_email_returns_message_id_on_success(self):
        """send_proposal_email returns the Resend message ID on success."""
        with patch("resend.Emails") as mock_emails_cls:
            mock_emails_cls.send.return_value = {"id": "msg_abc123"}

            from src.services.email_service import send_proposal_email
            result = send_proposal_email(
                to_email="owner@example.com",
                campaign_name="Test Campaign",
                proposal_type="keyword_add",
                impact_summary="Adding 10 new keywords",
                reasoning="Test reasoning.",
            )

            assert result == {"id": "msg_abc123"}

    def test_send_proposal_email_raises_on_api_error(self):
        """send_proposal_email raises an exception when Resend API fails."""
        with patch("resend.Emails") as mock_emails_cls:
            mock_emails_cls.send.side_effect = Exception("Resend API error: 401 Unauthorized")

            from src.services.email_service import send_proposal_email
            with pytest.raises(Exception) as exc_info:
                send_proposal_email(
                    to_email="owner@example.com",
                    campaign_name="Test Campaign",
                    proposal_type="budget_update",
                    impact_summary="Increase budget",
                    reasoning="Test reasoning.",
                )
            assert "Resend API error" in str(exc_info.value)


class TestEmailServiceSendWeeklyDigest:
    """Tests for send_weekly_digest()."""

    def test_send_weekly_digest_calls_resend_with_metrics(self):
        """send_weekly_digest sends digest email with performance metrics."""
        with patch("resend.Emails") as mock_emails_cls:
            mock_emails_cls.send.return_value = {"id": "msg_digest456"}

            from src.services.email_service import send_weekly_digest
            send_weekly_digest(
                to_email="owner@example.com",
                campaign_name="Test Campaign",
                impressions=50000,
                clicks=1250,
                spend=250.00,
                ctr=2.5,
                n_approved=3,
                n_rejected=1,
                n_pending=2,
            )

            mock_emails_cls.send.assert_called_once()
            params = mock_emails_cls.send.call_args[0][0]
            assert params["to"] == ["owner@example.com"]
            assert "[AdsAgent] Weekly update" in params["subject"]
            assert "Test Campaign" in params["html"]
            assert "50,000" in params["html"]  # impressions formatted
            assert "1,250" in params["html"]   # clicks formatted
            assert "250.00" in params["html"]  # spend formatted
            assert "2.5%" in params["html"]   # CTR formatted
            assert "3 approved" in params["html"]
            assert "1 rejected" in params["html"]
            assert "2 proposal(s) awaiting your review" in params["html"]

    def test_send_weekly_digest_returns_message_id_on_success(self):
        """send_weekly_digest returns Resend message ID on success."""
        with patch("resend.Emails") as mock_emails_cls:
            mock_emails_cls.send.return_value = {"id": "msg_digest789"}

            from src.services.email_service import send_weekly_digest
            result = send_weekly_digest(
                to_email="owner@example.com",
                campaign_name="Test Campaign",
                impressions=10000,
                clicks=300,
                spend=100.00,
                ctr=3.0,
                n_approved=1,
                n_rejected=0,
                n_pending=1,
            )

            assert result == {"id": "msg_digest789"}
