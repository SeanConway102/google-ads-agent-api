"""
RED: Test _send_proposal_email_for returns early when no email is configured.

Line 185: when both owner_email is None and HITL_DEFAULT_EMAIL is empty,
the function returns {"id": "no_emailConfigured"} without calling the Resend API.
This is an important edge case — no point calling the email API with no recipient.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.agents.green_team import GreenTeamAgent


class TestSendProposalEmailNoRecipient:
    """_send_proposal_email_for must not call Resend API when no email is configured."""

    @pytest.fixture
    def mock_settings(self, monkeypatch):
        """Set env vars with EMPTY HITL_DEFAULT_EMAIL to trigger no_emailConfigured path."""
        import sys
        for mod in list(sys.modules.keys()):
            if mod == "src.config":
                del sys.modules[mod]
        from src.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("HITL_ENABLED", "true")
        monkeypatch.setenv("HITL_DEFAULT_EMAIL", "")  # Empty — no fallback
        return get_settings()

    @pytest.mark.asyncio
    async def test_no_email_configured_returns_early(self, mock_settings):
        """
        When campaign has no owner_email AND HITL_DEFAULT_EMAIL is empty,
        _send_proposal_email_for returns {"id": "no_emailConfigured"} without
        calling send_proposal_email.
        """
        agent = GreenTeamAgent()
        proposal = {"type": "keyword_add", "count": 10, "impact_summary": "test"}
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": True,
            "owner_email": None,  # No owner email
        }

        mock_email = MagicMock(return_value={"id": "em_123"})
        with patch("src.services.email_service.send_proposal_email", mock_email):
            result = await agent._send_proposal_email_for(proposal, campaign)

        assert result == {"id": "no_emailConfigured"}
        mock_email.assert_not_called()
