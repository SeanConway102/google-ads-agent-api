"""
Request/response schemas for the Campaign Management API.
All API inputs and outputs are validated with Pydantic models.
"""
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────

class CampaignStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class CampaignType(str, Enum):
    SEARCH = "search"
    DISPLAY = "display"
    SHOPPING = "shopping"
    VIDEO = "video"


# ──────────────────────────────────────────────────────────────────────────────
# Campaign schemas
# ──────────────────────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    """Request body for POST /campaigns."""
    campaign_id: str = Field(..., min_length=1, max_length=100, description="Google Ads campaign ID")
    customer_id: str = Field(..., min_length=1, max_length=100, description="Google Ads customer ID")
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable campaign name")
    api_key_token: str = Field(..., min_length=1, description="API key token for Google Ads")
    campaign_type: CampaignType = Field(default=CampaignType.SEARCH)
    owner_tag: Optional[str] = Field(default=None, max_length=100, description="Owner team or tag")

    model_config = {
        "json_schema_extra": {
            "example": {
                "campaign_id": "cmp_12345",
                "customer_id": "123-456-7890",
                "name": "Summer Sale Campaign",
                "api_key_token": "tok_abc123xyz",
                "campaign_type": "search",
                "owner_tag": "marketing",
            }
        }
    }


class CampaignResponse(BaseModel):
    """Response body for campaign operations."""
    id: UUID
    campaign_id: str
    customer_id: str
    name: str
    status: CampaignStatus
    campaign_type: Optional[CampaignType] = None
    owner_tag: Optional[str]
    created_at: datetime
    last_synced_at: Optional[datetime]
    last_reviewed_at: Optional[datetime]
    # HITL fields
    hitl_enabled: Optional[bool] = False
    owner_email: Optional[str] = None
    hitl_threshold: Optional[str] = "budget>20pct,keyword_add>5"


class CampaignUpdate(BaseModel):
    """Request body for PATCH /campaigns/{uuid} — update HITL and other mutable fields."""
    hitl_enabled: Optional[bool] = None
    owner_email: Optional[str] = None
    hitl_threshold: Optional[str] = None


class CampaignListResponse(BaseModel):
    """Response body for GET /campaigns."""
    campaigns: List[CampaignResponse]
    total: int


class CampaignInsights(BaseModel):
    """Response body for GET /campaigns/{uuid}/insights."""
    id: UUID
    campaign_id: str
    customer_id: str
    name: str
    status: CampaignStatus
    campaign_type: CampaignType
    owner_tag: Optional[str]
    created_at: datetime
    last_synced_at: Optional[datetime]
    last_reviewed_at: Optional[datetime]
    # Debate state fields (null if no debate has run yet)
    phase: Optional[str] = None
    round_number: Optional[int] = None
    green_proposals: Optional[List[Any]] = None
    red_objections: Optional[List[Any]] = None
    coordinator_decision: Optional[dict] = None
    consensus_reached: Optional[bool] = None


class ActionPayload(BaseModel):
    """Request body for POST /campaigns/{uuid}/override."""
    action_type: str = Field(..., min_length=1, description="Action type e.g. keyword_add, keyword_remove")
    keywords: Optional[List[str]] = Field(default=None, description="Keywords for keyword actions")
    bid_adjustment: Optional[float] = Field(default=None, description="Bid adjustment value")
    ad_group_id: Optional[str] = Field(default=None, description="Ad group ID target")


class ApproveResponse(BaseModel):
    """Response body for POST /campaigns/{uuid}/approve."""
    status: str
    campaign_id: UUID


class OverrideResponse(BaseModel):
    """Response body for POST /campaigns/{uuid}/override."""
    status: str
    audit_id: int


class TriggerResponse(BaseModel):
    """Response body for POST /research/trigger."""
    status: str
    campaign_id: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Wiki schemas
# ──────────────────────────────────────────────────────────────────────────────

class SourceItem(BaseModel):
    """A source reference in a wiki entry."""
    url: str
    title: str


class RedObjection(BaseModel):
    """A red team objection with resolution."""
    objection: str
    resolution: Optional[str] = None


class WikiEntryCreate(BaseModel):
    """Request body for POST /wiki."""
    title: str = Field(..., min_length=1, max_length=500)
    slug: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    sources: List[SourceItem] = Field(default_factory=list)
    green_rationale: Optional[str] = None
    red_objections: List[RedObjection] = Field(default_factory=list)
    consensus_note: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class WikiEntryResponse(BaseModel):
    """Response body for wiki operations."""
    id: UUID
    title: str
    slug: str
    content: str
    sources: List[SourceItem]
    green_rationale: Optional[str]
    red_objections: List[RedObjection]
    consensus_note: Optional[str]
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime]
    invalidated_at: Optional[datetime]
    invalidation_reason: Optional[str]


class WikiSearchResponse(BaseModel):
    """Response body for GET /wiki/search."""
    entries: List[WikiEntryResponse]
    query: str
    limit: int


# ──────────────────────────────────────────────────────────────────────────────
# Debate state schemas
# ──────────────────────────────────────────────────────────────────────────────

class DebatePhase(str, Enum):
    IDLE = "idle"
    GREEN_PROPOSES = "green_proposes"
    RED_CHALLENGES = "red_challenges"
    COORDINATOR_DECIDES = "coordinator_decides"
    CONSENSUS = "consensus"


class GreenProposal(BaseModel):
    """A green team proposal."""
    type: str = Field(..., description="e.g. keyword_add, negative_keyword, bid_adjustment")
    value: Any = Field(..., description="The proposed change value")


class DebateStateSave(BaseModel):
    """Request body for PUT /debate/state."""
    cycle_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    campaign_id: UUID
    phase: DebatePhase
    round_number: int = Field(default=1, ge=1, le=20)
    green_proposals: List[GreenProposal] = Field(default_factory=list)
    red_objections: List[RedObjection] = Field(default_factory=list)
    consensus_reached: bool = Field(default=False)


class DebateStateResponse(BaseModel):
    """Response body for debate state operations."""
    id: int
    cycle_date: str
    campaign_id: UUID
    phase: DebatePhase
    round_number: int
    green_proposals: List[GreenProposal]
    red_objections: List[RedObjection]
    coordinator_decision: Optional[dict]
    consensus_reached: bool
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Webhook schemas
# ──────────────────────────────────────────────────────────────────────────────

class WebhookEvent(str, Enum):
    CONSENSUS_REACHED = "consensus_reached"
    ACTION_EXECUTED = "action_executed"
    DEBATE_STALLED = "debate_stalled"
    CAMPAIGN_SYNCED = "campaign_synced"


class WebhookRegister(BaseModel):
    """Request body for POST /webhooks."""
    url: str = Field(..., description="HTTPS endpoint URL")
    events: List[WebhookEvent] = Field(..., description="Event types to subscribe to")
    secret: Optional[str] = Field(default=None, description="HMAC secret for signing payloads")

    @field_validator("url")
    @classmethod
    def url_must_be_https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("url must use HTTPS")
        return v


class WebhookResponse(BaseModel):
    """Response body for webhook operations."""
    id: UUID
    url: str
    events: List[WebhookEvent]
    active: bool
    created_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Audit log schemas
# ──────────────────────────────────────────────────────────────────────────────

class AuditAction(str, Enum):
    CAMPAIGN_CREATED = "campaign_created"
    CAMPAIGN_DELETED = "campaign_deleted"
    WIKI_CREATED = "wiki_created"
    WIKI_INVALIDATED = "wiki_invalidated"
    DEBATE_STATE_SAVED = "debate_state_saved"
    CONSENSUS_REACHED = "consensus_reached"
    ACTION_EXECUTED = "action_executed"


class AuditLogResponse(BaseModel):
    """Response body for audit log queries."""
    id: int
    cycle_date: Optional[str]
    campaign_id: Optional[UUID]
    action_type: AuditAction
    target: Optional[dict]
    green_proposal: Optional[dict]
    red_objections: Optional[List[RedObjection]]
    coordinator_note: Optional[str]
    debate_rounds: Optional[int]
    performed_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# HITL / Proposal schemas
# ──────────────────────────────────────────────────────────────────────────────

class HitlProposalResponse(BaseModel):
    """Response body for a single HITL proposal."""
    id: UUID
    campaign_id: UUID
    proposal_type: str
    impact_summary: str
    reasoning: str
    status: str  # pending | approved | rejected | expired
    created_at: datetime
    updated_at: datetime
    decided_at: Optional[datetime] = None
    replier_response: Optional[str] = None


class HitlDecisionRequest(BaseModel):
    """Request body for POST /campaigns/{uuid}/hitl/proposals/{id}/decide."""
    decision: str = Field(..., description="Must be 'approved' or 'rejected'")
    notes: Optional[str] = Field(default=None, description="Optional coordinator notes")


class HitlDecisionResponse(BaseModel):
    """Response body after deciding a HITL proposal."""
    id: UUID
    status: str
    decided_at: Optional[datetime] = None


# ──────────────────────────────────────────────────────────────────────────────
# Error schemas
# ──────────────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None
