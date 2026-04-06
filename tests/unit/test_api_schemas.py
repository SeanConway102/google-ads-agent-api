"""
RED: Write the failing test first.
Tests for src/api/schemas.py — Pydantic model validation.
"""
import pytest
from datetime import datetime
from uuid import uuid4

from pydantic import ValidationError


# ──────────────────────────────────────────────────────────────────────────────
# Campaign schema tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCampaignSchemas:

    def test_campaign_create_accepts_valid_data(self):
        """Valid campaign creation data passes Pydantic validation."""
        from src.api.schemas import CampaignCreate, CampaignType

        result = CampaignCreate(
            campaign_id="cmp_12345",
            customer_id="123-456-7890",
            name="Summer Sale",
            api_key_token="tok_abc123",
            campaign_type=CampaignType.SEARCH,
            owner_tag="marketing",
        )
        assert result.campaign_id == "cmp_12345"
        assert result.customer_id == "123-456-7890"
        assert result.name == "Summer Sale"
        assert result.campaign_type == CampaignType.SEARCH
        assert result.owner_tag == "marketing"

    def test_campaign_create_requires_campaign_id(self):
        """campaign_id is required — empty string fails validation."""
        from src.api.schemas import CampaignCreate

        with pytest.raises(ValidationError) as exc_info:
            CampaignCreate(
                campaign_id="",
                customer_id="123-456-7890",
                name="Test",
                api_key_token="tok_abc",
            )
        assert "campaign_id" in str(exc_info.value)

    def test_campaign_create_requires_name(self):
        """name is required — missing name fails validation."""
        from src.api.schemas import CampaignCreate

        with pytest.raises(ValidationError) as exc_info:
            CampaignCreate(
                campaign_id="cmp_001",
                customer_id="123-456-7890",
                name="",
                api_key_token="tok_abc",
            )
        assert "name" in str(exc_info.value)

    def test_campaign_create_defaults_to_search_type(self):
        """campaign_type defaults to SEARCH when not specified."""
        from src.api.schemas import CampaignCreate, CampaignType

        result = CampaignCreate(
            campaign_id="cmp_001",
            customer_id="123-456-7890",
            name="Test",
            api_key_token="tok_abc",
        )
        assert result.campaign_type == CampaignType.SEARCH

    def test_campaign_response_is_pydantic_model(self):
        """CampaignResponse must be a Pydantic BaseModel with correct fields."""
        from src.api.schemas import CampaignResponse, CampaignStatus, CampaignType

        now = datetime(2026, 4, 6, 10, 0, 0)  # fixed test datetime
        response = CampaignResponse(
            id=uuid4(),
            campaign_id="cmp_001",
            customer_id="123-456-7890",
            name="Test",
            status=CampaignStatus.ACTIVE,
            campaign_type=CampaignType.SEARCH,
            owner_tag=None,
            created_at=now,
            last_synced_at=None,
            last_reviewed_at=None,
        )
        assert response.campaign_id == "cmp_001"
        assert response.status == CampaignStatus.ACTIVE


# ──────────────────────────────────────────────────────────────────────────────
# Wiki schema tests
# ──────────────────────────────────────────────────────────────────────────────

class TestWikiSchemas:

    def test_wiki_entry_create_accepts_valid_data(self):
        """Valid wiki entry data passes validation."""
        from src.api.schemas import WikiEntryCreate, SourceItem, RedObjection

        result = WikiEntryCreate(
            title="Keyword Optimization Guide",
            slug="keyword-optimization-guide",
            content="Full research content here...",
            sources=[SourceItem(url="https://example.com", title="Example")],
            green_rationale="Adding keywords improves match quality",
            red_objections=[RedObjection(objection="May increase CPC", resolution="Set bid limits")],
            consensus_note="Agreed to add 5 keywords with $2 bid cap",
            tags=["keywords", "optimization"],
        )
        assert result.title == "Keyword Optimization Guide"
        assert result.slug == "keyword-optimization-guide"
        assert len(result.sources) == 1
        assert len(result.red_objections) == 1

    def test_wiki_entry_create_requires_title(self):
        """title is required."""
        from src.api.schemas import WikiEntryCreate

        with pytest.raises(ValidationError) as exc_info:
            WikiEntryCreate(
                title="",
                slug="some-slug",
                content="Content",
                api_key_token="tok_abc",
            )
        assert "title" in str(exc_info.value)

    def test_wiki_entry_create_requires_content(self):
        """content is required."""
        from src.api.schemas import WikiEntryCreate

        with pytest.raises(ValidationError) as exc_info:
            WikiEntryCreate(
                title="Some Title",
                slug="some-slug",
                content="",
                api_key_token="tok_abc",
            )
        assert "content" in str(exc_info.value)

    def test_wiki_entry_create_defaults_empty_lists(self):
        """sources, red_objections, tags default to empty lists."""
        from src.api.schemas import WikiEntryCreate

        result = WikiEntryCreate(
            title="Title",
            slug="slug",
            content="Content",
            api_key_token="tok_abc",
        )
        assert result.sources == []
        assert result.red_objections == []
        assert result.tags == []

    def test_red_objection_with_resolution(self):
        """RedObjection can include a resolution string."""
        from src.api.schemas import RedObjection

        obj = RedObjection(objection="Cost too high", resolution="Reduce bid by 20%")
        assert obj.objection == "Cost too high"
        assert obj.resolution == "Reduce bid by 20%"


# ──────────────────────────────────────────────────────────────────────────────
# Debate state schema tests
# ──────────────────────────────────────────────────────────────────────────────

class TestDebateStateSchemas:

    def test_debate_state_save_validates_cycle_date_format(self):
        """cycle_date must be YYYY-MM-DD format."""
        from src.api.schemas import DebateStateSave

        result = DebateStateSave(
            cycle_date="2026-04-06",
            campaign_id=uuid4(),
            phase="green_proposes",
            round_number=1,
            green_proposals=[],
            red_objections=[],
            consensus_reached=False,
        )
        assert result.cycle_date == "2026-04-06"

    def test_debate_state_save_rejects_invalid_date(self):
        """Invalid date format raises ValidationError."""
        from src.api.schemas import DebateStateSave

        with pytest.raises(ValidationError) as exc_info:
            DebateStateSave(
                cycle_date="04-06-2026",  # Wrong format
                campaign_id=uuid4(),
                phase="idle",
            )
        assert "cycle_date" in str(exc_info.value)

    def test_debate_state_save_requires_valid_uuid(self):
        """campaign_id must be a valid UUID."""
        from src.api.schemas import DebateStateSave

        with pytest.raises(ValidationError) as exc_info:
            DebateStateSave(
                cycle_date="2026-04-06",
                campaign_id="not-a-uuid",
                phase="idle",
            )
        assert "campaign_id" in str(exc_info.value)

    def test_debate_state_save_defaults_round_to_1(self):
        """round_number defaults to 1."""
        from src.api.schemas import DebateStateSave

        result = DebateStateSave(
            cycle_date="2026-04-06",
            campaign_id=uuid4(),
            phase="idle",
        )
        assert result.round_number == 1

    def test_debate_state_save_rejects_round_above_20(self):
        """round_number must be <= 20."""
        from src.api.schemas import DebateStateSave

        with pytest.raises(ValidationError) as exc_info:
            DebateStateSave(
                cycle_date="2026-04-06",
                campaign_id=uuid4(),
                phase="idle",
                round_number=25,
            )
        assert "round_number" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────────────
# Webhook schema tests
# ──────────────────────────────────────────────────────────────────────────────

class TestWebhookSchemas:

    def test_webhook_register_requires_https_url(self):
        """Webhook URL must be a valid HTTPS endpoint."""
        from src.api.schemas import WebhookRegister, WebhookEvent

        result = WebhookRegister(
            url="https://example.com/webhook",
            events=[WebhookEvent.CONSENSUS_REACHED],
            secret="hmac_secret",
        )
        assert result.url == "https://example.com/webhook"
        assert WebhookEvent.CONSENSUS_REACHED in result.events

    def test_webhook_register_accepts_empty_events_list(self):
        """An empty events list is valid (register now, subscribe later)."""
        from src.api.schemas import WebhookRegister

        result = WebhookRegister(
            url="https://example.com/webhook",
            events=[],
        )
        assert result.events == []
        assert result.url == "https://example.com/webhook"

    def test_webhook_event_enum_values(self):
        """WebhookEvent enum has expected values."""
        from src.api.schemas import WebhookEvent

        assert WebhookEvent.CONSENSUS_REACHED.value == "consensus_reached"
        assert WebhookEvent.ACTION_EXECUTED.value == "action_executed"
        assert WebhookEvent.DEBATE_STALLED.value == "debate_stalled"
        assert WebhookEvent.CAMPAIGN_SYNCED.value == "campaign_synced"


# ──────────────────────────────────────────────────────────────────────────────
# Error response schema tests
# ──────────────────────────────────────────────────────────────────────────────

class TestErrorSchemas:

    def test_error_response_serializes_correctly(self):
        """ErrorResponse produces correct JSON structure."""
        from src.api.schemas import ErrorResponse

        error = ErrorResponse(
            error="validation_error",
            detail="campaign_id is required",
            request_id="req_abc123",
        )
        data = error.model_dump(exclude_none=True)
        assert data["error"] == "validation_error"
        assert data["detail"] == "campaign_id is required"
        assert data["request_id"] == "req_abc123"

    def test_error_response_optional_fields(self):
        """ErrorResponse detail and request_id are optional."""
        from src.api.schemas import ErrorResponse

        error = ErrorResponse(error="internal_error")
        data = error.model_dump(exclude_none=True)
        assert "detail" not in data
        assert "request_id" not in data
