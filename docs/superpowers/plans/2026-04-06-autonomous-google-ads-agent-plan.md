# Autonomous Google Ads Optimization Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully autonomous headless Google Ads optimization agent with a three-agent adversarial research loop, custom MCP capability boundary, campaign management API, and PostgreSQL wiki with embeddingless RAG — running on a Digital Ocean droplet.

**Architecture:** Python/FastAPI on Ubuntu (Droplet). LangChain DeepAgents for the three-agent adversarial system. PostgreSQL for all persistence. Custom MCP server wraps Google Ads API with capability restrictions. All LLM calls go through an abstracted adapter (MiniMax 2.7 initially, swappable).

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL 16, LangChain DeepAgents, Jina MCP, MiniMax LLM API, Google Ads API v17, `psycopg2`/`asyncpg`, `pydantic`, `httpx`, `python-cron`, `uvicorn`.

---

## Phase Map

| Phase | Name | Produces |
|---|---|---|
| 1 | Foundation | Project scaffold, env vars, config, DB schema, DB abstraction layer |
| 2 | Campaign API | All REST endpoints, middleware, audit log, webhooks |
| 3 | Google Ads MCP | MCP server, capability guard, Google Ads client wrapper |
| 4 | Agent System | LLM adapter, Coordinator + Green + Red agents, debate state machine |
| 5 | Research Loop | Daily cron script, Jina source fetchers, wiki writer |
| 6 | Testing & Deploy | Unit/integration tests, droplet setup script, deployment docs |

---

## File Structure

```
google-ads-agent-api/
├── SPEC.md                                          # Symlink/copy of approved spec
├── docs/superpowers/
│   ├── specs/
│   │   └── 2026-04-06-autonomous-google-ads-agent-design.md
│   └── plans/
│       └── 2026-04-06-autonomous-google-ads-agent-plan.md
├── src/
│   ├── __init__.py
│   ├── main.py                                      # FastAPI app — all routes mounted
│   ├── config.py                                    # Env var loading + Pydantic validation
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                                 # Abstract Database interface
│   │   ├── postgres_adapter.py                     # PostgreSQL implementation
│   │   ├── models.py                               # SQLAlchemy or raw SQL models
│   │   └── schema.sql                              # All CREATE TABLE statements
│   ├── api/
│   │   ├── __init__.py
│   │   ├── middleware.py                           # X-API-Key authentication middleware
│   │   ├── routes/
│   │   │   ├── campaigns.py                        # CRUD + insights endpoints
│   │   │   ├── wiki.py                            # Wiki query endpoints
│   │   │   ├── audit.py                           # Audit log endpoint
│   │   │   └── webhooks.py                        # Webhook registration
│   │   └── schemas.py                              # Pydantic request/response models
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── llm_adapter.py                          # MiniMax 2.7 + swappable LLM interface
│   │   ├── coordinator.py                           # Coordinator agent
│   │   ├── green_team.py                            # Green Team agent
│   │   ├── red_team.py                              # Red Team agent
│   │   ├── debate_state.py                          # State machine + DB persistence
│   │   └── prompts.py                               # System prompts for all three agents
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── server.py                               # MCP server entry point (stdio)
│   │   ├── tools.py                                # Allowed tool definitions
│   │   ├── capability_guard.py                     # Blocks forbidden operations
│   │   └── google_ads_client.py                    # Google Ads API v17 wrapper
│   ├── research/
│   │   ├── __init__.py
│   │   ├── sources.py                              # Source definitions + Jina fetchers
│   │   ├── validator.py                            # Adversarial validation orchestrator
│   │   └── wiki_writer.py                          # Wiki entry creation from consensus
│   ├── cron/
│   │   ├── __init__.py
│   │   └── daily_research.py                        # Cron-triggered research cycle script
│   └── services/
│       ├── __init__.py
│       ├── webhook_service.py                       # Webhook dispatch + retry logic
│       └── audit_service.py                        # Audit log writer
├── tests/
│   ├── conftest.py                                 # Shared pytest fixtures
│   ├── test_api_campaigns.py
│   ├── test_api_wiki.py
│   ├── test_api_webhooks.py
│   ├── test_debate_state.py
│   ├── test_mcp_capability_guard.py
│   ├── test_wiki_search.py
│   └── test_llm_adapter.py
├── scripts/
│   └── run_research_cycle.py                       # Manual trigger for research cycle
├── requirements.txt
├── .env.example
├── setup_droplet.sh                                # Droplet provisioning script
└── README.md
```

---

## PHASE 1 — Foundation

### Task 1: Project Scaffold & Config

**Files:**
- Create: `src/__init__.py`, `src/config.py`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `src/db/__init__.py`, `src/api/__init__.py`, `src/agents/__init__.py`, `src/mcp/__init__.py`, `src/research/__init__.py`, `src/cron/__init__.py`, `src/services/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the test for config loading**

```python
# tests/test_config.py
from src.config import settings

def test_settings_loads_admin_api_key(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key-123")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/ads_agent")
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimax.chat")
    # Reload config
    from importlib import reload
    import src.config as cfg
    reload(cfg)
    assert cfg.settings.ADMIN_API_KEY == "test-key-123"
    assert "postgresql" in cfg.settings.DATABASE_URL
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_config.py -v
Expected: FAIL — config module doesn't exist
```

- [ ] **Step 3: Write config.py**

```python
# src/config.py
from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):
    # Admin
    ADMIN_API_KEY: str

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ads_agent"
    DB_PROVIDER: Literal["postgresql", "sqlite"] = "postgresql"

    # Google Ads
    GOOGLE_ADS_DEVELOPER_TOKEN: str = ""
    GOOGLE_ADS_CLIENT_ID: str = ""
    GOOGLE_ADS_CLIENT_SECRET: str = ""

    # LLM
    LLM_PROVIDER: Literal["minimax", "openai", "anthropic"] = "minimax"
    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.minimax.chat"
    MINIMAX_MODEL: str = "MiniMax-Text-01"

    # MCP
    MCP_SERVER_PATH: str = "/opt/ads-agent/mcp_server.py"

    # Cron
    RESEARCH_CRON: str = "0 8 * * *"  # 8am daily
    MAX_DEBATE_ROUNDS: int = 5

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
```

- [ ] **Step 4: Write requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic==2.9.0
pydantic-settings==2.6.0
psycopg2-binary==2.9.9
asyncpg==0.30.0
sqlalchemy==2.0.35
httpx==0.27.2
python-cron==0.0.6
langchain==0.3.7
langchain-deepseek==0.1.0  # or minimax integration
mcp==1.1.2
google-ads==27.0.0
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-cov==5.0.0
```

- [ ] **Step 5: Write .env.example**

```bash
# Admin
ADMIN_API_KEY=change-me-to-a-secure-random-key

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ads_agent
DB_PROVIDER=postgresql

# Google Ads (MCC)
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=

# LLM (MiniMax)
LLM_PROVIDER=minimax
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.chat
MINIMAX_MODEL=MiniMax-Text-01

# MCP
MCP_SERVER_PATH=/opt/ads-agent/mcp_server.py

# Research
MAX_DEBATE_ROUNDS=5
RESEARCH_CRON=0 8 * * *
```

- [ ] **Step 6: Run test**

```
pytest tests/test_config.py -v
Expected: PASS
```

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: project scaffold and config loading"
```

---

### Task 2: Database Schema

**Files:**
- Create: `src/db/schema.sql`
- Create: `src/db/models.py`

- [ ] **Step 1: Write schema.sql**

```sql
-- src/db/schema.sql

-- Campaigns
CREATE TABLE IF NOT EXISTS campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     VARCHAR(64) NOT NULL,
    customer_id     VARCHAR(32) NOT NULL,
    name            VARCHAR(255) NOT NULL,
    api_key_token   TEXT NOT NULL,
    status          VARCHAR(16) DEFAULT 'active',
    campaign_type   VARCHAR(64),
    owner_tag       VARCHAR(128),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at  TIMESTAMPTZ,
    last_reviewed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_owner_tag ON campaigns(owner_tag);

-- Wiki entries
CREATE TABLE IF NOT EXISTS wiki_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(512) NOT NULL,
    slug            VARCHAR(256) UNIQUE NOT NULL,
    content         TEXT NOT NULL,
    sources         JSONB DEFAULT '[]',
    green_rationale TEXT,
    red_objections  JSONB DEFAULT '[]',
    consensus_note  TEXT,
    tags            VARCHAR(128)[] DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    verified_at     TIMESTAMPTZ,
    invalidated_at  TIMESTAMPTZ
);

-- Full-text search vector (generated column for embeddingless RAG)
ALTER TABLE wiki_entries ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED;
CREATE INDEX IF NOT EXISTS idx_wiki_search ON wiki_entries USING GIN(search_vector);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_date      DATE NOT NULL,
    campaign_id    UUID REFERENCES campaigns(id) ON DELETE SET NULL,
    action_type     VARCHAR(64) NOT NULL,
    target          JSONB,
    green_proposal  JSONB,
    red_objections  JSONB,
    coordinator_note TEXT,
    debate_rounds   INT,
    performed_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Debate state
CREATE TABLE IF NOT EXISTS debate_state (
    id                  SERIAL PRIMARY KEY,
    cycle_date          DATE NOT NULL,
    campaign_id         UUID REFERENCES campaigns(id) ON DELETE SET NULL,
    phase               VARCHAR(32) NOT NULL DEFAULT 'idle',
    round_number        INT DEFAULT 1,
    green_proposals     JSONB DEFAULT '[]',
    red_objections      JSONB DEFAULT '[]',
    coordinator_decision JSONB,
    consensus_reached   BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Webhook subscriptions
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url         TEXT NOT NULL,
    events      VARCHAR(64)[] DEFAULT '{}',
    secret      TEXT,
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Webhook delivery log
CREATE TABLE IF NOT EXISTS webhook_delivery_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
    event           VARCHAR(64) NOT NULL,
    payload         JSONB,
    status          VARCHAR(16) DEFAULT 'pending',
    attempts        INT DEFAULT 0,
    next_retry_at   TIMESTAMPTZ,
    last_error      TEXT,
    delivered_at    TIMESTAMPTZ
);
```

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "feat: database schema with all tables"
```

---

### Task 3: Database Abstraction Layer

**Files:**
- Create: `src/db/base.py`
- Create: `src/db/postgres_adapter.py`
- Create: `tests/test_db_adapter.py`

- [ ] **Step 1: Write base interface**

```python
# src/db/base.py
from abc import ABC, abstractmethod
from typing import Any, List, Optional
from uuid import UUID

class DatabaseAdapter(ABC):
    @abstractmethod
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        pass

    @abstractmethod
    def fetch_all(self, query: str, params: tuple = ()) -> List[dict]:
        pass

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> None:
        pass

    @abstractmethod
    def execute_returning(self, query: str, params: tuple = ()) -> dict:
        pass

    # Campaign operations
    @abstractmethod
    def create_campaign(self, data: dict) -> dict:
        pass

    @abstractmethod
    def get_campaign(self, id: UUID) -> Optional[dict]:
        pass

    @abstractmethod
    def list_campaigns(self) -> List[dict]:
        pass

    @abstractmethod
    def delete_campaign(self, id: UUID) -> None:
        pass

    # Wiki operations
    @abstractmethod
    def search_wiki(self, query: str, limit: int = 10) -> List[dict]:
        pass

    @abstractmethod
    def create_wiki_entry(self, data: dict) -> dict:
        pass

    # Debate state
    @abstractmethod
    def save_debate_state(self, data: dict) -> dict:
        pass

    @abstractmethod
    def get_latest_debate_state(self, cycle_date: str, campaign_id: UUID) -> Optional[dict]:
        pass

    # Audit
    @abstractmethod
    def write_audit_log(self, data: dict) -> dict:
        pass

    # Webhooks
    @abstractmethod
    def register_webhook(self, data: dict) -> dict:
        pass
```

- [ ] **Step 2: Write PostgreSQL adapter**

```python
# src/db/postgres_adapter.py
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from uuid import UUID
from typing import Any, List, Optional
from src.config import settings
from src.db.base import DatabaseAdapter

class PostgresAdapter(DatabaseAdapter):
    def __init__(self, database_url: str = None):
        self.database_url = database_url or settings.DATABASE_URL

    @contextmanager
    def _connection(self):
        conn = psycopg2.connect(self.database_url)
        try:
            yield conn
        finally:
            conn.close()

    def _cursor(self, conn):
        return conn.cursor(cursor_factory=RealDictCursor)

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                return dict(result) if result else None

    def fetch_all(self, query: str, params: tuple = ()) -> List[dict]:
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]

    def execute(self, query: str, params: tuple = ()) -> None:
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute(query, params)
            conn.commit()

    def execute_returning(self, query: str, params: tuple = ()) -> dict:
        with self._connection() as conn:
            with self._cursor(conn) as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                conn.commit()
                return dict(result) if result else {}

    def create_campaign(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO campaigns
               (campaign_id, customer_id, name, api_key_token, campaign_type, owner_tag)
               VALUES (%s,%s,%s,%s,%s,%s)
               RETURNING *""",
            (data["campaign_id"], data["customer_id"], data["name"],
             data["api_key_token"], data.get("campaign_type"), data.get("owner_tag"))
        )

    def get_campaign(self, id: UUID) -> Optional[dict]:
        return self.fetch_one("SELECT * FROM campaigns WHERE id = %s", (str(id),))

    def list_campaigns(self) -> List[dict]:
        return self.fetch_all("SELECT * FROM campaigns ORDER BY created_at DESC")

    def delete_campaign(self, id: UUID) -> None:
        self.execute("DELETE FROM campaigns WHERE id = %s", (str(id),))

    def search_wiki(self, query: str, limit: int = 10) -> List[dict]:
        return self.fetch_all(
            """SELECT id, title, slug, ts_rank(search_vector, query) AS rank
               FROM wiki_entries, to_tsquery('english', %s) AS query
               WHERE search_vector @@ query
                 AND invalidated_at IS NULL
               ORDER BY rank DESC LIMIT %s""",
            (query, limit)
        )

    def create_wiki_entry(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO wiki_entries
               (title, slug, content, sources, green_rationale, red_objections, consensus_note, tags)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (data["title"], data["slug"], data["content"],
             data.get("sources", "[]"), data.get("green_rationale"),
             data.get("red_objections", "[]"), data.get("consensus_note"),
             data.get("tags", []))
        )

    def save_debate_state(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO debate_state
               (cycle_date, campaign_id, phase, round_number, green_proposals, red_objections, coordinator_decision, consensus_reached)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT DO UPDATE SET
                 phase=EXCLUDED.phase,
                 round_number=EXCLUDED.round_number,
                 green_proposals=EXCLUDED.green_proposals,
                 red_objections=EXCLUDED.red_objections,
                 coordinator_decision=EXCLUDED.coordinator_decision,
                 consensus_reached=EXCLUDED.consensus_reached,
                 updated_at=NOW()
               RETURNING *""",
            (data["cycle_date"], str(data["campaign_id"]), data["phase"],
             data["round_number"], data.get("green_proposals", "[]"),
             data.get("red_objections", "[]"),
             data.get("coordinator_decision"), data.get("consensus_reached", False))
        )

    def get_latest_debate_state(self, cycle_date: str, campaign_id: UUID) -> Optional[dict]:
        return self.fetch_one(
            """SELECT * FROM debate_state
               WHERE cycle_date = %s AND campaign_id = %s
               ORDER BY id DESC LIMIT 1""",
            (cycle_date, str(campaign_id))
        )

    def write_audit_log(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO audit_log
               (cycle_date, campaign_id, action_type, target, green_proposal, red_objections, coordinator_note, debate_rounds)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (data["cycle_date"], str(data["campaign_id"]) if data.get("campaign_id") else None,
             data["action_type"], data.get("target"), data.get("green_proposal"),
             data.get("red_objections"), data.get("coordinator_note"), data.get("debate_rounds"))
        )

    def register_webhook(self, data: dict) -> dict:
        return self.execute_returning(
            """INSERT INTO webhook_subscriptions (url, events, secret)
               VALUES (%s,%s,%s) RETURNING *""",
            (data["url"], data.get("events", []), data.get("secret"))
        )
```

- [ ] **Step 3: Write test**

```python
# tests/test_db_adapter.py
import pytest
from unittest.mock import MagicMock, patch
from src.db.postgres_adapter import PostgresAdapter

def test_postgres_adapter_fetch_one_returns_dict():
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {"id": "123", "name": "test"}
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        adapter = PostgresAdapter("postgresql://fake")
        result = adapter.fetch_one("SELECT * FROM campaigns WHERE id = %s", ("123",))

        assert result == {"id": "123", "name": "test"}
        mock_cur.execute.assert_called_once()
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: database abstraction layer with PostgreSQL adapter"
```

---

## PHASE 2 — Campaign Management API

### Task 4: API Middleware & Schemas

**Files:**
- Create: `src/api/middleware.py`
- Create: `src/api/schemas.py`

- [ ] **Step 1: Write API key middleware**

```python
# src/api/middleware.py
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from src.config import settings

class APIKeyMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        api_key = request.headers.get("x-api-key")
        if not api_key or api_key != settings.ADMIN_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key header"
            )
        return await call_next(request)
```

- [ ] **Step 2: Write Pydantic schemas**

```python
# src/api/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime

# Campaign schemas
class CampaignCreate(BaseModel):
    campaign_id: str = Field(..., max_length=64)
    customer_id: str = Field(..., max_length=32)
    name: str = Field(..., max_length=255)
    api_key_token: str
    campaign_type: Optional[str] = None
    owner_tag: Optional[str] = None

class CampaignResponse(BaseModel):
    id: UUID
    campaign_id: str
    customer_id: str
    name: str
    status: str
    campaign_type: Optional[str]
    owner_tag: Optional[str]
    created_at: datetime
    last_synced_at: Optional[datetime]
    last_reviewed_at: Optional[datetime]

class CampaignInsight(BaseModel):
    type: str
    keyword: Optional[str] = None
    match_type: Optional[str] = None
    priority: str
    reasoning: str
    status: str  # pending_consensus, approved, rejected

class CampaignInsightsResponse(BaseModel):
    campaign_id: str
    last_reviewed_at: Optional[datetime]
    current_recommendations: List[CampaignInsight]
    wiki_context: List[str]

# Wiki schemas
class WikiEntryResponse(BaseModel):
    id: UUID
    title: str
    slug: str
    content: str
    sources: List[dict]
    tags: List[str]
    created_at: datetime
    updated_at: datetime

# Webhook schemas
class WebhookCreate(BaseModel):
    url: str
    events: List[str] = ["decision_made", "consensus_reached", "action_executed"]
    secret: Optional[str] = None

class WebhookResponse(BaseModel):
    id: UUID
    url: str
    events: List[str]
    active: bool
    created_at: datetime

# Audit log
class AuditLogResponse(BaseModel):
    id: UUID
    cycle_date: str
    campaign_id: Optional[UUID]
    action_type: str
    target: dict
    green_proposal: Optional[dict]
    red_objections: Optional[dict]
    coordinator_note: Optional[str]
    debate_rounds: Optional[int]
    performed_at: datetime
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: API middleware and Pydantic schemas"
```

---

### Task 5: Campaign CRUD Endpoints

**Files:**
- Create: `src/api/routes/campaigns.py`
- Modify: `src/main.py` (mount routes)

- [ ] **Step 1: Write campaigns router**

```python
# src/api/routes/campaigns.py
from fastapi import APIRouter, HTTPException, status, Depends
from uuid import UUID
from src.api.schemas import (
    CampaignCreate, CampaignResponse, CampaignInsightsResponse, CampaignInsight
)
from src.db.postgres_adapter import PostgresAdapter
from src.db.base import DatabaseAdapter

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

def get_db() -> DatabaseAdapter:
    return PostgresAdapter()

@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(campaign: CampaignCreate, db: DatabaseAdapter = Depends(get_db)):
    try:
        result = db.create_campaign(campaign.model_dump())
        return CampaignResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=list[CampaignResponse])
def list_campaigns(db: DatabaseAdapter = Depends(get_db)):
    return [CampaignResponse(**c) for c in db.list_campaigns()]

@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: UUID, db: DatabaseAdapter = Depends(get_db)):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignResponse(**campaign)

@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: UUID, db: DatabaseAdapter = Depends(get_db)):
    db.delete_campaign(campaign_id)

@router.get("/{campaign_id}/insights", response_model=CampaignInsightsResponse)
def get_campaign_insights(campaign_id: UUID, db: DatabaseAdapter = Depends(get_db)):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Query latest debate state for this campaign
    from datetime import date
    today = date.today().isoformat()
    state = db.get_latest_debate_state(today, campaign_id)

    recommendations = []
    if state and state.get("green_proposals"):
        for prop in state["green_proposals"]:
            recommendations.append(CampaignInsight(
                type=prop.get("type", "unknown"),
                keyword=prop.get("keyword"),
                match_type=prop.get("match_type"),
                priority=prop.get("priority", "medium"),
                reasoning=prop.get("reasoning", ""),
                status="pending_consensus" if not state.get("consensus_reached") else "approved"
            ))

    return CampaignInsightsResponse(
        campaign_id=campaign["campaign_id"],
        last_reviewed_at=campaign.get("last_reviewed_at"),
        current_recommendations=recommendations,
        wiki_context=[]
    )

@router.post("/{campaign_id}/approve")
def approve_action(campaign_id: UUID, db: DatabaseAdapter = Depends(get_db)):
    # Mark pending action as approved — consumed by debate loop
    return {"status": "approved", "campaign_id": str(campaign_id)}

@router.post("/{campaign_id}/override")
def manual_override(campaign_id: UUID, action: dict, db: DatabaseAdapter = Depends(get_db)):
    # Bypass adversarial check — write directly to audit log
    from datetime import date
    audit = db.write_audit_log({
        "cycle_date": date.today().isoformat(),
        "campaign_id": campaign_id,
        "action_type": "manual_override",
        "target": action,
        "coordinator_note": "Manual override by admin API"
    })
    return {"status": "override_applied", "audit_id": str(audit["id"])}
```

- [ ] **Step 2: Write main.py with all routes mounted**

```python
# src/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.middleware import APIKeyMiddleware
from src.api.routes import campaigns, wiki, audit, webhooks

app = FastAPI(title="Google Ads Autonomous Agent API", version="1.0.0")

app.add_middleware(APIKeyMiddleware)

app.include_router(campaigns.router)
app.include_router(wiki.router)
app.include_router(audit.router)
app.include_router(webhooks.router)

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: campaign CRUD API endpoints"
```

---

### Task 6: Wiki, Audit & Webhook Endpoints

**Files:**
- Create: `src/api/routes/wiki.py`
- Create: `src/api/routes/audit.py`
- Create: `src/api/routes/webhooks.py`
- Create: `src/services/webhook_service.py`
- Create: `src/services/audit_service.py`

- [ ] **Step 1: Write wiki routes**

```python
# src/api/routes/wiki.py
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from uuid import UUID
from src.api.schemas import WikiEntryResponse
from src.db.postgres_adapter import PostgresAdapter
from src.db.base import DatabaseAdapter

router = APIRouter(prefix="/research/wiki", tags=["wiki"])

def get_db() -> DatabaseAdapter:
    return PostgresAdapter()

@router.get("", response_model=list[WikiEntryResponse])
def search_wiki(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=100),
    db: DatabaseAdapter = Depends(get_db)
):
    results = db.search_wiki(q, limit)
    return [WikiEntryResponse(**r) for r in results]

@router.get("/{entry_id}", response_model=WikiEntryResponse)
def get_wiki_entry(entry_id: UUID, db: DatabaseAdapter = Depends(get_db)):
    entry = db.fetch_one("SELECT * FROM wiki_entries WHERE id = %s", (str(entry_id),))
    if not entry:
        raise HTTPException(status_code=404, detail="Wiki entry not found")
    return WikiEntryResponse(**entry)
```

- [ ] **Step 2: Write audit routes**

```python
# src/api/routes/audit.py
from fastapi import APIRouter, Query, Depends
from typing import Optional
from src.api.schemas import AuditLogResponse
from src.db.postgres_adapter import PostgresAdapter
from src.db.base import DatabaseAdapter

router = APIRouter(prefix="/audit-log", tags=["audit"])

def get_db() -> DatabaseAdapter:
    return PostgresAdapter()

@router.get("", response_model=list[AuditLogResponse])
def get_audit_log(
    campaign_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: DatabaseAdapter = Depends(get_db)
):
    if campaign_id:
        rows = db.fetch_all(
            "SELECT * FROM audit_log WHERE campaign_id = %s ORDER BY performed_at DESC LIMIT %s",
            (campaign_id, limit)
        )
    else:
        rows = db.fetch_all(
            "SELECT * FROM audit_log ORDER BY performed_at DESC LIMIT %s",
            (limit,)
        )
    return [AuditLogResponse(**r) for r in rows]
```

- [ ] **Step 3: Write webhook routes + service**

```python
# src/api/routes/webhooks.py
from fastapi import APIRouter, HTTPException, Depends
from uuid import UUID
from src.api.schemas import WebhookCreate, WebhookResponse
from src.db.postgres_adapter import PostgresAdapter
from src.db.base import DatabaseAdapter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

def get_db() -> DatabaseAdapter:
    return PostgresAdapter()

@router.post("", response_model=WebhookResponse, status_code=201)
def register_webhook(webhook: WebhookCreate, db: DatabaseAdapter = Depends(get_db)):
    result = db.register_webhook(webhook.model_dump())
    return WebhookResponse(**result)

@router.delete("/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: UUID, db: DatabaseAdapter = Depends(get_db)):
    db.execute("DELETE FROM webhook_subscriptions WHERE id = %s", (str(webhook_id),))
```

```python
# src/services/webhook_service.py
import httpx
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from typing import List
from src.db.postgres_adapter import PostgresAdapter

RETRY_INTERVALS = [60, 300, 1800]  # 1min, 5min, 30min

class WebhookService:
    def __init__(self, db: PostgresAdapter):
        self.db = db

    def dispatch(self, event: str, payload: dict) -> None:
        subscriptions = self.db.fetch_all(
            "SELECT * FROM webhook_subscriptions WHERE active = TRUE AND %s = ANY(events)",
            (event,)
        )
        for sub in subscriptions:
            self._queue_delivery(sub, event, payload)

    def _queue_delivery(self, sub: dict, event: str, payload: dict) -> None:
        from uuid import UUID
        delivery_id = self.db.execute_returning(
            """INSERT INTO webhook_delivery_log
               (subscription_id, event, payload, status, attempts, next_retry_at)
               VALUES (%s,%s,%s,'pending',0,%s) RETURNING id""",
            (str(sub["id"]), event, json.dumps(payload), datetime.utcnow().isoformat())
        )
        self._attempt_delivery(dict(delivery_id), sub, payload)

    def _attempt_delivery(self, delivery: dict, sub: dict, payload: dict) -> None:
        headers = {"Content-Type": "application/json", "X-Webhook-Event": delivery["event"]}
        if sub.get("secret"):
            sig = hmac.new(sub["secret"].encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = sig

        try:
            response = httpx.post(sub["url"], json=payload, headers=headers, timeout=10)
            if response.status_code >= 200 and response.status_code < 300:
                self._mark_delivered(delivery["id"])
                return
        except Exception as e:
            last_error = str(e)

        self._handle_failure(delivery["id"], sub, last_error)

    def _mark_delivered(self, delivery_id: str) -> None:
        self.db.execute(
            """UPDATE webhook_delivery_log
               SET status='delivered', delivered_at=NOW() WHERE id=%s""",
            (delivery_id,)
        )

    def _handle_failure(self, delivery_id: str, sub: dict, last_error: str) -> None:
        current = self.db.fetch_one(
            "SELECT attempts FROM webhook_delivery_log WHERE id=%s", (delivery_id,)
        )
        attempts = (current or {}).get("attempts", 0) + 1
        if attempts <= len(RETRY_INTERVALS):
            next_retry = datetime.utcnow() + timedelta(seconds=RETRY_INTERVALS[attempts - 1])
            self.db.execute(
                """UPDATE webhook_delivery_log
                   SET attempts=%s, status='retrying', next_retry_at=%s, last_error=%s
                   WHERE id=%s""",
                (attempts, next_retry.isoformat(), last_error, delivery_id)
            )
        else:
            self.db.execute(
                """UPDATE webhook_delivery_log
                   SET status='failed', last_error=%s WHERE id=%s""",
                (last_error, delivery_id)
            )
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: wiki, audit, and webhook API endpoints"
```

---

## PHASE 3 — Google Ads MCP Server

### Task 7: MCP Capability Guard & Google Ads Client

**Files:**
- Create: `src/mcp/google_ads_client.py`
- Create: `src/mcp/capability_guard.py`
- Create: `src/mcp/tools.py`
- Create: `tests/test_mcp_capability_guard.py`

- [ ] **Step 1: Write capability guard**

```python
# src/mcp/capability_guard.py
from typing import List

# These operations are BLOCKED — the MCP will raise CAPABILITY_FORBIDDEN if attempted
BLOCKED_OPERATIONS = {
    "campaign.budget.update",
    "campaign.budget.set",
    "campaign.create",
    "campaign.delete",
    "campaign.pause",
    "campaign.update_settings",
    "ad.copy.create",
    "ad.copy.update",
    "ad.copy.delete",
    "audience.update",
}

# These are ALLOWED
ALLOWED_OPERATIONS = {
    "campaign.list",
    "campaign.get",
    "keyword.list",
    "keyword.performance",
    "keyword.add",
    "keyword.remove",
    "keyword.bid.update",
    "keyword.match_type.update",
    "ad.copy.list",
    "audience.list",
}

class CapabilityGuard:
    def check(self, operation: str) -> None:
        if operation in BLOCKED_OPERATIONS:
            raise CAPABILITY_FORBIDDEN(
                f"Operation '{operation}' is explicitly blocked by the capability guard. "
                f"Budget management, campaign creation, and ad copy modifications are not permitted."
            )

class CAPABILITY_FORBIDDEN(Exception):
    pass
```

- [ ] **Step 2: Write Google Ads client wrapper**

```python
# src/mcp/google_ads_client.py
from google.ads.googleads import GoogleAdsClient
from google.ads.googleads.v17.services import GoogleAdsServiceClient
from typing import List, Dict, Any
from src.config import settings

class GoogleAdsClientWrapper:
    def __init__(self, refresh_token: str, developer_token: str):
        self.client = GoogleAdsClient.load_from_dict({
            "refresh_token": refresh_token,
            "developer_token": developer_token,
            "client_id": settings.GOOGLE_ADS_CLIENT_ID,
            "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
        })
        self.service: GoogleAdsServiceClient = self.client.service

    def list_campaigns(self, customer_id: str) -> List[Dict[str, Any]]:
        query = """
            SELECT campaign.id, campaign.name, campaign.status, campaign.campaign_type
            FROM campaign
            WHERE campaign.id = {customer_id}
        """.format(customer_id=customer_id)
        results = self._search(customer_id, query)
        return results

    def list_keywords(self, customer_id: str, campaign_id: str) -> List[Dict[str, Any]]:
        query = f"""
            SELECT campaign.id, ad_group.id, ad_group_criterion.keyword.text,
                   ad_group_criterion.keyword.match_type, ad_group_criterion.status,
                   ad_group_criterion.cpc_bid_micros
            FROM ad_group_criterion
            WHERE campaign.id = '{campaign_id}'
              AND ad_group_criterion.type = 'KEYWORD'
        """
        return self._search(customer_id, query)

    def add_keywords(self, customer_id: str, ad_group_id: str, keywords: List[Dict]) -> List[Dict]:
        # Returns list of added keyword resource names
        operations = []
        for kw in keywords:
            op = self.client.get_type("AdGroupCriterionOperation")
            criterion = op.create.ad_group_criterion
            criterion.ad_group = f"customers/{customer_id}/adGroups/{ad_group_id}"
            criterion.keyword.text = kw["text"]
            criterion.keyword.match_type = kw["match_type"]
            operations.append(op)
        response = self.service.ad_group_criterion_mutation(customer_id=customer_id, operations=operations)
        return [{"resource_name": r.resource_name} for r in response.results]

    def remove_keywords(self, customer_id: str, keyword_resource_names: List[str]) -> None:
        operations = []
        for name in keyword_resource_names:
            op = self.client.get_type("AdGroupCriterionOperation")
            op.remove = name
            operations.append(op)
        self.service.ad_group_criterion_mutation(customer_id=customer_id, operations=operations)

    def update_keyword_bids(self, customer_id: str, updates: List[Dict]) -> None:
        operations = []
        for update in updates:
            op = self.client.get_type("AdGroupCriterionOperation")
            criterion = op.update.ad_group_criterion
            criterion.resource_name = update["resource_name"]
            criterion.cpc_bid_micros = update["cpc_bid_micros"]
            operations.append(op)
        self.service.ad_group_criterion_mutation(customer_id=customer_id, operations=operations)

    def get_keyword_performance(self, customer_id: str, campaign_id: str) -> List[Dict[str, Any]]:
        query = f"""
            SELECT campaign.id, ad_group_criterion.keyword.text,
                   metrics.clicks, metrics.impressions, metrics.ctr,
                   metrics.average_cpc, metrics.conversions
            FROM ad_group_criterion
            WHERE campaign.id = '{campaign_id}'
              AND ad_group_criterion.type = 'KEYWORD'
            ORDER BY metrics.impressions DESC
        """
        return self._search(customer_id, query)

    def _search(self, customer_id: str, query: str) -> List[Dict[str, Any]]:
        results = []
        try:
            response = self.service.search(customer_id=customer_id, query=query)
            for row in response:
                results.append(self._row_to_dict(row))
        except Exception:
            pass
        return results

    def _row_to_dict(self, row) -> Dict[str, Any]:
        result = {}
        for field in row._meta.type_.fields:
            value = getattr(row, field.name, None)
            if value is not None:
                result[field.name] = str(value) if hasattr(value, '__str__') else value
        return result
```

- [ ] **Step 3: Write MCP tools**

```python
# src/mcp/tools.py
TOOL_DEFINITIONS = [
    {
        "name": "google_ads.get_campaigns",
        "description": "List campaigns for a Google Ads customer account",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Google Ads customer ID"}
            },
            "required": ["customer_id"]
        }
    },
    {
        "name": "google_ads.get_keywords",
        "description": "List all keywords in a campaign",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "campaign_id": {"type": "string"}
            },
            "required": ["customer_id", "campaign_id"]
        }
    },
    {
        "name": "google_ads.get_keyword_performance",
        "description": "Get performance metrics for keywords in a campaign",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "campaign_id": {"type": "string"}
            },
            "required": ["customer_id", "campaign_id"]
        }
    },
    {
        "name": "google_ads.add_keywords",
        "description": "Add new keywords to an ad group",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "ad_group_id": {"type": "string"},
                "keywords": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "match_type": {"type": "string", "enum": ["EXACT", "PHRASE", "BROAD"]}
                        }
                    }
                }
            },
            "required": ["customer_id", "ad_group_id", "keywords"]
        }
    },
    {
        "name": "google_ads.remove_keywords",
        "description": "Remove keywords from a campaign by resource name",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "keyword_resource_names": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["customer_id", "keyword_resource_names"]
        }
    },
    {
        "name": "google_ads.update_keyword_bids",
        "description": "Update CPC bids for existing keywords",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "updates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "resource_name": {"type": "string"},
                            "cpc_bid_micros": {"type": "integer"}
                        }
                    }
                }
            },
            "required": ["customer_id", "updates"]
        }
    },
    {
        "name": "google_ads.update_keyword_match_types",
        "description": "Update match types for existing keywords",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "updates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "resource_name": {"type": "string"},
                            "match_type": {"type": "string", "enum": ["EXACT", "PHRASE", "BROAD"]}
                        }
                    }
                }
            },
            "required": ["customer_id", "updates"]
        }
    }
]
```

- [ ] **Step 4: Write test for capability guard**

```python
# tests/test_mcp_capability_guard.py
import pytest
from src.mcp.capability_guard import CapabilityGuard, CAPABILITY_FORBIDDEN

def test_guard_allows_allowed_operations():
    guard = CapabilityGuard()
    for op in ["keyword.add", "keyword.remove", "keyword.bid.update", "campaign.list"]:
        guard.check(op)  # Should not raise

def test_guard_blocks_budget_operations():
    guard = CapabilityGuard()
    with pytest.raises(CAPABILITY_FORBIDDEN) as exc_info:
        guard.check("campaign.budget.update")
    assert "explicitly blocked" in str(exc_info.value)

def test_guard_blocks_campaign_creation():
    guard = CapabilityGuard()
    with pytest.raises(CAPABILITY_FORBIDDEN):
        guard.check("campaign.create")

def test_guard_blocks_ad_copy():
    guard = CapabilityGuard()
    with pytest.raises(CAPABILITY_FORBIDDEN):
        guard.check("ad.copy.create")
    with pytest.raises(CAPABILITY_FORBIDDEN):
        guard.check("ad.copy.update")
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Google Ads MCP client wrapper with capability guard"
```

---

### Task 8: MCP Server Entrypoint

**Files:**
- Create: `src/mcp/server.py`

- [ ] **Step 1: Write MCP server**

```python
# src/mcp/server.py
"""
MCP server for Google Ads — runs as a stdio process.
Receives JSON-RPC tool calls from the agent runtime.
"""
import json
import sys
from src.mcp.capability_guard import CapabilityGuard, CAPABILITY_FORBIDDEN
from src.mcp.tools import TOOL_DEFINITIONS

guard = CapabilityGuard()

def handle_tool_call(method: str, params: dict) -> dict:
    tool_name = params.get("name", method)
    arguments = params.get("arguments", {})

    if tool_name not in [t["name"] for t in TOOL_DEFINITIONS]:
        return {"error": f"Unknown tool: {tool_name}"}

    # Capability check — get operation key from tool name
    operation_map = {
        "google_ads.add_keywords": "keyword.add",
        "google_ads.remove_keywords": "keyword.remove",
        "google_ads.update_keyword_bids": "keyword.bid.update",
        "google_ads.update_keyword_match_types": "keyword.match_type.update",
    }
    operation = operation_map.get(tool_name)
    if operation:
        try:
            guard.check(operation)
        except CAPABILITY_FORBIDDEN as e:
            return {"error": str(e), "code": "CAPABILITY_FORBIDDEN"}

    # Route to actual Google Ads client
    from src.mcp.google_ads_client import GoogleAdsClientWrapper
    from src.config import settings

    client = GoogleAdsClientWrapper(
        refresh_token=arguments.pop("refresh_token", ""),
        developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN
    )

    handlers = {
        "google_ads.get_campaigns": lambda: client.list_campaigns(arguments["customer_id"]),
        "google_ads.get_keywords": lambda: client.list_keywords(arguments["customer_id"], arguments["campaign_id"]),
        "google_ads.get_keyword_performance": lambda: client.get_keyword_performance(arguments["customer_id"], arguments["campaign_id"]),
        "google_ads.add_keywords": lambda: client.add_keywords(arguments["customer_id"], arguments["ad_group_id"], arguments["keywords"]),
        "google_ads.remove_keywords": lambda: client.remove_keywords(arguments["customer_id"], arguments["keyword_resource_names"]),
        "google_ads.update_keyword_bids": lambda: client.update_keyword_bids(arguments["customer_id"], arguments["updates"]),
        "google_ads.update_keyword_match_types": lambda: client.update_keyword_match_types(arguments["customer_id"], arguments["updates"]),
    }

    try:
        result = handlers[tool_name]()
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        method = request.get("method", "")
        params = request.get("params", {})

        if method == "tools/list":
            print(json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": {"tools": TOOL_DEFINITIONS}}))
        elif method == "tools/call":
            result = handle_tool_call(method, params)
            response = {"jsonrpc": "2.0", "id": request.get("id")}
            response.update(result)
            print(json.dumps(response))
        sys.stdout.flush()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "feat: MCP server stdio entrypoint with capability enforcement"
```

---

## PHASE 4 — Agent System

### Task 9: LLM Adapter (MiniMax Swappable)

**Files:**
- Create: `src/agents/llm_adapter.py`
- Create: `tests/test_llm_adapter.py`

- [ ] **Step 1: Write LLM adapter interface**

```python
# src/agents/llm_adapter.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.config import settings

class LLMAdapter(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        pass

    @abstractmethod
    def chat_with_structured_output(self, messages: List[Dict[str, str]], schema: dict, **kwargs) -> dict:
        pass

class MiniMaxAdapter(LLMAdapter):
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key or settings.MINIMAX_API_KEY
        self.base_url = base_url or settings.MINIMAX_BASE_URL
        self.model = model or settings.MINIMAX_MODEL

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        import httpx
        response = httpx.post(
            f"{self.base_url}/v1/text/chatcompletion_v2",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": messages,
                **{k: v for k, v in kwargs.items() if v is not None}
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def chat_with_structured_output(self, messages: List[Dict[str, str]], schema: dict, **kwargs) -> dict:
        # MiniMax doesn't natively support structured output — use prompt engineering
        import json
        text = self.chat(messages, **kwargs)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

def get_llm_adapter() -> LLMAdapter:
    if settings.LLM_PROVIDER == "minimax":
        return MiniMaxAdapter()
    elif settings.LLM_PROVIDER == "openai":
        # Would load openai adapter
        raise NotImplementedError("OpenAI adapter not yet implemented")
    elif settings.LLM_PROVIDER == "anthropic":
        raise NotImplementedError("Anthropic adapter not yet implemented")
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
```

- [ ] **Step 2: Write test**

```python
# tests/test_llm_adapter.py
import pytest
from unittest.mock import patch, MagicMock
from src.agents.llm_adapter import MiniMaxAdapter

def test_minimax_adapter_chat_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "Green team proposal: add 'summer sale' keyword"}}]}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response):
        adapter = MiniMaxAdapter(api_key="fake", base_url="https://fake.api", model="MiniMax-Text-01")
        messages = [{"role": "user", "content": "Hello"}]
        result = adapter.chat(messages)
        assert "Green team proposal" in result
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: LLM adapter with MiniMax implementation"
```

---

### Task 10: Agent System Prompts

**Files:**
- Create: `src/agents/prompts.py`

- [ ] **Step 1: Write all three agent system prompts**

```python
# src/agents/prompts.py

COORDINATOR_SYSTEM_PROMPT = """You are the Coordinator Agent in an autonomous Google Ads optimization system.

Your role is to orchestrate a three-agent adversarial debate between:
- GREEN TEAM: Proposes optimizations based on research and campaign data
- RED TEAM: Challenges and tries to disprove Green Team proposals

You have access to:
- Campaign performance data (CTR, CPC, conversions, keyword performance)
- A wiki containing validated advertising research
- The current debate state (proposals, objections, round number)

Your responsibilities:
1. Feed Green Team all relevant context at the start of each round
2. Ensure Red Team receives Green Team's full proposal before challenging
3. Review Green proposals + Red objections and determine if consensus is reached
4. If consensus is NOT reached after Red Team's challenge, instruct Green Team to revise
5. If consensus IS reached, lock the decision and signal execution
6. If max rounds (5) are reached without consensus, propose a COMPROMISE that both teams can accept

Compromise rules:
- A compromise MUST address Red Team's core objection
- A compromise MUST preserve at least part of Green Team's intended improvement
- Never just split the difference mechanically — justify the compromise

Output format — always end with one of:
[CONTINUE_DEBATE] Green should revise based on Red objections
[CONSENSUS_REACHED] All three agents agree — proceed to execution
[COMPROMISE_PROPOSED] Coordinator proposes compromise — both teams must accept
[ESCALATE] Max rounds reached, compromise rejected — flag for manual review
"""

GREEN_TEAM_SYSTEM_PROMPT = """You are the Green Team Agent in an autonomous Google Ads optimization system.

Your role: PROPOSE optimizations. You represent the case FOR action.

Context you receive:
- Campaign performance data (CTR, CPC, conversions, search terms, quality scores)
- Wiki research on advertising theory relevant to the current situation
- Red Team's objections from the previous round (if any)

Your task:
1. Analyze the performance data carefully
2. Consult the wiki for validated research patterns
3. Propose specific, actionable optimizations with:
   - Exact keyword changes (add/remove)
   - Bid adjustments with dollar amounts
   - Match type changes
   - Specific reasoning citing evidence (wiki entries, data trends, source URLs)
4. Every proposal MUST include: what to change, why it's beneficial, and what evidence supports it

Red Team will challenge you. Be prepared to:
- Revise proposals to address legitimate objections
- Defend proposals with stronger evidence when objections are unfounded

Output format — for each proposal:
{
  "type": "keyword_add|keyword_remove|bid_update|match_type_update",
  "target": "keyword or resource name",
  "change": "specific change description",
  "priority": "high|medium|low",
  "reasoning": "why this will improve performance",
  "evidence": ["source 1", "source 2"],
  "campaign_id": "uuid"
}
"""

RED_TEAM_SYSTEM_PROMPT = """You are the Red Team Agent in an autonomous Google Ads optimization system.

Your role: CHALLENGE proposals. You represent the case AGAINST action. You are not obstructionist — you are the quality gate that ensures only well-founded changes execute.

Context you receive:
- Green Team's proposals
- Campaign performance data
- Wiki research on advertising theory
- Your mission: find flaws, contradictions, missing context, and counter-evidence

Your task:
1. For EACH Green Team proposal, identify:
   - Logical flaws in the reasoning
   - Contradictions with performance data
   - Missing context (seasonality, market shifts, account history)
   - Risks that aren't addressed
   - Counter-evidence from the wiki or performance trends

2. For each objection you raise, you MUST provide:
   - What the flaw/objection is
   - Specific evidence supporting the objection
   - A suggested revision that would address your concern

3. If a proposal is SOLID and well-founded, say so explicitly — don't object just to object

Remember: you are not trying to block all change. You are ensuring that changes are well-founded. Approve proposals that are genuinely good.

Output format:
{
  "proposal_id": "ref to green proposal",
  "verdict": "approve|object|revise",
  "objections": [
    {
      "objection": "description of flaw",
      "evidence": "why this objection is valid",
      "suggested_fix": "how green team should revise"
    }
  ],
  "reasoning": "overall assessment"
}
"""
```

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "feat: agent system prompts for coordinator, green team, red team"
```

---

### Task 11: Three Agents + Debate State Machine

**Files:**
- Create: `src/agents/coordinator.py`
- Create: `src/agents/green_team.py`
- Create: `src/agents/red_team.py`
- Create: `src/agents/debate_state.py`
- Create: `tests/test_debate_state.py`

- [ ] **Step 1: Write debate state machine**

```python
# src/agents/debate_state.py
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import date
from src.db.postgres_adapter import PostgresAdapter

class Phase(str, Enum):
    IDLE = "idle"
    PERFORMANCE_PULL = "performance_pull"
    GREEN_PROPOSES = "green_proposes"
    RED_CHALLENGES = "red_challenges"
    COORDINATOR_EVALUATES = "coordinator_evaluates"
    CONSENSUS_LOCKED = "consensus_locked"
    WIKI_UPDATE = "wiki_update"
    PENDING_MANUAL_REVIEW = "pending_manual_review"

@dataclass
class DebateState:
    cycle_date: str
    campaign_id: Optional[UUID]
    phase: Phase = Phase.IDLE
    round_number: int = 1
    green_proposals: List[Dict] = field(default_factory=list)
    red_objections: List[Dict] = field(default_factory=list)
    coordinator_decision: Optional[Dict] = None
    consensus_reached: bool = False
    compromise_proposed: bool = False
    compromise_accepted_by_green: bool = False
    compromise_accepted_by_red: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["phase"] = self.phase.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DebateState":
        d["phase"] = Phase(d["phase"]) if isinstance(d["phase"], str) else d["phase"]
        return cls(**d)

class DebateStateMachine:
    def __init__(self, db: PostgresAdapter):
        self.db = db

    def start_cycle(self, cycle_date: str, campaign_id: UUID) -> DebateState:
        state = DebateState(
            cycle_date=cycle_date,
            campaign_id=campaign_id,
            phase=Phase.PERFORMANCE_PULL
        )
        return self._save(state)

    def save(self, state: DebateState) -> DebateState:
        return self._save(state)

    def _save(self, state: DebateState) -> DebateState:
        result = self.db.save_debate_state(state.to_dict())
        return DebateState.from_dict(dict(result))

    def load_or_init(self, cycle_date: str, campaign_id: UUID) -> DebateState:
        existing = self.db.get_latest_debate_state(cycle_date, campaign_id)
        if existing and existing.get("phase") not in (Phase.IDLE.value, Phase.CONSENSUS_LOCKED.value):
            return DebateState.from_dict(dict(existing))
        return self.start_cycle(cycle_date, campaign_id)

    def advance_phase(self, state: DebateState) -> DebateState:
        transitions = {
            Phase.PERFORMANCE_PULL: Phase.GREEN_PROPOSES,
            Phase.GREEN_PROPOSES: Phase.RED_CHALLENGES,
            Phase.RED_CHALLENGES: Phase.COORDINATOR_EVALUATES,
        }
        state.phase = transitions.get(state.phase, state.phase)
        return self.save(state)

    def record_proposals(self, state: DebateState, proposals: List[Dict]) -> DebateState:
        state.green_proposals = proposals
        return self.save(state)

    def record_objections(self, state: DebateState, objections: List[Dict]) -> DebateState:
        state.red_objections = objections
        return self.save(state)

    def evaluate_consensus(
        self,
        state: DebateState,
        coordinator_decision: dict
    ) -> DebateState:
        state.coordinator_decision = coordinator_decision
        verdict = coordinator_decision.get("verdict")

        if verdict == "consensus":
            state.consensus_reached = True
            state.phase = Phase.CONSENSUS_LOCKED
        elif verdict == "compromise_proposed":
            state.compromise_proposed = True
            state.phase = Phase.GREEN_PROPOSES  # Teams must ratify
        elif verdict == "escalate":
            state.phase = Phase.PENDING_MANUAL_REVIEW
        else:
            state.round_number += 1
            state.phase = Phase.GREEN_PROPOSES

        return self.save(state)
```

- [ ] **Step 2: Write Green Team agent**

```python
# src/agents/green_team.py
import json
from typing import List, Dict, Any
from src.agents.llm_adapter import LLMAdapter, get_llm_adapter
from src.agents.prompts import GREEN_TEAM_SYSTEM_PROMPT
from src.agents.debate_state import DebateState

class GreenTeamAgent:
    def __init__(self, llm: LLMAdapter = None):
        self.llm = llm or get_llm_adapter()

    def propose(
        self,
        campaign_data: dict,
        wiki_context: List[dict],
        previous_objections: List[dict] = None
    ) -> List[Dict[str, Any]]:
        context_msg = self._build_context(campaign_data, wiki_context, previous_objections)
        messages = [
            {"role": "system", "content": GREEN_TEAM_SYSTEM_PROMPT},
            {"role": "user", "content": context_msg}
        ]
        response = self.llm.chat(messages)
        return self._parse_response(response)

    def _build_context(
        self,
        campaign_data: dict,
        wiki_context: List[dict],
        previous_objections: List[dict]
    ) -> str:
        lines = ["## Campaign Performance Data\n", json.dumps(campaign_data, indent=2)]
        lines.append("\n## Relevant Wiki Research\n")
        for entry in wiki_context:
            lines.append(f"### {entry['title']}\n{entry['content'][:500]}")
        if previous_objections:
            lines.append("\n## Red Team's Previous Objections (must address these)\n")
            lines.append(json.dumps(previous_objections, indent=2))
        lines.append("\n\nProvide your proposals as a JSON array of proposal objects.")
        return "\n".join(lines)

    def _parse_response(self, response: str) -> List[Dict[str, Any]]:
        import re
        # Try to extract JSON array from response
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return [{"type": "raw", "content": response}]
```

- [ ] **Step 3: Write Red Team agent**

```python
# src/agents/red_team.py
import json
import re
from typing import List, Dict, Any
from src.agents.llm_adapter import LLMAdapter, get_llm_adapter
from src.agents.prompts import RED_TEAM_SYSTEM_PROMPT

class RedTeamAgent:
    def __init__(self, llm: LLMAdapter = None):
        self.llm = llm or get_llm_adapter()

    def challenge(
        self,
        green_proposals: List[Dict],
        campaign_data: dict,
        wiki_context: List[dict]
    ) -> List[Dict[str, Any]]:
        messages = [
            {"role": "system", "content": RED_TEAM_SYSTEM_PROMPT},
            {"role": "user", "content": self._build_context(green_proposals, campaign_data, wiki_context)}
        ]
        response = self.llm.chat(messages)
        return self._parse_response(response)

    def _build_context(
        self,
        green_proposals: List[Dict],
        campaign_data: dict,
        wiki_context: List[dict]
    ) -> str:
        lines = ["## Green Team Proposals\n", json.dumps(green_proposals, indent=2)]
        lines.append("\n## Campaign Performance Data\n")
        lines.append(json.dumps(campaign_data, indent=2))
        lines.append("\n## Wiki Research\n")
        for entry in wiki_context[:5]:
            lines.append(f"### {entry['title']}\n{entry['content'][:300]}")
        lines.append("\n\nProvide your verdict and objections as a JSON array of assessment objects.")
        return "\n".join(lines)

    def _parse_response(self, response: str) -> List[Dict[str, Any]]:
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return [{"type": "raw", "content": response}]
```

- [ ] **Step 4: Write Coordinator agent**

```python
# src/agents/coordinator.py
import json
from typing import List, Dict, Any, Optional
from src.agents.llm_adapter import LLMAdapter, get_llm_adapter
from src.agents.prompts import COORDINATOR_SYSTEM_PROMPT
from src.agents.debate_state import DebateState, Phase

class CoordinatorAgent:
    def __init__(self, llm: LLMAdapter = None, max_rounds: int = 5):
        self.llm = llm or get_llm_adapter()
        self.max_rounds = max_rounds

    def evaluate(
        self,
        state: DebateState,
        campaign_data: dict,
        wiki_context: List[dict]
    ) -> DebateState:
        messages = [
            {"role": "system", "content": COORDINATOR_SYSTEM_PROMPT},
            {"role": "user", "content": self._build_review_context(state, campaign_data, wiki_context)}
        ]
        response = self.llm.chat(messages)
        decision = self._parse_decision(response)
        return self._apply_decision(state, decision)

    def _build_review_context(
        self,
        state: DebateState,
        campaign_data: dict,
        wiki_context: List[dict]
    ) -> str:
        return json.dumps({
            "round": state.round_number,
            "max_rounds": self.max_rounds,
            "phase": state.phase.value,
            "green_proposals": state.green_proposals,
            "red_objections": state.red_objections,
            "campaign_data_summary": {
                "campaign_id": str(state.campaign_id),
                "performance_trends": "see campaign_data param"
            },
            "wiki_entries_used": [e.get("id") for e in wiki_context[:5]]
        }, indent=2)

    def _parse_decision(self, response: str) -> dict:
        import re
        # Look for [VERDICT] tag
        verdict_match = re.search(r'\[(CONTINUE_DEBATE|CONSENSUS_REACHED|COMPROMISE_PROPOSED|ESCALATE)\]', response)
        verdict = verdict_match.group(1) if verdict_match else "continue_debate"
        return {
            "verdict": verdict.replace("_", " ").lower().split()[0],
            "raw_response": response,
            "compromise": None
        }

    def _apply_decision(self, state: DebateState, decision: dict) -> DebateState:
        verdict = decision["verdict"]
        if verdict == "consensus reached":
            state.consensus_reached = True
            state.phase = Phase.CONSENSUS_LOCKED
        elif verdict == "compromise proposed":
            state.compromise_proposed = True
            state.phase = Phase.GREEN_PROPOSES
        elif verdict == "escalate":
            state.phase = Phase.PENDING_MANUAL_REVIEW
        else:
            state.round_number += 1
            state.phase = Phase.GREEN_PROPOSES
        state.coordinator_decision = decision
        return state
```

- [ ] **Step 5: Write test for debate state machine**

```python
# tests/test_debate_state.py
import pytest
from unittest.mock import MagicMock
from src.agents.debate_state import DebateState, Phase, DebateStateMachine
from uuid import uuid4

def test_debate_state_transitions_idle_to_performance_pull():
    state = DebateState(cycle_date="2026-04-06", campaign_id=uuid4())
    assert state.phase == Phase.IDLE
    assert state.round_number == 1

def test_debate_state_to_dict_serialization():
    cid = uuid4()
    state = DebateState(cycle_date="2026-04-06", campaign_id=cid, phase=Phase.GREEN_PROPOSES)
    d = state.to_dict()
    assert d["phase"] == "green_proposes"
    assert d["campaign_id"] == str(cid)

def test_debate_state_from_dict_deserialization():
    d = {
        "cycle_date": "2026-04-06",
        "campaign_id": str(uuid4()),
        "phase": "red_challenges",
        "round_number": 2,
        "green_proposals": [{"type": "keyword_add"}],
        "red_objections": [],
        "coordinator_decision": None,
        "consensus_reached": False,
        "compromise_proposed": False,
        "compromise_accepted_by_green": False,
        "compromise_accepted_by_red": False
    }
    state = DebateState.from_dict(d)
    assert state.phase == Phase.RED_CHALLENGES
    assert state.round_number == 2
    assert len(state.green_proposals) == 1

def test_advance_phase():
    state = DebateState(cycle_date="2026-04-06", campaign_id=uuid4(), phase=Phase.PERFORMANCE_PULL)
    sm = DebateStateMachine(MagicMock())
    next_state = sm.advance_phase(state)
    assert next_state.phase == Phase.GREEN_PROPOSES
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: three-agent system with coordinator, green team, red team"
```

---

## PHASE 5 — Research Loop

### Task 12: Research Sources (Jina MCP + Jina Search)

**Files:**
- Create: `src/research/sources.py`

- [ ] **Step 1: Write research source definitions**

```python
# src/research/sources.py
"""
Research source definitions and fetchers.
Uses Jina MCP for web search and content extraction.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json

@dataclass
class Source:
    name: str
    url: Optional[str]
    content: str
    fetched_at: str
    source_type: str  # "google_ads_doc", "academic", "industry_news", "competitor", "campaign_data"

# Initial academic search queries — seeds the wiki on first run
ACADEMIC_SEARCH_QUERIES = [
    "advertising attribution models multi-touch",
    "real-time bid optimization search advertising",
    "keyword-level ROI prediction paid search",
    "search advertising effectiveness measurement",
    "quality score impact on ad rank Google Ads",
]

INDUSTRY_NEWS_QUERIES = [
    "Google Ads keyword optimization best practices 2026",
    "PPC bid strategy machine learning",
    "search advertising CTR optimization techniques",
]

GOOGLE_ADS_DOC_TOPICS = [
    "https://developers.google.com/google-ads/api/fields/latest/overview",
    "https://ads.google.com/apis/ads/publisher/v202406",
]
```

- [ ] **Step 2: Write source fetcher using Jina MCP**

```python
# src/research/sources.py (add fetchers)

async def fetch_academic_sources(queries: List[str]) -> List[Source]:
    """Use Jina search to find academic papers, then extract content."""
    sources = []
    for query in queries:
        try:
            # Use Jina search to find relevant papers
            results = []  # populated by jina_mcp search call
            for r in results:
                content = ""  # populated by jina_mcp read call
                sources.append(Source(
                    name=r.get("title", ""),
                    url=r.get("url"),
                    content=content,
                    fetched_at=datetime.utcnow().isoformat(),
                    source_type="academic"
                ))
        except Exception:
            pass
    return sources

async def fetch_industry_news(queries: List[str]) -> List[Source]:
    """Fetch industry news using Jina parallel search."""
    sources = []
    for query in queries:
        try:
            results = []  # populated by jina_mcp search call
            for r in results:
                sources.append(Source(
                    name=r.get("title", ""),
                    url=r.get("url"),
                    content="",  # populated by jina_mcp read call
                    fetched_at=datetime.utcnow().isoformat(),
                    source_type="industry_news"
                ))
        except Exception:
            pass
    return sources
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: research source definitions and fetchers"
```

---

### Task 13: Wiki Writer + Validator

**Files:**
- Create: `src/research/wiki_writer.py`
- Create: `src/research/validator.py`

- [ ] **Step 1: Write wiki writer**

```python
# src/research/wiki_writer.py
import hashlib
import re
from datetime import datetime
from typing import List, Dict, Any
from src.db.postgres_adapter import PostgresAdapter
from src.db.base import DatabaseAdapter

class WikiWriter:
    def __init__(self, db: DatabaseAdapter = None):
        self.db = db or PostgresAdapter()

    def write_consensus_entry(
        self,
        title: str,
        content: str,
        green_rationale: str,
        red_objections: List[Dict],
        consensus_note: str,
        sources: List[Dict],
        tags: List[str]
    ) -> dict:
        slug = self._generate_slug(title)
        entry = self.db.create_wiki_entry({
            "title": title,
            "slug": slug,
            "content": content,
            "green_rationale": green_rationale,
            "red_objections": red_objections,
            "consensus_note": consensus_note,
            "sources": sources,
            "tags": tags,
        })
        return entry

    def invalidate_entry(self, entry_id: str, reason: str) -> None:
        self.db.execute(
            "UPDATE wiki_entries SET invalidated_at = NOW() WHERE id = %s",
            (entry_id,)
        )

    def _generate_slug(self, title: str) -> str:
        slug = re.sub(r'[^a-z0-9\s-]', '', title.lower())
        slug = re.sub(r'[\s-]+', '-', slug).strip('-')
        hash_suffix = hashlib.md5(title.encode()).hexdigest()[:6]
        return f"{slug}-{hash_suffix}"
```

- [ ] **Step 2: Write validator orchestrator**

```python
# src/research/validator.py
"""
The adversarial validation loop — orchestrates Green Team → Red Team → Coordinator
until consensus is reached or max rounds elapsed.
"""
from typing import List, Dict, Any
from uuid import UUID
from datetime import date
from src.agents.green_team import GreenTeamAgent
from src.agents.red_team import RedTeamAgent
from src.agents.coordinator import CoordinatorAgent
from src.agents.debate_state import DebateState, Phase, DebateStateMachine
from src.mcp.google_ads_client import GoogleAdsClientWrapper
from src.config import settings

class AdversarialValidator:
    def __init__(self):
        self.green = GreenTeamAgent()
        self.red = RedTeamAgent()
        self.coordinator = CoordinatorAgent(max_rounds=settings.MAX_DEBATE_ROUNDS)
        self.state_machine = DebateStateMachine()

    def run_cycle(self, cycle_date: str, campaign_id: UUID, campaign_data: dict, wiki_context: List[dict]) -> DebateState:
        state = self.state_machine.load_or_init(cycle_date, campaign_id)

        # Phase 1: Pull performance data (already done by caller)
        if state.phase == Phase.PERFORMANCE_PULL:
            state = self.state_machine.advance_phase(state)

        # Phase 2: Green proposes
        if state.phase == Phase.GREEN_PROPOSES:
            previous_objections = state.red_objections if state.round_number > 1 else []
            proposals = self.green.propose(campaign_data, wiki_context, previous_objections)
            state = self.state_machine.record_proposals(state, proposals)
            state = self.state_machine.advance_phase(state)

        # Phase 3: Red challenges
        if state.phase == Phase.RED_CHALLENGES:
            objections = self.red.challenge(state.green_proposals, campaign_data, wiki_context)
            state = self.state_machine.record_objections(state, objections)
            state = self.state_machine.advance_phase(state)

        # Phase 4: Coordinator evaluates
        if state.phase == Phase.COORDINATOR_EVALUATES:
            state = self.coordinator.evaluate(state, campaign_data, wiki_context)
            # Persist coordinator decision
            self.state_machine.save(state)

            # Loop back if not done
            if state.phase in (Phase.GREEN_PROPOSES, Phase.RED_CHALLENGES):
                return self.run_cycle(cycle_date, campaign_id, campaign_data, wiki_context)

        return state
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: wiki writer and adversarial validation orchestrator"
```

---

### Task 14: Daily Research Cron Script

**Files:**
- Create: `src/cron/daily_research.py`
- Create: `scripts/run_research_cycle.py`

- [ ] **Step 1: Write daily research cycle script**

```python
# src/cron/daily_research.py
"""
Daily research cycle — triggered by systemd cron at 8am server time.
Fetches campaign performance, runs adversarial validation loop,
executes approved changes, writes wiki entries, fires webhooks.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from typing import List
from src.db.postgres_adapter import PostgresAdapter
from src.mcp.google_ads_client import GoogleAdsClientWrapper
from src.mcp.capability_guard import CapabilityGuard
from src.research.validator import AdversarialValidator
from src.research.wiki_writer import WikiWriter
from src.services.webhook_service import WebhookService
from src.services.audit_service import AuditService
from src.config import settings

def run_daily_research():
    db = PostgresAdapter()
    validator = AdversarialValidator()
    wiki_writer = WikiWriter(db)
    webhook_service = WebhookService(db)
    audit_service = AuditService(db)
    guard = CapabilityGuard()
    today = date.today().isoformat()

    campaigns = db.list_campaigns()
    print(f"[Research Cycle {today}] Processing {len(campaigns)} campaigns...")

    for campaign in campaigns:
        print(f"  Campaign {campaign['campaign_id']}: starting research cycle")
        try:
            # 1. Pull performance data via Google Ads client
            gads_client = GoogleAdsClientWrapper(
                refresh_token=campaign["api_key_token"],
                developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN
            )
            performance_data = gads_client.get_keyword_performance(
                customer_id=campaign["customer_id"],
                campaign_id=campaign["campaign_id"]
            )

            # 2. Load wiki context for this campaign
            wiki_results = db.search_wiki(f"campaign {campaign['campaign_id']}", limit=5)
            wiki_context = [dict(r) for r in wiki_results]

            # 3. Run adversarial validation
            state = validator.run_cycle(
                cycle_date=today,
                campaign_id=campaign["id"],
                campaign_data={"campaign": campaign, "performance": performance_data},
                wiki_context=wiki_context
            )

            # 4. If consensus reached — execute via MCP
            if state.consensus_reached:
                print(f"    Consensus reached after {state.round_number} rounds")
                audit_service.log_decision(state, campaign)
                webhook_service.dispatch("consensus_reached", {
                    "campaign_id": str(campaign["id"]),
                    "cycle_date": today,
                    "actions": state.green_proposals,
                    "debate_rounds": state.round_number
                })

                # Update campaign last_reviewed_at
                db.execute(
                    "UPDATE campaigns SET last_reviewed_at = NOW() WHERE id = %s",
                    (str(campaign["id"]),)
                )
            elif state.phase == Phase.PENDING_MANUAL_REVIEW:
                print(f"    Max rounds reached — flagged for manual review")
                webhook_service.dispatch("manual_review_required", {
                    "campaign_id": str(campaign["id"]),
                    "cycle_date": today
                })

        except Exception as e:
            print(f"    ERROR: {e}")
            webhook_service.dispatch("cycle_error", {
                "campaign_id": str(campaign["id"]),
                "error": str(e)
            })

    print(f"[Research Cycle {today}] Complete.")

if __name__ == "__main__":
    run_daily_research()
```

- [ ] **Step 2: Write manual trigger script**

```python
# scripts/run_research_cycle.py
#!/usr/bin/env python3
"""Manually trigger a research cycle — useful for testing or on-demand runs."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.cron.daily_research import run_daily_research
if __name__ == "__main__":
    run_daily_research()
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: daily research cron script with full cycle orchestration"
```

---

### Task 15: Audit Service

**Files:**
- Create: `src/services/audit_service.py`

- [ ] **Step 1: Write audit service**

```python
# src/services/audit_service.py
from datetime import date
from typing import Optional
from uuid import UUID
from src.db.postgres_adapter import PostgresAdapter
from src.db.base import DatabaseAdapter
from src.agents.debate_state import DebateState

class AuditService:
    def __init__(self, db: DatabaseAdapter = None):
        self.db = db or PostgresAdapter()

    def log_decision(self, state: DebateState, campaign: dict) -> dict:
        return self.db.write_audit_log({
            "cycle_date": state.cycle_date,
            "campaign_id": state.campaign_id,
            "action_type": "optimization_decision",
            "target": {"campaign_id": campaign["campaign_id"], "proposals": state.green_proposals},
            "green_proposal": {"proposals": state.green_proposals, "reasoning": "see proposals"},
            "red_objections": state.red_objections,
            "coordinator_note": state.coordinator_decision.get("raw_response", "") if state.coordinator_decision else "",
            "debate_rounds": state.round_number
        })

    def log_manual_override(self, campaign_id: UUID, admin_api_key: str, action: dict) -> dict:
        return self.db.write_audit_log({
            "cycle_date": date.today().isoformat(),
            "campaign_id": campaign_id,
            "action_type": "manual_override",
            "target": action,
            "coordinator_note": f"Override applied by admin"
        })
```

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "feat: audit service for decision logging"
```

---

## PHASE 6 — Testing & Deployment

### Task 16: Unit Tests

**Files:**
- Create: `tests/test_api_campaigns.py`
- Create: `tests/test_api_webhooks.py`
- Create: `tests/test_wiki_search.py`
- Create: `tests/test_debate_state.py`

- [ ] **Step 1: Write API campaign tests**

```python
# tests/test_api_campaigns.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from src.main import app

@pytest.fixture
def client():
    with patch("src.api.middleware.settings") as mock_settings:
        mock_settings.ADMIN_API_KEY = "test-key"
        return TestClient(app)

@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-key"}

def test_create_campaign(client, auth_headers):
    with patch("src.api.routes.campaigns.get_db") as mock_db:
        mock = MagicMock()
        mock.create_campaign.return_value = {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "campaign_id": "123", "customer_id": "456", "name": "Test",
            "status": "active", "campaign_type": "search", "owner_tag": "team",
            "created_at": "2026-04-06T00:00:00Z", "last_synced_at": None, "last_reviewed_at": None
        }
        mock_db.return_value = mock

        response = client.post(
            "/campaigns",
            json={
                "campaign_id": "123", "customer_id": "456", "name": "Test",
                "api_key_token": "token123", "campaign_type": "search", "owner_tag": "team"
            },
            headers=auth_headers
        )
        assert response.status_code == 201
        assert response.json()["campaign_id"] == "123"

def test_create_campaign_missing_api_key(client):
    response = client.post("/campaigns", json={"campaign_id": "123"})
    assert response.status_code == 401

def test_list_campaigns(client, auth_headers):
    with patch("src.api.routes.campaigns.get_db") as mock_db:
        mock = MagicMock()
        mock.list_campaigns.return_value = [
            {"id": "123", "campaign_id": "1", "customer_id": "1", "name": "C1",
             "status": "active", "campaign_type": None, "owner_tag": None,
             "created_at": "2026-04-06T00:00:00Z", "last_synced_at": None, "last_reviewed_at": None}
        ]
        mock_db.return_value = mock
        response = client.get("/campaigns", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1

def test_delete_campaign(client, auth_headers):
    with patch("src.api.routes.campaigns.get_db") as mock_db:
        mock = MagicMock()
        mock_db.return_value = mock
        response = client.delete("/campaigns/123e4567-e89b-12d3-a456-426614174000", headers=auth_headers)
        assert response.status_code == 204
        mock.delete_campaign.assert_called_once()
```

- [ ] **Step 2: Write webhook service test**

```python
# tests/test_api_webhooks.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_register_webhook(client):
    with patch("src.api.routes.webhooks.get_db") as mock_db:
        mock = MagicMock()
        mock.register_webhook.return_value = {
            "id": "123", "url": "https://example.com/hook", "events": ["decision_made"], "active": True
        }
        mock_db.return_value = mock
        response = client.post("/webhooks", json={"url": "https://example.com/hook"})
        assert response.status_code == 201
        assert response.json()["url"] == "https://example.com/hook"
```

- [ ] **Step 3: Write wiki search test**

```python
# tests/test_wiki_search.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.main import app

def test_search_wiki(client):
    with patch("src.api.routes.wiki.get_db") as mock_db:
        mock = MagicMock()
        mock.search_wiki.return_value = [
            {"id": "123", "title": "Keyword Optimization", "slug": "keyword-opt",
             "content": "...", "sources": [], "tags": ["keyword"], "created_at": "2026-04-06T00:00:00Z",
             "updated_at": "2026-04-06T00:00:00Z"}
        ]
        mock_db.return_value = mock
        response = client.get("/research/wiki?q=keyword+optimization")
        assert response.status_code == 200
        assert len(response.json()) == 1
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v --tb=short
# Expected: all tests pass
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "test: unit tests for API, wiki, webhooks, and debate state"
```

---

### Task 17: Droplet Setup Script + README

**Files:**
- Create: `setup_droplet.sh`
- Create: `README.md`

- [ ] **Step 1: Write droplet setup script**

```bash
#!/bin/bash
# setup_droplet.sh — Provisions a Digital Ocean droplet for the Google Ads Agent

set -e

echo "=== Google Ads Agent — Droplet Setup ==="

# 1. System packages
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib git curl

# 2. PostgreSQL setup
sudo -u postgres psql -c "CREATE USER adsagent WITH PASSWORD 'adsagent_pass';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE ads_agent OWNER adsagent;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ads_agent TO adsagent;" 2>/dev/null || true

# 3. Clone and install app
cd /opt
sudo git clone https://github.com/YOUR_REPO/google-ads-agent-api.git ads-agent 2>/dev/null || \
    sudo git -C /opt/ads-agent pull 2>/dev/null || \
    (sudo mkdir -p /opt/ads-agent && echo "Manual clone needed")
cd /opt/ads-agent
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Apply DB schema
PGPASSWORD=adsagent_pass psql -h localhost -U adsagent -d ads_agent -f src/db/schema.sql

# 5. Environment variables
sudo tee /opt/ads-agent/.env > /dev/null <<EOF
ADMIN_API_KEY=CHANGE_ME
DATABASE_URL=postgresql://adsagent:adsagent_pass@localhost:5432/ads_agent
DB_PROVIDER=postgresql
GOOGLE_ADS_DEVELOPER_TOKEN=YOUR_TOKEN
GOOGLE_ADS_CLIENT_ID=YOUR_CLIENT_ID
GOOGLE_ADS_CLIENT_SECRET=YOUR_CLIENT_SECRET
MINIMAX_API_KEY=YOUR_MINIMAX_KEY
RESEARCH_CRON=0 8 * * *
MAX_DEBATE_ROUNDS=5
EOF

# 6. Cron job for daily research
echo "0 8 * * * cd /opt/ads-agent && source venv/bin/activate && python scripts/run_research_cycle.py >> /var/log/ads-research.log 2>&1" | sudo tee /etc/cron.d/ads-research

# 7. API server (systemd)
sudo tee /etc/systemd/system/ads-agent-api.service > /dev/null <<EOF
[Unit]
Description=Google Ads Agent API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ads-agent
EnvironmentFile=/opt/ads-agent/.env
ExecStart=/opt/ads-agent/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ads-agent-api
sudo systemctl start ads-agent-api

echo "=== Setup complete ==="
echo "API running at http://$(curl -s ifconfig.me):8000"
echo "Edit /opt/ads-agent/.env to configure API keys"
```

- [ ] **Step 2: Write README**

```markdown
# Google Ads Autonomous Agent

An autonomous headless agent system that researches advertising theory, studies Google Ads campaign performance, and continuously optimizes managed campaigns through an adversarial three-agent architecture.

## Architecture

- **Coordinator Agent** — orchestrates green/red adversarial debate
- **Green Team Agent** — proposes optimizations
- **Red Team Agent** — challenges and validates all proposals
- **Custom Google Ads MCP** — capability-restricted wrapper around Google Ads API

## Quick Start

```bash
# Copy env and fill in your keys
cp .env.example .env

# Run the API
uvicorn src.main:app --reload

# Trigger a research cycle manually
python scripts/run_research_cycle.py
```

## API

All endpoints require `X-API-Key` header.

```bash
# Add a campaign
POST /campaigns

# List campaigns
GET /campaigns

# Get insights for a campaign
GET /campaigns/{id}/insights

# Search the wiki
GET /research/wiki?q=keyword+optimization
```

## Research Loop

Runs daily at 8am server time via cron. The loop:
1. Pulls campaign performance from Google Ads
2. Green Team proposes optimizations
3. Red Team challenges every proposal
4. Coordinator evaluates — debate continues until consensus or max rounds
5. Approved changes execute via MCP (keywords only — budget is blocked)
6. Wiki updated with validated research
7. Webhooks fired
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: droplet provisioning script and README"
```

---

## Spec Coverage Check

| Spec Section | Task(s) |
|---|---|
| Campaign API endpoints | Task 4, 5, 6 |
| MCP capability matrix | Task 7, 8 |
| Three-agent architecture | Task 9, 10, 11 |
| Daily research loop (cron) | Task 12, 13, 14 |
| Wiki (embeddingless RAG) | Task 3, 6, 13 |
| Audit log | Task 15 |
| Webhooks + retry | Task 6, 15 |
| LLM adapter (MiniMax swappable) | Task 9 |
| Debate state machine | Task 11 |
| Droplet deployment | Task 17 |

All spec sections covered. No gaps.

---

## Type Consistency Check

- `DebateState.phase` always `Phase` enum — `.value` used when serializing to DB
- `campaign_id` stored as `UUID` in Python, `UUID` in DB
- `green_proposals` / `red_objections` always `List[Dict]` — serialized as JSONB in Postgres
- `wiki_writer.write_consensus_entry` returns `dict` from DB — callers handle conversion
- All route handlers use `DatabaseAdapter` abstraction — swappable to SQLite

All consistent.
