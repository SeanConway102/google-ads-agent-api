"""
RED: Write the failing test first.
Tests for reply_handler.py — stores question replies in hitl_proposals.

BUG: email_replies.py fires question_asked webhook for "question" intent,
but the owner's actual question text is never persisted anywhere.
reply_handler should exist and handle question storage.
"""
import uuid
from unittest.mock import MagicMock, patch
import pytest

from src.services.reply_handler import parse_reply, handle_inbound_reply


class TestParseReply:
    """parse_reply classifies email body as approved/rejected/question."""

    def test_approve_words(self):
        for word in ["approve", "yes", "sounds good", "do it", "go ahead", "sounds great"]:
            assert parse_reply(word) == "approved", f"'{word}' should be approved"

    def test_reject_words(self):
        for word in ["reject", "no", "not this time", "not now", "don't"]:
            assert parse_reply(word) == "rejected", f"'{word}' should be rejected"

    def test_question_words(self):
        assert parse_reply("Can you explain why this is needed?") == "question"
        assert parse_reply("I have some questions about this") == "question"
        assert parse_reply("What is the expected CPC?") == "question"


class TestHandleInboundReplyQuestion:
    """When owner asks a question, the question text should be stored in hitl_proposals."""

    def test_question_stores_proposal_in_hitl_proposals(self):
        """
        A question reply (not approve/reject) should call adapter.create_proposal
        with the owner's question body stored as reasoning/impact_summary.
        """
        campaign_uuid = uuid.uuid4()
        proposal_uuid = uuid.uuid4()

        mock_adapter = MagicMock()
        mock_adapter.get_campaign_by_owner_email.return_value = {
            "id": campaign_uuid,
            "campaign_id": "cmp_001",
            "customer_id": "cust_001",
            "name": "Test Campaign",
            "owner_email": "owner@example.com",
            "hitl_enabled": True,
        }
        mock_adapter.get_latest_debate_state_any_cycle.return_value = {
            "id": 1,
            "phase": "pending_manual_review",
            "round_number": 3,
            "campaign_id": campaign_uuid,
            "green_proposals": [
                {"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]},
            ],
            "red_objections": [],
            "consensus_reached": False,
        }
        mock_adapter.list_hitl_proposals.return_value = []

        with patch("src.services.reply_handler.PostgresAdapter", return_value=mock_adapter):
            handle_inbound_reply(
                from_email="owner@example.com",
                to_email="reply@adsagent.ai",
                subject=f"Re: [AdsAgent] Action required on campaign [#proposal-{proposal_uuid}]",
                body="Can you explain why this is needed?",
            )

        # Should have created a hitl_proposals entry for the question
        mock_adapter.create_hitl_proposal.assert_called_once()
        call_args = mock_adapter.create_hitl_proposal.call_args[0][0]
        assert call_args["campaign_id"] == campaign_uuid
        assert call_args["proposal_type"] == "question"
        assert "Can you explain" in call_args["reasoning"]

    def test_question_does_not_store_proposal_when_hitl_disabled(self):
        """
        When hitl_enabled=False, question replies must NOT create hitl_proposals.
        This prevents replies to non-HITL campaigns from creating spurious proposals.
        """
        campaign_uuid = uuid.uuid4()

        mock_adapter = MagicMock()
        mock_adapter.get_campaign_by_owner_email.return_value = {
            "id": campaign_uuid,
            "campaign_id": "cmp_001",
            "customer_id": "cust_001",
            "name": "Test Campaign",
            "owner_email": "owner@example.com",
            "hitl_enabled": False,  # HITL disabled
        }
        mock_adapter.get_latest_debate_state_any_cycle.return_value = {
            "id": 1,
            "phase": "pending_manual_review",
            "round_number": 3,
            "campaign_id": campaign_uuid,
            "green_proposals": [
                {"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]},
            ],
            "red_objections": [],
            "consensus_reached": False,
        }

        with patch("src.services.reply_handler.PostgresAdapter", return_value=mock_adapter):
            handle_inbound_reply(
                from_email="owner@example.com",
                to_email="reply@adsagent.ai",
                subject="Re: [AdsAgent] Action required on campaign [#proposal-abc]",
                body="Can you explain why this is needed?",
            )

        # Must NOT create any hitl_proposals entry
        mock_adapter.create_hitl_proposal.assert_not_called()
