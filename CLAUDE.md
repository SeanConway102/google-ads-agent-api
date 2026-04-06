# Google Ads Autonomous Agent API — CLAUDE.md

## Project Overview

Autonomous headless Google Ads optimization agent with a three-agent adversarial architecture (Coordinator + Green Team + Red Team). Runs on a Digital Ocean droplet. Manages campaigns via a custom MCP-wrapped Google Ads API.

- **Repo**: `C:/dev/google-ads-agent-api`
- **Spec**: `docs/superpowers/specs/2026-04-06-autonomous-google-ads-agent-design.md`
- **Plan**: `docs/superpowers/plans/2026-04-06-autonomous-google-ads-agent-plan.md`
- **User Stories**: `docs/superpowers/plans/2026-04-06-autonomous-google-ads-agent-user-stories.md`
- **Stack**: Python 3.12, FastAPI, PostgreSQL 16, LangChain DeepAgents, Jina MCP, MiniMax LLM

---

## AI Agent Guardrails — READ FIRST

This project is developed with AI assistance. AI agents produce more bugs when unchecked. These rules exist to counteract that.

### Never Trust AI-Generated Tests at Face Value
- A test that only checks `status code 200` proves nothing — the route could return completely wrong data with a 200
- Every test MUST assert at least one thing beyond status: body structure, specific field values, content-type, or error message
- If AI wrote both the code AND the test, the test is suspect — it confirms what the code does, not what it should do
- Tests that pass on first run without ever failing are a red flag — TDD requires RED (fail) before GREEN (pass)

### Small Commits, Every Commit Reviewable
- Max ~5 files and ~100 changed lines per commit when possible
- Each commit should be independently testable and revertible
- The human must be able to read and understand every diff

### Security Review Every New Endpoint
Every new route must be checked for:
- Authentication: Is it behind API key middleware?
- Authorization: Does it verify access to the requested resource?
- Rate limiting: Can it be abused?
- Input validation: Missing/malformed params handled?
- Information exposure: Does it return more data than needed?

### Error Handling in All Code
Every `httpx`/`requests` call, every async call, every DB operation must have error handling. Silent failures are worse than crashes.

### Context Decay Awareness
Long AI sessions lose context. After major direction changes, re-verify that previously-working code still works. Don't assume earlier changes are still valid.

---

## Development Methodology

This project uses **Red-Green-Refactor TDD** with **Generative Adversarial Validation** at the end of every development tick.

### The Tick Cycle

Every development session follows this exact pattern:

```
┌─────────────────────────────────────────────────────────────┐
│  TICK CYCLE                                                  │
│                                                              │
│  1. WRITE test (.py)  ──► 2. RUN ──► 3. IMPLEMENT (src/)  │
│         │ RED                     GREEN                     │
│         ▼                                                   │
│  4. RUN ──► 5. REFACTOR (if needed) ──► 6. COMMIT           │
│       GREEN                                               │
│         │                                                   │
│         ▼                                                   │
│  7. ADVERSARIAL REVIEW                                     │
│     Green Agent: "This implementation handles all cases"      │
│     Red Agent:  "What about X, Y, Z edge cases?"            │
│     Coordinator: "All concerns addressed. Tick complete."      │
│                                                              │
│  REPEAT for next task                                        │
└─────────────────────────────────────────────────────────────┘
```

### Step 1 — RED: Write the Failing Test
- Write the test BEFORE writing any production code
- The test describes what the code SHOULD do, not what it currently does
- Run the test. Watch it fail with the expected error.
- If it passes without the implementation existing, the test is broken — fix the test

### Step 2 — GREEN: Write Minimum Code
- Write only what's needed to make the test pass
- Do not add "just in case" code, speculative features, or extra validation
- Run the test. It must pass. If not, fix the code, not the test.

### Step 3 — REFACTOR: Clean Up
- Only after tests pass: improve code structure
- Extract middleware, DRY up code, improve naming
- All existing tests must still pass after refactor

### Step 4 — COMMIT: Small and Descriptive
- Commit message describes WHAT changed and WHY
- Reference the user story ID: `git commit -m "feat(campaigns): add POST /campaigns endpoint CM-001"`

### Step 5 — ADVERSARIAL REVIEW (End of Every Tick)
After every commit, before starting the next tick, run the adversarial review:

**Green Agent (proposer):** Reviews the code and says: "This implementation handles the happy path for [feature]."

**Red Agent (challenger):** Actively looks for:
- What edge cases are unhandled? (null inputs, empty lists, duplicate keys, network timeouts)
- What error paths are missing?
- What could break the adversarial loop itself?
- What assumptions were made that could be wrong?

**Coordinator:** Synthesizes. If Red Agent raised valid concerns, they become the next tick's RED tests. If all concerns are addressed, tick is complete.

> **Note:** The adversarial review is a mental process, not a separate agent system. The developer plays all three roles: write the code (green), challenge it (red), and decide if it's ready (coordinator).

---

## Test Suite Structure

```
tests/
  features/                    # Gherkin .feature files (the human-readable specs)
    api-campaigns.feature       # Campaign CRUD API
    api-wiki.feature            # Wiki search and retrieval
    api-webhooks.feature        # Webhook registration and delivery
    api-audit.feature           # Audit log retrieval
    mcp-capabilities.feature    # MCP capability guard
    debate-state.feature        # Three-agent debate state machine
    research-loop.feature       # Daily research cycle
  steps/                       # Python step definitions
    api_steps.py                # Shared API steps (GET, POST, auth, assertions)
    debate_steps.py             # Debate state machine step definitions
    mcp_steps.py               # MCP tool call steps
  support/                     # Test infrastructure
    world.py                   # TestWorld — shared state per scenario
    hooks.py                   # Before/After hooks, environment setup
    config.py                  # Env-var-driven config
  conftest.py                  # Pytest fixtures and configuration
  unit/                        # Pure unit tests (no I/O)
    test_debate_state.py
    test_capability_guard.py
    test_llm_adapter.py
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# CI-equivalent suite (clean output):
pytest tests/ -v --tb=short --no-header

# Unit tests only (no integration):
pytest tests/unit/ -v

# Feature/integration tests:
pytest tests/features/ -v

# Single test file:
pytest tests/unit/test_debate_state.py -v

# With coverage:
pytest tests/ --cov=src --cov-report=term-missing
```

### Test Tags (for future CI integration)

| Tag | Meaning |
|-----|---------|
| `@unit` | Pure unit tests, no I/O |
| `@integration` | Tests that hit DB or network |
| `@slow` | Tests that take >5 seconds |
| `@requires-db` | Needs PostgreSQL running |
| `@requires-mcp` | Needs MCP server running |

---

## Development Workflow by Phase

### Phase 1: Foundation
1. Write `tests/unit/test_config.py` — RED
2. Write `src/config.py` — GREEN
3. Write `src/db/schema.sql` — GREEN
4. Write `tests/unit/test_db_adapter.py` — RED
5. Write `src/db/base.py` + `postgres_adapter.py` — GREEN

### Phase 2: Campaign API
1. Write `tests/features/api-campaigns.feature` — RED (Gherkin)
2. Write `tests/unit/test_api_campaigns.py` — RED (unit)
3. Write `src/api/middleware.py` + `src/api/schemas.py` — GREEN
4. Write `src/api/routes/campaigns.py` — GREEN
5. Write `src/main.py` — GREEN
6. **Adversarial review** — Red Agent challenges: auth bypass? missing 404s? duplicate handling?
7. Commit

### Phase 3: Google Ads MCP
1. Write `tests/unit/test_capability_guard.py` — RED
2. Write `src/mcp/capability_guard.py` — GREEN
3. Write `tests/features/mcp-capabilities.feature` — RED
4. Write `src/mcp/google_ads_client.py` — GREEN
5. Write `src/mcp/tools.py` — GREEN
6. Write `src/mcp/server.py` — GREEN
7. **Adversarial review** — Red Agent: "What if the MCP receives a blocked operation? Is the error structured correctly?"
8. Commit

### Phase 4: Agent System
1. Write `tests/unit/test_llm_adapter.py` — RED
2. Write `src/agents/llm_adapter.py` — GREEN
3. Write `src/agents/prompts.py` — GREEN (prompts are not testable in unit, reviewed manually)
4. Write `tests/unit/test_debate_state.py` — RED
5. Write `src/agents/debate_state.py` — GREEN
6. Write `tests/features/debate-state.feature` — RED
7. Write `src/agents/green_team.py` + `red_team.py` + `coordinator.py` — GREEN
8. **Adversarial review** — Red Agent: "What if Green proposes nothing? What if Red approves everything? What if consensus loops forever?"
9. Commit

### Phase 5: Research Loop
1. Write `tests/features/research-loop.feature` — RED
2. Write `src/research/sources.py` — GREEN
3. Write `src/research/wiki_writer.py` — GREEN
4. Write `src/research/validator.py` — GREEN
5. Write `src/cron/daily_research.py` — GREEN
6. **Adversarial review** — Red Agent: "What if Jina MCP fails? What if wiki write fails mid-cycle?"
7. Commit

### Phase 6: Testing & Deploy
1. Write all remaining integration tests
2. Write `setup_droplet.sh`
3. Write `README.md`
4. Verify all tests pass
5. **Adversarial review** — Full system: "What fails when the droplet reboots? Is the cron resilient to missed runs?"
6. Commit

---

## Code Patterns

### Database
- All DB operations go through `DatabaseAdapter` (`src/db/base.py`)
- PostgreSQL is the default; swap via `DB_PROVIDER` env var
- All queries use parameterized placeholders — NEVER string concatenation
- SQLAlchemy-style raw SQL in `postgres_adapter.py` (no ORM needed for this scale)

### API Routes
- FastAPI with `APIRouter` per resource group
- Pydantic models for all request/response bodies (`src/api/schemas.py`)
- `Depends(get_db)` for database adapter injection
- All routes except `/health` require `X-API-Key` header

### Agents
- All LLM calls go through `src/agents/llm_adapter.py`
- MiniMax adapter is the default; swappable via `LLM_PROVIDER` env var
- All agent prompts defined in `src/agents/prompts.py`
- Debate state persisted to `debate_state` table after every phase transition

### MCP Server
- Runs as a stdio process on the droplet
- Agents communicate via JSON-RPC over stdio
- `CapabilityGuard` is the only gatekeeper — blocked operations raise `CAPABILITY_FORBIDDEN`

### Error Handling
- All `httpx`/`requests` calls wrapped in try/except
- All DB operations use context managers
- Structured errors: `CAPABILITY_FORBIDDEN`, `AppError`, `ValidationError`
- Errors are never silently swallowed

---

## Never Do These Things

| Rule | Why |
|------|-----|
| Write code before writing the test | Tests-after only prove what code does, not what it should do |
| Commit without running tests | Broken code in main blocks the whole team |
| Add a new package without checking if existing one works | Avoid dependency sprawl |
| Bypass the adversarial review step | Red Team catches real bugs — don't skip it |
| Return raw database errors to API clients | Information exposure risk |
| Use string concatenation in SQL | SQL injection vulnerability |
| Change the DB schema without updating schema.sql | Schema drift breaks environments |

---

## Process Safety

- NEVER use `taskkill //F //IM python.exe` — use `python -m pytest` with proper process management
- If PostgreSQL is not running: `sudo systemctl start postgresql`
- If the API crashes on startup: check `.env` has all required variables
- If cron doesn't fire: check `sudo systemctl status cron` and `sudo journalctl -u ads-research`

---

## Key Files

| File | Purpose |
|------|---------|
| `src/config.py` | All environment variable loading + validation |
| `src/db/schema.sql` | All PostgreSQL table definitions |
| `src/db/base.py` | Abstract database interface |
| `src/db/postgres_adapter.py` | PostgreSQL implementation |
| `src/api/middleware.py` | X-API-Key authentication |
| `src/api/routes/campaigns.py` | Campaign CRUD endpoints |
| `src/agents/llm_adapter.py` | LLM abstraction (MiniMax, OpenAI, Anthropic) |
| `src/agents/debate_state.py` | Debate state machine |
| `src/agents/coordinator.py` | Coordinator agent |
| `src/agents/green_team.py` | Green Team agent |
| `src/agents/red_team.py` | Red Team agent |
| `src/mcp/capability_guard.py` | Blocks forbidden Google Ads operations |
| `src/mcp/server.py` | MCP stdio server entry point |
| `src/cron/daily_research.py` | Daily research cycle orchestration |
| `setup_droplet.sh` | Droplet provisioning script |
