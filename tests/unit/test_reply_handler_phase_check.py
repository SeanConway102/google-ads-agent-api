"""
RED: Test for reply_handler silently discarding replies when phase is not PENDING.

When a campaign's debate is in APPROVED or REJECTED phase (not PENDING_MANUAL_REVIEW),
a reply from the owner is silently discarded. There's no test for this case.

The expected behavior: if phase is already APPROVED and owner replies "yes", or
if phase is REJECTED and owner asks a question, the reply_handler currently just
returns without any indication. This might be correct for approve/reject (already
decided), but it could silently lose valid question replies from owners.

This test documents the current behavior.
"""
import uuid
from unittest.mock import MagicMock, patch

from src.services.reply_handler import handle_inbound_reply


class TestReplyHandlerPhaseNotPending:
    """
    When the debate phase is not PENDING_MANUAL_REVIEW, replies are discarded.

    The current behavior: returns silently without creating a hitl_proposal.
    This means:
    - Owner replies to an already-approved debate: silently discarded
    - Owner asks a question after debate was already decided: silently discarded

    This may be correct behavior (debate is already resolved), but it means
    valid owner questions are lost without any operator notification.
    """

    def test_approved_phase_yes_reply_is_discarded(self):
        """
        When phase=APPROVED, an "approve" reply must NOT create a hitl_proposal.
        The debate is already approved — no action should be taken.
        """
        campaign_uuid = uuid.uuid4()
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
            "phase": "approved",  # NOT pending_manual_review
            "round_number": 3,
            "campaign_id": campaign_uuid,
            "green_proposals": [{"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]}],
            "red_objections": [],
            "consensus_reached": False,
        }

        with patch("src.services.reply_handler.PostgresAdapter", return_value=mock_adapter):
            handle_inbound_reply(
                from_email="owner@example.com",
                to_email="reply@adsagent.ai",
                subject="Re: [AdsAgent] Action required",
                body="yes",  # parse_reply → "approved"
            )

        # Must NOT create a hitl_proposal for already-approved debate
        mock_adapter.create_hitl_proposal.assert_not_called()

    def test_rejected_phase_question_is_discarded(self):
        """
        When phase=REJECTED, a question reply must NOT create a hitl_proposal.
        The debate is already rejected — no action should be taken.
        """
        campaign_uuid = uuid.uuid4()
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
            "phase": "rejected",  # NOT pending_manual_review
            "round_number": 3,
            "campaign_id": campaign_uuid,
            "green_proposals": [],
            "red_objections": [],
            "consensus_reached": False,
        }

        with patch("src.services.reply_handler.PostgresAdapter", return_value=mock_adapter):
            handle_inbound_reply(
                from_email="owner@example.com",
                to_email="reply@adsagent.ai",
                subject="Re: [AdsAgent] Action required",
                body="Can you explain why this was rejected?",  # parse_reply → "question"
            )

        # Must NOT create a hitl_proposal for already-rejected debate
        mock_adapter.create_hitl_proposal.assert_not_called()

    def test_approved_phase_question_is_discarded(self):
        """
        When phase=APPROVED, a question reply must NOT create a hitl_proposal.
        Even if the owner is confused and asks about an already-approved proposal,
        the current behavior is to discard it silently.
        """
        campaign_uuid = uuid.uuid4()
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
            "phase": "approved",
            "round_number": 3,
            "campaign_id": campaign_uuid,
            "green_proposals": [{"type": "keyword_add", "ad_group_id": "ag_001", "keywords": ["shoes"]}],
            "red_objections": [],
            "consensus_reached": False,
        }

        with patch("src.services.reply_handler.PostgresAdapter", return_value=mock_adapter):
            handle_inbound_reply(
                from_email="owner@example.com",
                to_email="reply@adsagent.ai",
                subject="Re: [AdsAgent] Action required",
                body="Wait, why did you add keywords I didn't ask for?",  # question
            )

        # Silently discarded — no proposal created
        mock_adapter.create_hitl_proposal.assert_not_called()
