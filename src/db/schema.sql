-- Google Ads Agent API — PostgreSQL Schema
-- All tables for: campaigns, wiki, audit, debate state, webhooks

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- CAMPAIGNS
-- =============================================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     VARCHAR(64) NOT NULL,          -- Google Ads campaign ID
    customer_id     VARCHAR(32) NOT NULL,          -- Google Ads customer ID
    name            VARCHAR(255) NOT NULL,
    api_key_token   TEXT NOT NULL,                 -- Google Ads refresh token
    status          VARCHAR(16) DEFAULT 'active',  -- active | paused | synced
    campaign_type   VARCHAR(64),                   -- search | display | shopping | video
    owner_tag       VARCHAR(128),                  -- team/department label
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at  TIMESTAMPTZ,                   -- last Google Ads sync
    last_reviewed_at TIMESTAMPTZ                    -- last agent review
);

CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_owner_tag ON campaigns(owner_tag);
CREATE UNIQUE INDEX IF NOT EXISTS idx_campaigns_campaign_id ON campaigns(campaign_id);

-- =============================================================================
-- WIKI ENTRIES
-- Embeddingless RAG via PostgreSQL full-text search (tsvector)
-- =============================================================================
CREATE TABLE IF NOT EXISTS wiki_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(512) NOT NULL,
    slug            VARCHAR(256) UNIQUE NOT NULL,  -- unique: no duplicate topics
    content         TEXT NOT NULL,                  -- full markdown content

    -- Research metadata
    sources         JSONB DEFAULT '[]',             -- [{url, title, date, excerpt}]
    green_rationale TEXT,                          -- Green Team's reasoning
    red_objections  JSONB DEFAULT '[]',            -- [{objection, evidence, resolution, was_resolved}]
    consensus_note  TEXT,                          -- Coordinator's final note
    tags            VARCHAR(128)[] DEFAULT '{}',

    -- Timestamps
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    verified_at     TIMESTAMPTZ,                   -- last re-validated by time-decay challenge
    invalidated_at  TIMESTAMPTZ,                  -- contradicted by new research
    invalidation_reason VARCHAR(512)               -- why it was invalidated
);

-- Full-text search vector — generated column for embeddingless RAG
-- No vector embeddings needed: use tsvector + ts_rank for relevance scoring
ALTER TABLE wiki_entries ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', title || ' ' || content)
    ) STORED;

-- GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_wiki_search ON wiki_entries USING GIN(search_vector);

-- Index for active (non-invalidated) entries
CREATE INDEX IF NOT EXISTS idx_wiki_active ON wiki_entries(created_at DESC)
    WHERE invalidated_at IS NULL;

-- =============================================================================
-- AUDIT LOG
-- Permanent, immutable record of all agent decisions
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_date      DATE NOT NULL,                 -- YYYY-MM-DD of research cycle
    campaign_id     UUID REFERENCES campaigns(id) ON DELETE SET NULL,

    -- What happened
    action_type     VARCHAR(64) NOT NULL,          -- keyword_added | keyword_removed | bid_updated | etc.
    target          JSONB,                          -- full change payload

    -- Full debate transcript
    green_proposal  JSONB,                          -- Green Team's full proposal
    red_objections  JSONB,                          -- Red Team's full objections
    coordinator_note TEXT,                          -- Coordinator's reasoning
    debate_rounds   INT,                            -- number of debate rounds before consensus

    -- Metadata
    performed_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_campaign ON audit_log(campaign_id);
CREATE INDEX IF NOT EXISTS idx_audit_cycle ON audit_log(cycle_date DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action_type);

-- =============================================================================
-- DEBATE STATE
-- Tracks the adversarial loop progress per campaign per cycle
-- =============================================================================
CREATE TABLE IF NOT EXISTS debate_state (
    id                      SERIAL PRIMARY KEY,
    cycle_date              DATE NOT NULL,
    campaign_id             UUID REFERENCES campaigns(id) ON DELETE SET NULL,

    -- Current phase in the debate state machine
    phase                   VARCHAR(32) NOT NULL DEFAULT 'idle',
    -- idle | performance_pull | green_proposes | red_challenges |
    -- coordinator_evaluates | consensus_locked | wiki_update | pending_manual_review

    round_number            INT DEFAULT 1,           -- increments each green-red cycle

    -- Debate content
    green_proposals         JSONB DEFAULT '[]',    -- [{type, target, change, priority, reasoning, evidence}]
    red_objections           JSONB DEFAULT '[]',    -- [{proposal_id, verdict, objections, reasoning}]

    -- Coordinator decision
    coordinator_decision    JSONB,                  -- {verdict, raw_response, compromise}

    -- Consensus flag
    consensus_reached        BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (cycle_date, campaign_id)
);

CREATE INDEX IF NOT EXISTS idx_debate_cycle ON debate_state(cycle_date);
CREATE INDEX IF NOT EXISTS idx_debate_phase ON debate_state(phase);

-- =============================================================================
-- WEBHOOK SUBSCRIPTIONS
-- =============================================================================
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url         TEXT NOT NULL,                     -- webhook endpoint URL
    events      VARCHAR(64)[] DEFAULT '{}',        -- ['decision_made', 'consensus_reached', ...]
    secret      TEXT,                              -- HMAC-SHA256 signing secret (optional)
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_active ON webhook_subscriptions(active);

-- =============================================================================
-- WEBHOOK DELIVERY LOG
-- Tracks delivery attempts with exponential backoff retry
-- =============================================================================
CREATE TABLE IF NOT EXISTS webhook_delivery_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,

    -- What was delivered
    event           VARCHAR(64) NOT NULL,
    payload         JSONB,

    -- Delivery state
    status          VARCHAR(16) DEFAULT 'pending',
    -- pending | retrying | delivered | failed

    attempts         INT DEFAULT 0,
    next_retry_at   TIMESTAMPTZ,
    last_error      TEXT,
    delivered_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_delivery_subscription ON webhook_delivery_log(subscription_id);
CREATE INDEX IF NOT EXISTS idx_delivery_status ON webhook_delivery_log(status);
CREATE INDEX IF NOT EXISTS idx_delivery_retry ON webhook_delivery_log(next_retry_at)
    WHERE status = 'retrying';
