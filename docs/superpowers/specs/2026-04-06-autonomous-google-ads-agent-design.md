# Autonomous Google Ads Optimization Agent — Design Spec

**Date:** 2026-04-06
**Status:** Approved for Planning

---

## 1. Overview

An autonomous headless agent system that researches advertising theory, studies Google Ads campaign performance, and continuously optimizes managed campaigns through an adversarial three-agent architecture. The system runs on a Digital Ocean droplet, manages campaigns via a custom MCP-wrapped Google Ads API, and stores all knowledge in a PostgreSQL-backed wiki with embeddingless RAG.

**Core Principle:** Nothing executes until all three agents agree. All decisions are grounded in campaign performance data and validated research.

---

## 2. Architecture

```
Digital Ocean Droplet (Ubuntu 22.04)
│
├── PostgreSQL 16 (local, swappable to managed)
│   ├── campaigns table
│   ├── wiki_entries table
│   ├── audit_log table
│   ├── debate_state table        # tracks adversarial loop progress
│   └── webhook_subscriptions table
│
├── Cron Scheduler (systemd cron)
│   └── Triggers research loop daily
│
├── Agent Runtime (Python via LangChain DeepAgents)
│   ├── Coordinator Agent         # orchestrates green/red teams
│   ├── Green Team Agent          # proposes optimizations
│   └── Red Team Agent            # challenges/validates proposals
│
├── Custom Google Ads MCP Server
│   ├── Wraps Google Ads API v17
│   ├── Enforces capability restrictions
│   └── Exposes only safe tools to agents
│
└── REST API Server (FastAPI / Flask)
    ├── Headless, API-key authenticated
    └── Single admin key
```

---

## 3. Campaign Management API

### 3.1 Data Model

```sql
CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     VARCHAR(64) NOT NULL,      -- Google Ads campaign ID
    customer_id     VARCHAR(32) NOT NULL,      -- Google Ads customer ID
    name            VARCHAR(255) NOT NULL,
    api_key_token   TEXT NOT NULL,            -- Google Ads refresh token
    status          VARCHAR(16) DEFAULT 'active',
    campaign_type   VARCHAR(64),
    owner_tag       VARCHAR(128),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at  TIMESTAMPTZ,
    last_reviewed_at TIMESTAMPTZ              -- when agent last reviewed performance
);

-- Indexes
CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_campaigns_owner_tag ON campaigns(owner_tag);
```

### 3.2 Authentication

- Single admin API key via `X-API-Key` header
- Key stored as env var `ADMIN_API_KEY` on droplet
- All endpoints require this key — no per-client or per-campaign auth

### 3.3 Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/campaigns` | Add a campaign to management |
| `DELETE` | `/campaigns/{id}` | Remove a campaign |
| `GET` | `/campaigns` | List all campaigns with summaries |
| `GET` | `/campaigns/{id}` | Get single campaign details |
| `GET` | `/campaigns/{id}/insights` | Get current agent recommendations for this campaign |
| `POST` | `/campaigns/{id}/approve` | Approve a pending agent action |
| `POST` | `/campaigns/{id}/override` | Force a manual override (bypasses adversarial check) |
| `GET` | `/research/wiki` | Search/query the wiki |
| `GET` | `/research/wiki/{entry_id}` | Get specific wiki entry |
| `GET` | `/audit-log` | Full decision/action audit trail |
| `POST` | `/webhooks` | Register webhook URL for decision notifications |
| `DELETE` | `/webhooks/{id}` | Remove webhook |
| `GET` | `/health` | Health check |

### 3.4 Request/Response Shapes

**POST /campaigns**
```json
{
  "campaign_id": "123456789",
  "customer_id": "987654321",
  "name": "Summer Sale - Search",
  "api_key_token": "1//0gYEdMk...longtoken",
  "campaign_type": "search",
  "owner_tag": "marketing-team"
}
```

**GET /campaigns/{id}/insights**
```json
{
  "campaign_id": "123456789",
  "last_reviewed_at": "2026-04-06T08:00:00Z",
  "current_recommendations": [
    {
      "type": "add_keyword",
      "keyword": "summer sale shoes",
      "match_type": "phrase",
      "priority": "high",
      "reasoning": "Green team: high search volume, aligns with existing themes",
      "status": "pending_consensus"
    }
  ],
  "wiki_context": ["entry_id_1", "entry_id_2"]
}
```

---

## 4. Custom Google Ads MCP Server

### 4.1 Purpose

The MCP server is the **capability boundary**. It wraps the Google Ads API and exposes only whitelisted tools to the agent runtime. This is how we enforce that the agent never touches budget, creates campaigns, or modifies ad copy.

### 4.2 Capability Matrix

| Google Ads Operation | Allowed via MCP |
|---|---|
| Read campaign data (all fields) | ✅ Yes |
| Read keyword performance | ✅ Yes |
| Read ad copy and assets | ✅ Yes |
| Read audience/targeting data | ✅ Yes |
| Add keywords | ✅ Yes |
| Remove keywords | ✅ Yes |
| Modify keyword bids | ✅ Yes |
| Modify keyword match types | ✅ Yes |
| Modify campaign budget | 🔴 Blocked (MCP raises `CAPABILITY_FORBIDDEN`) |
| Modify ad copy | 🔴 Blocked |
| Create new campaigns | 🔴 Blocked |
| Modify campaign settings/targeting | 🔴 Blocked |
| Pause/delete campaigns | 🔴 Blocked |

### 4.3 MCP Tools Exposed

```json
{
  "tools": [
    "google_ads.get_campaigns",
    "google_ads.get_keywords",
    "google_ads.get_keyword_performance",
    "google_ads.get_ad_copy",
    "google_ads.add_keywords",
    "google_ads.remove_keywords",
    "google_ads.update_keyword_bids",
    "google_ads.update_keyword_match_types"
  ]
}
```

### 4.4 Implementation

- MCP server runs as a Python process on the droplet
- Agents communicate with it via stdio (MCP stdio protocol)
- The MCP client is initialized once per research cycle and reused
- All blocked operations raise a structured `CAPABILITY_FORBIDDEN` error with the operation name

---

## 5. Autonomous Research Agent (LangChain DeepAgents)

### 5.1 Three-Agent Architecture

```
┌─────────────────────────────────────────┐
│          Coordinator Agent               │
│  (LangChain DeepAgent)                  │
│                                         │
│  - Owns the debate state machine         │
│  - Feeds campaign performance data      │
│  - Feeds wiki context (prior research)  │
│  - Declares consensus or continues loop │
└───────────┬─────────────┬───────────────┘
            │             │
   Green Team          Red Team
   (Proposer)          (Challenger)
```

**Green Team Agent:** Proposes optimizations based on research + campaign data. Must cite specific evidence (wiki entries, performance data, source URLs). Proposes with structured rationale.

**Red Team Agent:** Actively challenges every Green Team proposal. Looks for: flawed reasoning, missing context, contradictory data, outdated assumptions. Must provide counter-evidence for each objection.

**Coordinator Agent:** Orchestrates. Decides when to continue debate and when consensus is reached. Enforces that no decision ships without explicit Red Team sign-off.

### 5.2 Daily Research Loop (State Machine)

Stored in `debate_state` table. Tracks progress across phases.

```
PHASE 1: performance_pull
  → Fetch latest performance data for all campaigns via MCP
  → Store in debate_state.payload

PHASE 2: green_proposes
  → Green Team receives: campaign data + wiki context
  → Green Team outputs: list of proposed actions with structured reasoning

PHASE 3: red_challenges
  → Red Team receives: Green proposals + campaign data
  → Red Team outputs: list of objections per proposal

PHASE 4: coordinator_evaluates
  → Coordinator reviews: green proposals + red objections
  → If unresolved objections → loop back to PHASE 2 (green revises)
  → If all objections resolved → PHASE 5

  Loop counter: max 5 rounds before escalation (manual review flag)

PHASE 5: consensus_locked
  → All three agents have agreed
  → Actions are marked as approved
  → Execute via MCP (only allowed operations)
  → Write to audit_log
  → Update wiki with validated findings
  → Fire webhooks

PHASE 6: wiki_update
  → Write new wiki entries for validated research
  → Update campaign.last_reviewed_at
```

### 5.3 Debate State Table

```sql
CREATE TABLE debate_state (
    id                  SERIAL PRIMARY KEY,
    cycle_date          DATE NOT NULL,
    campaign_id         UUID REFERENCES campaigns(id),
    phase               VARCHAR(32) NOT NULL,
    round_number        INT DEFAULT 1,
    green_proposals     JSONB,
    red_objections      JSONB,
    coordinator_decision JSONB,
    consensus_reached   BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.4 Research Sources (Full Stack)

1. **Google Ads Official Docs** — documentation, policy updates, best practices
2. **Academic Papers** — arXiv/SSRN advertising research (via Jina MCP for retrieval)
3. **Industry News** — Search Engine Land, PPC industry blogs
4. **Competitor Intelligence** — public competitor ad data, market research
5. **Campaign Performance Data** — direct from Google Ads via MCP — the agent's own empirical data

The campaign performance data is the most important source — it grounds all theoretical research in actual results.

### 5.5 Campaign Performance as Validation Input

Each daily cycle, the agent reviews:
- CTR, CPC, conversion rate trends per keyword
- Search term report — new queries to potentially add as keywords
- Negative keyword opportunities — searches consuming budget without converting
- Keyword-level quality score trends

This performance data is fed to both Green Team and Red Team before proposals are made. Red Team specifically challenges whether Green Team's proposals align with what the data actually shows.

---

## 6. Wiki (Embeddingless RAG)

### 6.1 Schema

```sql
CREATE TABLE wiki_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(512) NOT NULL,
    slug            VARCHAR(256) UNIQUE NOT NULL,
    content         TEXT NOT NULL,           -- Full markdown content
    sources         JSONB,                   -- [{url, title, date, excerpt}]
    green_rationale TEXT,                    -- Why Green Team accepted this
    red_objections  JSONB,                  -- [{objection, resolution, was_resolved}]
    consensus_note  TEXT,                   -- Coordinator's final note
    tags            VARCHAR(128)[],
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    verified_at     TIMESTAMPTZ,             -- When last re-validated
    invalidated_at  TIMESTAMPTZ               -- If contradicted by new research
);
```

### 6.2 Embeddingless RAG Strategy

Full-text search using PostgreSQL `tsvector` and `ts_rank` / `ts_rank_cd`:

```sql
-- Full-text search (no vector embeddings needed)
SELECT id, title, slug, ts_rank(search_vector, query) AS rank
FROM wiki_entries, to_tsquery('english', 'keyword & optimization & google_ads') AS query
WHERE search_vector @@ query
  AND invalidated_at IS NULL
ORDER BY rank DESC;
```

`search_vector` is a generated column: `ALTER TABLE wiki_entries ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED;`

Each wiki entry also maintains a `sources` JSONB array — during research, agents can pull in specific source citations rather than relying on semantic similarity.

### 6.3 Wiki Update Rules

- New entries are created only after consensus is reached (Phase 5)
- Entries that are contradicted by new performance data are marked `invalidated_at` rather than deleted (preserves audit trail)
- The `verified_at` field is updated each time an entry survives adversarial re-challenge (time-decay challenge)

---

## 7. Audit Log

```sql
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_date      DATE NOT NULL,
    campaign_id    UUID REFERENCES campaigns(id),
    action_type     VARCHAR(64) NOT NULL,   -- keyword_added, keyword_removed, bid_updated, etc.
    target          JSONB,                   -- What was changed
    green_proposal  JSONB,                   -- Full Green Team proposal
    red_objections  JSONB,                   -- Full Red Team objections
    coordinator_note TEXT,
    debate_rounds   INT,
    performed_at    TIMESTAMPTZ DEFAULT NOW()
);
```

Every action, every proposal, every objection, and the final coordinator note are permanently stored. Nothing is ever lost.

---

## 8. Webhooks

```sql
CREATE TABLE webhook_subscriptions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url         TEXT NOT NULL,
    events      VARCHAR(64)[],               -- ['decision_made', 'consensus_reached', 'action_executed']
    secret      TEXT,                         -- HMAC secret for payload signing
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

Webhook payload:
```json
{
  "event": "consensus_reached",
  "cycle_date": "2026-04-06",
  "campaign_id": "uuid",
  "actions": [...],
  "debate_rounds": 3,
  "performed_at": "2026-04-06T08:45:00Z"
}
```

Signed with `HMAC-SHA256` using the registered secret.

---

## 9. Configuration & Environment

### 9.1 Environment Variables

```bash
# Admin
ADMIN_API_KEY=                    # Single key for all API endpoints

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/ads_agent
DB_PROVIDER=postgresql            # Swappable — if 'sqlite', use SQLite backend

# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN=       # MCC developer token
GOOGLE_ADS_CLIENT_ID=             # OAuth client ID
GOOGLE_ADS_CLIENT_SECRET=         # OAuth client secret

# LangChain / AI
OPENAI_API_KEY=                   # Or ANTHROPIC_API_KEY for LLM calls
LLM_MODEL=gpt-4o                  # Model for all three agents

# MCP
MCP_SERVER_PATH=/opt/ads-agent/mcp_server.py

# Cron
RESEARCH_CRON="0 8 * * *"         # Daily at 8am server time
MAX_DEBATE_ROUNDS=5
```

### 9.2 Database Abstraction Layer

The codebase uses an abstract `Database` interface (`src/db/base.py`) with a `PostgreSQLAdapter`. To swap to SQLite, MySQL, or a managed service later:

1. Change `DB_PROVIDER=sqlite` env var
2. Implement a new `SQLiteAdapter` / `ManagedPostgresAdapter` following the base interface
3. No other code changes needed

---

## 10. Directory Structure

```
google-ads-agent-api/
├── SPEC.md
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-06-autonomous-google-ads-agent-design.md
├── src/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # Env var loading + validation
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract Database interface
│   │   ├── postgres_adapter.py   # PostgreSQL implementation
│   │   └── sqlite_adapter.py     # SQLite implementation (future)
│   │   └── schema.sql            # All table definitions
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── campaigns.py
│   │   │   ├── wiki.py
│   │   │   ├── audit.py
│   │   │   └── webhooks.py
│   │   ├── middleware.py         # API key auth middleware
│   │   └── schemas.py            # Pydantic request/response models
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── coordinator.py        # Coordinator agent (LangChain DeepAgent)
│   │   ├── green_team.py         # Green Team agent
│   │   ├── red_team.py           # Red Team agent
│   │   ├── debate_state.py       # State machine + DB persistence
│   │   └── prompts.py            # Agent system prompts
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── server.py             # MCP server entry point
│   │   ├── tools.py              # Allowed Google Ads tool definitions
│   │   ├── capability_guard.py   # Enforces blocked operations
│   │   └── google_ads_client.py  # Google Ads API wrapper
│   ├── research/
│   │   ├── __init__.py
│   │   ├── sources.py            # Source definitions + fetchers
│   │   ├── validator.py          # Adversarial validation logic
│   │   └── wiki_writer.py        # Wiki entry creation
│   └── cron/
│       ├── __init__.py
│       └── daily_research.py      # Cron-triggered research loop script
├── tests/
│   ├── test_api_campaigns.py
│   ├── test_api_wiki.py
│   ├── test_debate_state.py
│   ├── test_mcp_capabilities.py
│   └── test_wiki_search.py
├── scripts/
│   └── run_research_cycle.py     # Direct script to trigger research cycle
├── requirements.txt
└── .env.example
```

---

## 11. Scope Boundaries (What This System Does NOT Do)

- **Does NOT manage budget** — MCP explicitly blocks all budget operations
- **Does NOT create or delete Google Ads campaigns** — only manages existing campaigns added via API
- **Does NOT modify ad copy** — read-only access to ad creative
- **Does NOT have per-client auth** — single admin key for entire system
- **Does NOT use vector embeddings** — full-text search only
- **Does NOT run on a managed cloud platform** — self-hosted on Digital Ocean droplet

---

## 12. Resolved Decisions

1. **LLM Provider:** MiniMax 2.7. All LLM calls go through `src/agents/llm_adapter.py` — an abstraction layer that accepts any LangChain-compatible chat model. To switch providers, swap the adapter implementation and env vars.

2. **Academic Papers:** Source via Jina MCP. Initial corpus seeded by running targeted arXiv/SSRN searches on: advertising attribution models, real-time bid optimization, keyword-level ROI prediction, search advertising effectiveness measurement.

3. **Webhook Retry:** Exponential backoff — 3 retries at 1min, 5min, 30min intervals after initial failure. After all retries exhausted, the delivery is marked `failed` in `webhook_delivery_log` and an alert is written to the audit log.

4. **Max-Round Escalation:** Coordinator proposes compromise. If Green Team and Red Team cannot agree after 5 rounds, the Coordinator does not stall — it synthesizes a compromise proposal that both teams can accept given their core constraints. Only if the Coordinator's compromise is also rejected does the action enter `pending_manual_review` status (flagged via API and audit log).
