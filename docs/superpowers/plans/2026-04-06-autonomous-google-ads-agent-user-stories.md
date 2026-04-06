# User Stories — Autonomous Google Ads Optimization Agent

**Project:** Autonomous Google Ads Optimization Agent
**Date:** 2026-04-06
**Related Spec:** `2026-04-06-autonomous-google-ads-agent-design.md`

---

## Persona Index

| Persona | Description |
|---|---|
| `campaign-manager` | Marketing team member who owns Google Ads campaigns and wants the system to optimize them |
| `api-operator` | Technical user who administers the system via API |
| `green-team` | The agent that proposes optimizations |
| `red-team` | The agent that challenges and validates proposals |
| `coordinator` | The agent that orchestrates the debate and declares consensus |
| `webhook-consumer` | External system that receives decision notifications |
| `developer` | Engineer building or maintaining the system |

---

## Category 1 — Campaign Management API

### CM-001: Add a campaign to management
**Persona:** `api-operator`
**Story:** As an api-operator, I want to register a Google Ads campaign with the system by providing its campaign ID, customer ID, and API refresh token, so that the agent can begin managing and researching it.
**Acceptance Criteria:**
- [ ] `POST /campaigns` accepts campaign_id, customer_id, name, api_key_token, campaign_type, owner_tag
- [ ] Campaign is persisted to PostgreSQL with status `active`
- [ ] Returns 201 with the full campaign object including generated UUID
- [ ] Duplicate campaign_id returns 400 with error message
- [ ] Missing required fields returns 422 with validation errors

### CM-002: Remove a campaign from management
**Persona:** `api-operator`
**Story:** As an api-operator, I want to remove a campaign by its UUID, so that it is no longer managed or reviewed by the research agent.
**Acceptance Criteria:**
- [ ] `DELETE /campaigns/{uuid}` removes the campaign from the database
- [ ] Returns 204 on success
- [ ] Returns 404 if campaign does not exist
- [ ] Associated debate states are preserved (campaign_id set to null via ON DELETE SET NULL)

### CM-003: List all managed campaigns
**Persona:** `api-operator`
**Story:** As an api-operator, I want to list all campaigns with their current status and last-reviewed timestamp, so that I can see at a glance what is being managed.
**Acceptance Criteria:**
- [ ] `GET /campaigns` returns all campaigns ordered by created_at DESC
- [ ] Each result includes: id, campaign_id, customer_id, name, status, campaign_type, owner_tag, created_at, last_synced_at, last_reviewed_at
- [ ] Empty list returns `[]` with 200

### CM-004: Get a single campaign
**Persona:** `api-operator`
**Story:** As an api-operator, I want to retrieve full details for a single campaign by UUID, so that I can inspect its configuration.
**Acceptance Criteria:**
- [ ] `GET /campaigns/{uuid}` returns full campaign object
- [ ] Returns 404 if not found

### CM-005: Get current agent insights for a campaign
**Persona:** `campaign-manager`
**Story:** As a campaign-manager, I want to see what optimizations the agent is currently proposing or has approved, so that I understand the system's thinking and can intervene if needed.
**Acceptance Criteria:**
- [ ] `GET /campaigns/{uuid}/insights` returns current recommendations
- [ ] Each recommendation includes: type, keyword, match_type, priority, reasoning, status (pending_consensus / approved / rejected)
- [ ] Returns last_reviewed_at timestamp
- [ ] Returns empty recommendations list if no active proposals

### CM-006: Approve a pending agent action
**Persona:** `api-operator`
**Story:** As an api-operator, I want to explicitly approve a pending agent action via API, so that I can enforce a human-in-the-loop checkpoint before execution.
**Acceptance Criteria:**
- [ ] `POST /campaigns/{uuid}/approve` marks the action as approved
- [ ] Returns `{status: "approved", campaign_id: "..."}`
- [ ] If no pending action exists, returns 404

### CM-007: Manual override bypassing adversarial check
**Persona:** `api-operator`
**Story:** As an api-operator, I want to force a direct action on a campaign that bypasses the adversarial debate, so that I can act immediately in emergencies.
**Acceptance Criteria:**
- [ ] `POST /campaigns/{uuid}/override` accepts an action payload
- [ ] Writes directly to audit_log with action_type `manual_override`
- [ ] Does NOT invoke green/red team debate
- [ ] Returns `{status: "override_applied", audit_id: "..."}`

### CM-008: API authentication via single admin key
**Persona:** `api-operator`
**Story:** As an api-operator, I want all API endpoints to require a shared X-API-Key header, so that only authorized operators can manage campaigns.
**Acceptance Criteria:**
- [ ] All endpoints except /health reject requests without X-API-Key header
- [ ] Requests with invalid key return 401
- [ ] Health endpoint /health remains unauthenticated

---

## Category 2 — Wiki & Knowledge Management

### WK-001: Search the wiki by full-text query
**Persona:** `campaign-manager`
**Story:** As a campaign-manager, I want to search the wiki using natural language keywords, so that I can find relevant research and validated findings quickly.
**Acceptance Criteria:**
- [ ] `GET /research/wiki?q=keyword` returns matching wiki entries using PostgreSQL tsvector full-text search
- [ ] Results ordered by relevance (ts_rank)
- [ ] Only returns entries where invalidated_at IS NULL
- [ ] Limit parameter (default 10, max 100) works correctly
- [ ] Returns empty list with 200 when no matches

### WK-002: Get a specific wiki entry
**Persona:** `campaign-manager`
**Story:** As a campaign-manager, I want to retrieve a specific wiki entry by its UUID, so that I can read the full validated research including sources, green rationale, and red objections.
**Acceptance Criteria:**
- [ ] `GET /research/wiki/{uuid}` returns full entry including: title, slug, content, sources (JSONB), green_rationale, red_objections (JSONB), consensus_note, tags, created_at, updated_at
- [ ] Returns 404 if entry does not exist

### WK-003: Wiki entry created after consensus is reached
**Persona:** `coordinator`
**Story:** As the coordinator agent, I want a new wiki entry to be automatically created when all three agents reach consensus, so that validated knowledge is permanently captured.
**Acceptance Criteria:**
- [ ] After phase CONSENSUS_LOCKED, wiki_writer.write_consensus_entry is called
- [ ] Entry includes: full proposal content, green rationale, red objections (as JSONB array), coordinator consensus note, source citations
- [ ] Slug is generated from title + hash suffix to ensure uniqueness
- [ ] Tags are extracted from the research topic

### WK-004: Wiki entries invalidated when contradicted
**Persona:** `coordinator`
**Story:** As the coordinator agent, I want wiki entries that are contradicted by new campaign performance data to be marked as invalidated rather than deleted, so that the audit trail is preserved.
**Acceptance Criteria:**
- [ ] When new research contradicts an existing entry, wiki_writer.invalidate_entry sets invalidated_at timestamp
- [ ] Invalidated entries do not appear in search results
- [ ] invalidated_at is preserved in the database permanently

### WK-005: Wiki context loaded before green team proposes
**Persona:** `green-team`
**Story:** As the green team agent, I want the wiki to be queried and relevant entries passed to me as context before I propose optimizations, so that my proposals are grounded in previously validated research.
**Acceptance Criteria:**
- [ ] At the start of each research cycle, `db.search_wiki` is called with the campaign's topic keywords
- [ ] Top 5–10 relevant entries are included in the context passed to green_team.propose()

---

## Category 3 — Audit Log

### AL-001: All decisions written to audit log
**Persona:** `api-operator`
**Story:** As an api-operator, I want a permanent, immutable record of every decision the agent makes, including full green proposals, red objections, and coordinator reasoning, so that I can review and explain any action.
**Acceptance Criteria:**
- [ ] Every state transition writes to audit_log table
- [ ] audit_log entry includes: cycle_date, campaign_id, action_type, target (JSONB), green_proposal, red_objections, coordinator_note, debate_rounds, performed_at
- [ ] `GET /audit-log` returns the full audit trail
- [ ] Supports filtering by campaign_id
- [ ] Supports pagination via limit parameter

### AL-002: Manual overrides logged with admin context
**Persona:** `api-operator`
**Story:** As an api-operator, I want my manual overrides to be logged with the fact that they bypassed adversarial review, so that the audit trail clearly distinguishes forced actions from agent decisions.
**Acceptance Criteria:**
- [ ] Override actions logged with action_type `manual_override`
- [ ] coordinator_note explicitly states "Manual override by admin API"
- [ ] The target field contains the full action payload

---

## Category 4 — Webhooks

### WH-001: Register a webhook endpoint
**Persona:** `webhook-consumer`
**Story:** As a webhook-consumer, I want to register a URL and specify which events I want to receive, so that my system is notified when the agent makes decisions.
**Acceptance Criteria:**
- [ ] `POST /webhooks` accepts url, events array, and optional secret
- [ ] Supported events: `decision_made`, `consensus_reached`, `action_executed`, `manual_review_required`, `cycle_error`
- [ ] Returns 201 with the created webhook object including UUID
- [ ] Invalid event names return 400

### WH-002: Webhook delivery with exponential backoff retry
**Persona:** `webhook-consumer`
**Story:** As a webhook-consumer, I want webhooks to be retried automatically on failure so that transient issues don't cause missed notifications.
**Acceptance Criteria:**
- [ ] Failed deliveries retry at 1 minute, 5 minutes, and 30 minutes (3 retries total)
- [ ] Each delivery attempt is logged in webhook_delivery_log with status: pending, retrying, delivered, failed
- [ ] After all retries exhausted, status is marked `failed` and alert is written to audit log
- [ ] Webhook payload is signed with HMAC-SHA256 using the registered secret if provided

### WH-003: Remove webhook
**Persona:** `webhook-consumer`
**Story:** As a webhook-consumer, I want to delete a webhook subscription so that I stop receiving notifications.
**Acceptance Criteria:**
- [ ] `DELETE /webhooks/{uuid}` removes the webhook subscription
- [ ] Returns 204 on success
- [ ] Returns 404 if not found

---

## Category 5 — Google Ads MCP

### MCP-001: MCP server exposes only allowed tools
**Persona:** `developer`
**Story:** As a developer, I want the MCP server to explicitly enumerate only the allowed Google Ads operations as tools, so that the agent cannot attempt blocked operations.
**Acceptance Criteria:**
- [ ] `tools/list` returns only these tools: get_campaigns, get_keywords, get_keyword_performance, add_keywords, remove_keywords, update_keyword_bids, update_keyword_match_types
- [ ] Budget operations, campaign creation, ad copy modification, and campaign settings changes are NOT in the tool list

### MCP-002: Blocked operations raise CAPABILITY_FORBIDDEN
**Persona:** `developer`
**Story:** As a developer, I want any attempt to call a blocked Google Ads operation through the MCP to return a structured CAPABILITY_FORBIDDEN error, so that the agent receives clear feedback and can log the attempt.
**Acceptance Criteria:**
- [ ] Calling `campaign.budget.update`, `campaign.create`, `ad.copy.create`, `ad.copy.update` via MCP returns error code `CAPABILITY_FORBIDDEN`
- [ ] The error message names the blocked operation
- [ ] The attempt is logged in the audit trail

### MCP-003: Agent can add keywords via MCP
**Persona:** `green-team`
**Story:** As the green team agent, I want to add keywords to a campaign's ad group through the MCP, so that approved keyword additions are executed against Google Ads.
**Acceptance Criteria:**
- [ ] `google_ads.add_keywords` tool accepts customer_id, ad_group_id, and a list of keywords with text and match_type
- [ ] Returns a list of resource names for the newly added keywords
- [ ] After successful execution, campaign.last_synced_at is updated

### MCP-004: Agent can remove keywords via MCP
**Persona:** `red-team`
**Story:** As the red team agent (when approving removal), I want to remove underperforming or irrelevant keywords from a campaign through the MCP, so that approved removals are executed.
**Acceptance Criteria:**
- [ ] `google_ads.remove_keywords` tool accepts customer_id and a list of keyword resource names
- [ ] Returns successfully when Google Ads confirms removal
- [ ] Returns error if keyword resource name is invalid

### MCP-005: Agent can update keyword bids via MCP
**Persona:** `green-team`
**Story:** As the green team agent, I want to update CPC bids for existing keywords through the MCP, so that approved bid adjustments are applied to Google Ads.
**Acceptance Criteria:**
- [ ] `google_ads.update_keyword_bids` accepts customer_id and a list of updates with resource_name and cpc_bid_micros
- [ ] Bids are updated successfully in Google Ads

### MCP-006: Agent can update keyword match types via MCP
**Persona:** `green-team`
**Story:** As the green team agent, I want to change the match type of existing keywords through the MCP, so that approved match type changes are applied.
**Acceptance Criteria:**
- [ ] `google_ads.update_keyword_match_types` accepts customer_id and a list of updates with resource_name and match_type (EXACT / PHRASE / BROAD)
- [ ] Match types are updated in Google Ads

### MCP-007: Agent can read keyword performance via MCP
**Persona:** `green-team`
**Story:** As the green team agent, I want to read CTR, CPC, impressions, clicks, and conversion data for keywords, so that my proposals are grounded in actual performance data.
**Acceptance Criteria:**
- [ ] `google_ads.get_keyword_performance` returns keyword-level metrics for a campaign
- [ ] Metrics include: clicks, impressions, ctr, average_cpc, conversions

---

## Category 6 — Three-Agent Adversarial System

### AG-001: Green team proposes optimizations with evidence
**Persona:** `green-team`
**Story:** As the green team agent, I want to propose specific keyword additions, removals, bid changes, or match type changes grounded in campaign performance data and wiki research, so that every proposal has cited evidence.
**Acceptance Criteria:**
- [ ] green_team.propose() is called with campaign performance data, wiki context, and any previous red team objections
- [ ] Each proposal includes: type, target, change description, priority, reasoning, evidence (wiki sources, data trends), campaign_id
- [ ] Proposals are persisted to debate_state.green_proposals in the database

### AG-002: Red team challenges all proposals with counter-evidence
**Persona:** `red-team`
**Story:** As the red team agent, I want to actively challenge every green team proposal by identifying logical flaws, contradictions with data, and missing context, so that only well-founded changes proceed.
**Acceptance Criteria:**
- [ ] red_team.challenge() receives green proposals, campaign data, and wiki context
- [ ] Each objection includes: the flaw description, supporting evidence, and a suggested fix
- [ ] Red team explicitly approves proposals that are solid — not all proposals are challenged
- [ ] Objections are persisted to debate_state.red_objections

### AG-003: Coordinator evaluates and advances the debate
**Persona:** `coordinator`
**Story:** As the coordinator agent, I want to review green proposals and red objections, determine if consensus is reached, and instruct the debate to continue or lock, so that the system either reaches agreement or escalates.
**Acceptance Criteria:**
- [ ] coordinator.evaluate() is called after each green-red round
- [ ] Coordinator can issue: CONTINUE_DEBATE, CONSENSUS_REACHED, COMPROMISE_PROPOSED, ESCALATE
- [ ] Coordinator's decision is persisted to debate_state.coordinator_decision
- [ ] Round number increments on CONTINUE_DEBATE

### AG-004: Coordinator proposes compromise at max rounds
**Persona:** `coordinator`
**Story:** As the coordinator agent, I want to synthesize a compromise proposal when green and red cannot agree after 5 rounds, so that the debate does not stall and at least a partial improvement is captured.
**Acceptance Criteria:**
- [ ] When round_number reaches MAX_DEBATE_ROUNDS (5), coordinator issues COMPROMISE_PROPOSED
- [ ] The compromise explicitly addresses Red Team's core objection
- [ ] The compromise preserves at least part of Green Team's intended improvement
- [ ] Both green_team and red_team must ratify the compromise
- [ ] Only if compromise is also rejected does the action enter PENDING_MANUAL_REVIEW

### AG-005: Consensus required before execution
**Persona:** `coordinator`
**Story:** As the coordinator agent, I want to enforce that no Google Ads action executes until all three agents agree, so that there is a hard quality gate on all changes.
**Acceptance Criteria:**
- [ ] MCP tool calls only happen after phase == CONSENSUS_LOCKED
- [ ] consensus_reached flag must be True in debate_state
- [ ] A log entry in audit trail records the consensus

### AG-006: Debate state persists across interrupted cycles
**Persona:** `developer`
**Story:** As a developer, I want the debate state to be persisted to PostgreSQL after every phase transition, so that if the process crashes mid-debate, it can resume from where it left off.
**Acceptance Criteria:**
- [ ] After every phase transition, `debate_state` row is updated
- [ ] On next cycle start, `debate_state_machine.load_or_init()` checks for existing in-progress state
- [ ] The system resumes from the current phase, not restart

---

## Category 7 — Daily Research Loop

### RL-001: Daily cron triggers research cycle
**Persona:** `developer`
**Story:** As the system, I want a cron job to fire the research loop every day at a configured time, so that campaign optimization happens automatically without manual triggers.
**Acceptance Criteria:**
- [ ] System cron job runs `python scripts/run_research_cycle.py` daily at 8am server time
- [ ] Script handles errors gracefully — one campaign's failure does not stop the entire cycle
- [ ] Each campaign is processed in sequence
- [ ] Full cycle can also be triggered manually via `python scripts/run_research_cycle.py`

### RL-002: Performance data pulled from Google Ads each cycle
**Persona:** `developer`
**Story:** As the system, I want to pull the latest keyword performance data from Google Ads for each campaign at the start of each research cycle, so that the agents are working with current data.
**Acceptance Criteria:**
- [ ] `google_ads.get_keyword_performance()` is called for each active campaign at PHASE 1 (performance_pull)
- [ ] Performance data is stored in the debate_state payload
- [ ] After pull, phase advances to GREEN_PROPOSES

### RL-003: Research sources fetched from Jina MCP
**Persona:** `developer`
**Story:** As the system, I want to pull the latest advertising research from academic papers and industry sources via Jina MCP, so that the agents have current theoretical grounding.
**Acceptance Criteria:**
- [ ] Jina MCP is used to search arXiv/SSRN for: advertising attribution, bid optimization, keyword ROI, search effectiveness
- [ ] Industry news searched via Jina parallel search for: Google Ads best practices, PPC optimization techniques
- [ ] Sources are stored in the wiki as draft entries (not yet validated)

### RL-004: Manual trigger via API or script
**Persona:** `api-operator`
**Story:** As an api-operator, I want to manually trigger a research cycle for a specific campaign or all campaigns on demand, so that I don't have to wait for the daily cron.
**Acceptance Criteria:**
- [ ] `POST /research/trigger` accepts optional campaign_id — if omitted, runs all campaigns
- [ ] Script `scripts/run_research_cycle.py` can be run directly from the command line
- [ ] Trigger returns immediately; research runs asynchronously

---

## Category 8 — LLM Adapter & Provider Swapping

### LL-001: All agents use the LLM adapter abstraction
**Persona:** `developer`
**Story:** As a developer, I want all three agents to call the LLM through `src/agents/llm_adapter.py`, so that we can swap the underlying LLM provider without changing agent code.
**Acceptance Criteria:**
- [ ] `get_llm_adapter()` factory function returns the configured adapter based on LLM_PROVIDER env var
- [ ] MiniMax adapter implements the full `LLMAdapter` interface
- [ ] Changing LLM_PROVIDER to "openai" or "anthropic" loads a different adapter (interface must be satisfied)

### LL-002: MiniMax adapter handles chat completions
**Persona:** `developer`
**Story:** As the system, I want the MiniMax adapter to send messages to the MiniMax chat completion API and return the response text, so that the agents can generate text.
**Acceptance Criteria:**
- [ ] `MiniMaxAdapter.chat(messages)` posts to the MiniMax API and returns the content of the first choice
- [ ] API key is read from MINIMAX_API_KEY env var
- [ ] Base URL is configurable via MINIMAX_BASE_URL env var
- [ ] Model is configurable via MINIMAX_MODEL env var
- [ ] Timeouts at 60 seconds

### LL-003: LLM adapter swappable without code changes
**Persona:** `developer`
**Story:** As a developer, I want to switch from MiniMax to OpenAI or Anthropic by changing environment variables and implementing a new adapter class, without touching any agent code.
**Acceptance Criteria:**
- [ ] Adding a new `OpenAIAdapter` or `AnthropicAdapter` requires only creating the file and updating `get_llm_adapter()`
- [ ] No changes needed to coordinator.py, green_team.py, or red_team.py
- [ ] Interface contract is enforced: each adapter must implement `.chat()` and `.chat_with_structured_output()`

---

## Category 9 — Database Abstraction

### DB-001: All database operations go through the adapter
**Persona:** `developer`
**Story:** As a developer, I want all database operations to go through `DatabaseAdapter`, so that swapping PostgreSQL for SQLite or a managed service requires changing only one file.
**Acceptance Criteria:**
- [ ] All API routes use `DatabaseAdapter` (injected via FastAPI Depends)
- [ ] All agent and service classes accept `DatabaseAdapter` in constructor
- [ ] New adapter implementation requires implementing all methods in `src/db/base.py`

### DB-002: PostgreSQL adapter implemented and working
**Persona:** `developer`
**Story:** As the system, I want all database operations to work against PostgreSQL 16, so that the system runs on the Digital Ocean droplet.
**Acceptance Criteria:**
- [ ] schema.sql creates all tables: campaigns, wiki_entries, audit_log, debate_state, webhook_subscriptions, webhook_delivery_log
- [ ] All DatabaseAdapter methods are implemented and tested
- [ ] Full-text search index on wiki_entries.search_vector is created

---

## Category 10 — Deployment & Operations

### OP-001: Droplet provisioning script works
**Persona:** `developer`
**Story:** As a developer, I want to run `setup_droplet.sh` on a fresh Ubuntu 22.04 Digital Ocean droplet and have the entire system running at the end, so that deployment is reproducible.
**Acceptance Criteria:**
- [ ] Script installs Python 3.12, pip, PostgreSQL 16, and git
- [ ] Script creates PostgreSQL user and database with correct credentials
- [ ] Script installs all Python dependencies from requirements.txt
- [ ] Script applies schema.sql to the database
- [ ] Script creates the .env file from .env.example
- [ ] Script sets up the cron job for daily research
- [ ] Script creates and starts the systemd service for the API
- [ ] API is reachable on port 8000 after setup

### OP-002: API server runs as systemd service
**Persona:** `developer`
**Story:** As a developer, I want the FastAPI application to run as a systemd service, so that it automatically restarts on failure and starts on boot.
**Acceptance Criteria:**
- [ ] Service definition at `/etc/systemd/system/ads-agent-api.service`
- [ ] `systemctl start ads-agent-api` starts the API
- [ ] `systemctl enable ads-agent-api` makes it start on boot
- [ ] Logs are visible via `journalctl -u ads-agent-api`

### OP-003: Health endpoint available without auth
**Persona:** `developer`
**Story:** As a developer or operator, I want a `/health` endpoint that returns 200 without requiring API authentication, so that load balancers and monitoring tools can check system health.
**Acceptance Criteria:**
- [ ] `GET /health` returns `{"status": "ok"}` with 200
- [ ] No X-API-Key header required

---

## Category 11 — Quality & Confidence

### QA-001: Every new function has a failing test before implementation
**Persona:** `developer`
**Story:** As a developer, I want every new function to be written only after a test that demonstrates the desired behavior fails, so that we follow TDD discipline and every line of code is proven necessary.
**Acceptance Criteria:**
- [ ] Each task follows RED-GREEN-Refactor: test fails first (expected error), then implementation, then test passes
- [ ] No production code committed without a corresponding failing test first
- [ ] Test output is pristine — no warnings, no errors in passing tests

### QA-002: API endpoints have integration tests
**Persona:** `developer`
**Story:** As a developer, I want all API endpoints to have integration tests using FastAPI's TestClient, so that we verify end-to-end request/response behavior.
**Acceptance Criteria:**
- [ ] All campaign endpoints (POST, GET, GET list, DELETE) have tests
- [ ] All wiki endpoints have tests
- [ ] All webhook endpoints have tests
- [ ] Auth middleware tested: valid key passes, invalid/missing key returns 401

### QA-003: Debate state machine has unit tests
**Persona:** `developer`
**Story:** As a developer, I want the debate state machine to have unit tests for every phase transition, so that the adversarial loop logic is proven correct.
**Acceptance Criteria:**
- [ ] State transitions: IDLE→PERFORMANCE_PULL→GREEN_PROPOSES→RED_CHALLENGES→COORDINATOR_EVALUATES all tested
- [ ] Consensus path tested: coordinator issues CONSENSUS_REACHED → phase = CONSENSUS_LOCKED
- [ ] Max rounds escalation tested: coordinator issues ESCALATE → phase = PENDING_MANUAL_REVIEW
- [ ] State persistence (save/load) tested

### QA-004: Capability guard has test coverage
**Persona:** `developer`
**Story:** As a developer, I want the capability guard to have explicit tests for every blocked and allowed operation, so that we can never accidentally unblock a dangerous operation.
**Acceptance Criteria:**
- [ ] Test: all ALLOWED operations do NOT raise
- [ ] Test: all BLOCKED operations (budget, ad copy, campaign create/delete) raise CAPABILITY_FORBIDDEN
- [ ] New blocked operations added to BLOCKED_OPERATIONS set must trigger a test failure if not added to test coverage
