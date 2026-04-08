"""
RED: Test route_proposals — HITL routing for Green Team proposals.

route_proposals (lines 122-146) is completely untested. It routes proposals
to HITL or auto-execution based on threshold and hitl_enabled.

Additionally, _send_proposal_email_for (lines 179-193) has a bug:
    proposal.get("reasoning", "")[:300]
crashes when reasoning is explicitly None (dict.get returns None, not "").
The fix: (proposal.get("reasoning") or "")[:300]
"""
import uuid
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.agents.green_team import GreenTeamAgent


class TestRouteProposals:
    """route_proposals routes proposals based on threshold and hitl_enabled."""

    @pytest.fixture
    def mock_assessor(self, monkeypatch):
        """Mock should_require_approval to avoid config dependency."""
        mock = MagicMock()
        monkeypatch.setattr(
            "src.services.impact_assessor.should_require_approval", mock
        )
        return mock

    @pytest.fixture
    def mock_email(self, monkeypatch):
        mock = MagicMock(return_value={"id": "em_123"})
        # send_proposal_email is a sync function — using AsyncMock would cause
        # the await in _send_proposal_email_for to receive a coroutine instead
        # of the return value. Use MagicMock so await passes through directly.
        monkeypatch.setattr(
            "src.services.email_service.send_proposal_email", mock
        )
        return mock

    @pytest.fixture
    def mock_settings(self, monkeypatch):
        """Set env vars so Settings() can be instantiated without ValidationError."""
        # MUST clear cache FIRST before any env var is set or Settings() is called
        # because lru_cache caches failures too, and a prior test's cached failure
        # will persist even after env vars are changed.
        # Only delete config module — we need green_team and postgres_adapter
        # to stay intact so mock_adapter's monkeypatch applies to the right module.
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
        monkeypatch.setenv("HITL_DEFAULT_EMAIL", "default@example.com")
        return get_settings()

    @pytest.fixture
    def mock_adapter(self, monkeypatch):
        mock = MagicMock()
        mock.execute_returning.return_value = {"id": uuid.uuid4()}
        monkeypatch.setattr(
            "src.db.postgres_adapter.PostgresAdapter", lambda: mock
        )
        return mock

    @pytest.mark.asyncio
    async def test_above_threshold_hitl_enabled_goes_to_approval(
        self, mock_assessor, mock_email, mock_adapter, mock_settings
    ):
        """
        Proposal above threshold with hitl_enabled=true is routed to needs_approval.
        """
        mock_assessor.return_value = True  # above threshold

        agent = GreenTeamAgent()
        proposals = [
            {"type": "keyword_add", "count": 10, "impact_summary": "add 10 keywords"},
        ]
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": True,
            "owner_email": "owner@example.com",
        }

        needs_approval, auto_execute = await agent.route_proposals(proposals, campaign)

        assert len(needs_approval) == 1
        assert len(auto_execute) == 0

    @pytest.mark.asyncio
    async def test_below_threshold_hitl_enabled_goes_to_auto_execute(
        self, mock_assessor, mock_email, mock_adapter, mock_settings
    ):
        """
        Proposal below threshold goes directly to auto_execute.
        """
        mock_assessor.return_value = False  # below threshold

        agent = GreenTeamAgent()
        proposals = [
            {"type": "keyword_add", "count": 3, "impact_summary": "add 3 keywords"},
        ]
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": True,
            "owner_email": "owner@example.com",
        }

        needs_approval, auto_execute = await agent.route_proposals(proposals, campaign)

        assert len(needs_approval) == 0
        assert len(auto_execute) == 1

    @pytest.mark.asyncio
    async def test_hitl_disabled_goes_to_auto_execute_regardless_of_threshold(
        self, mock_assessor, mock_email, mock_adapter, mock_settings
    ):
        """
        When hitl_enabled=false, proposals go to auto_execute even if above threshold.
        """
        mock_assessor.return_value = True  # would need approval

        agent = GreenTeamAgent()
        proposals = [
            {"type": "keyword_add", "count": 10, "impact_summary": "add 10 keywords"},
        ]
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": False,
            "owner_email": "owner@example.com",
        }

        needs_approval, auto_execute = await agent.route_proposals(proposals, campaign)

        assert len(needs_approval) == 0
        assert len(auto_execute) == 1

    @pytest.mark.asyncio
    async def test_mixed_proposals_split_correctly(
        self, mock_assessor, mock_email, mock_adapter, mock_settings
    ):
        """
        Some above threshold, some below → correct split.
        """
        # Return True for first proposal, False for second
        mock_assessor.side_effect = [True, False]

        agent = GreenTeamAgent()
        proposals = [
            {"type": "keyword_add", "count": 10, "impact_summary": "add 10"},
            {"type": "keyword_add", "count": 3, "impact_summary": "add 3"},
        ]
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": True,
            "owner_email": "owner@example.com",
        }

        needs_approval, auto_execute = await agent.route_proposals(proposals, campaign)

        assert len(needs_approval) == 1
        assert len(auto_execute) == 1

    @pytest.mark.asyncio
    async def test_above_threshold_sends_proposal_email(
        self, mock_assessor, mock_email, mock_adapter, mock_settings
    ):
        """
        When proposal is routed to needs_approval, send_proposal_email is called.
        """
        mock_assessor.return_value = True

        agent = GreenTeamAgent()
        proposals = [
            {"type": "keyword_add", "count": 10, "impact_summary": "add 10 keywords"},
        ]
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": True,
            "owner_email": "owner@example.com",
        }

        await agent.route_proposals(proposals, campaign)

        mock_email.assert_called_once()
        call_kwargs = mock_email.call_args.kwargs
        assert call_kwargs["to_email"] == "owner@example.com"
        assert call_kwargs["campaign_name"] == "Test Campaign"

    @pytest.mark.asyncio
    async def test_above_threshold_creates_hitl_proposal_record(
        self, mock_assessor, mock_email, mock_adapter, mock_settings
    ):
        """
        When proposal is routed to needs_approval, a HITL proposal DB record is created.
        """
        mock_assessor.return_value = True

        agent = GreenTeamAgent()
        proposals = [
            {"type": "keyword_add", "count": 10, "impact_summary": "add 10 keywords"},
        ]
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": True,
            "owner_email": "owner@example.com",
        }

        await agent.route_proposals(proposals, campaign)

        mock_adapter.execute_returning.assert_called_once()
        call_args = mock_adapter.execute_returning.call_args
        assert "INSERT INTO hitl_proposals" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_above_threshold_with_none_reasoning_does_not_crash(
        self, mock_assessor, mock_email, mock_adapter, mock_settings
    ):
        """
        Proposal with reasoning=None must not crash in _send_proposal_email_for.

        BUG: proposal.get("reasoning", "")[:300] crashes when reasoning is
        explicitly None. The fix: (proposal.get("reasoning") or "")[:300]
        """
        mock_assessor.return_value = True

        agent = GreenTeamAgent()
        proposals = [
            {
                "type": "keyword_add",
                "count": 10,
                "impact_summary": "add 10 keywords",
                "reasoning": None,  # explicitly None — dict.get returns None, not ""
            },
        ]
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": True,
            "owner_email": "owner@example.com",
        }

        # Must not raise TypeError
        needs_approval, auto_execute = await agent.route_proposals(proposals, campaign)

        assert len(needs_approval) == 1

    @pytest.mark.asyncio
    async def test_above_threshold_with_explicit_none_impact_summary(
        self, mock_assessor, mock_email, mock_adapter, mock_settings
    ):
        """
        Proposal with impact_summary=None must not crash.
        """
        mock_assessor.return_value = True

        agent = GreenTeamAgent()
        proposals = [
            {
                "type": "keyword_add",
                "count": 10,
                "impact_summary": None,
                "change": "add keywords",
                "reasoning": None,
            },
        ]
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": True,
            "owner_email": "owner@example.com",
        }

        needs_approval, auto_execute = await agent.route_proposals(proposals, campaign)
        assert len(needs_approval) == 1

    @pytest.mark.asyncio
    async def test_proposal_without_owner_email_uses_default_email(
        self, mock_assessor, mock_email, mock_adapter, mock_settings, monkeypatch
    ):
        """
        When campaign has no owner_email, send_proposal_email uses HITL_DEFAULT_EMAIL.
        """
        mock_assessor.return_value = True
        monkeypatch.setenv("ADMIN_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("HITL_ENABLED", "true")
        monkeypatch.setenv("HITL_DEFAULT_EMAIL", "default@example.com")

        agent = GreenTeamAgent()
        proposals = [
            {"type": "keyword_add", "count": 10, "impact_summary": "add 10"},
        ]
        campaign = {
            "id": uuid.uuid4(),
            "name": "Test Campaign",
            "hitl_enabled": True,
            "owner_email": None,  # no owner email
        }

        await agent.route_proposals(proposals, campaign)

        mock_email.assert_called_once()
        assert mock_email.call_args.kwargs["to_email"] == "default@example.com"
