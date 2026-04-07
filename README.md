# Google Ads Autonomous Agent API

Autonomous headless Google Ads optimization agent with a three-agent adversarial architecture (Coordinator + Green Team + Red Team). Runs on a Digital Ocean droplet.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Daily Research Cycle (cron / systemd timer)                        │
│                                                                     │
│  ┌──────────────┐    ┌────────────┐    ┌──────────────────────┐   │
│  │ Green Team   │───▶│ Red Team   │───▶│ Coordinator Agent    │   │
│  │ (proposer)   │    │(challenger)│    │ (arbitrator)         │   │
│  └──────────────┘    └────────────┘    └──────────────────────┘   │
│         │                   │                     │               │
│         └───────────────────┴─────────────────────┘               │
│                         │                                         │
│                   consensus?                                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────┐
              │ Google Ads MCP Client            │
              │ (capability-gated)                │
              │ - add_keywords (allowed)          │
              │ - update_campaign_budget (denied) │
              └───────────────────────────────────┘
```

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/SeanConway102/google-ads-agent-api.git /opt/ads-agent
cd /opt/ads-agent
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env  # create from example or manually
nano .env  # fill in your API keys
```

Required environment variables:

| Variable | Description |
|----------|-------------|
| `ADMIN_API_KEY` | API key for the FastAPI admin endpoints |
| `DATABASE_URL` | PostgreSQL connection string |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Google Ads developer token |
| `GOOGLE_ADS_CLIENT_ID` | OAuth client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_ADS_REFRESH_TOKEN` | OAuth refresh token |
| `MINIMAX_API_KEY` | MiniMax API key for LLM calls |
| `MAX_DEBATE_ROUNDS` | Max debate rounds before manual review (default: 5) |

### 3. Apply database schema

```bash
psql "$DATABASE_URL" -f src/db/schema.sql
```

### 4. Run the API server

```bash
source venv/bin/activate
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

All endpoints (except `/health`) require `X-API-Key` header.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth) |
| GET | `/api/campaigns` | List all campaigns |
| POST | `/api/campaigns` | Create a campaign |
| GET | `/api/campaigns/{id}` | Get a campaign |
| DELETE | `/api/campaigns/{id}` | Delete a campaign |
| GET | `/api/wiki/search?q=` | Search wiki entries |
| POST | `/api/wiki` | Create wiki entry |
| GET | `/api/audit` | Query audit logs |
| POST | `/api/webhooks` | Register webhook |
| GET | `/api/webhooks` | List webhooks |
| DELETE | `/api/webhooks/{id}` | Delete webhook |
| GET | `/api/mcp/tools` | List MCP tools |

## Daily Research Cycle

The research cycle runs automatically at 8am server time via cron. It:

1. Fetches keyword performance data for all active campaigns
2. Loads relevant wiki context for each campaign
3. Runs the adversarial validation loop:
   - **Green Team** proposes optimization changes
   - **Red Team** challenges the proposals
   - **Coordinator** evaluates and decides
4. On consensus: executes allowed changes, logs audit, fires webhooks
5. On max rounds without consensus: fires `manual_review_required` webhook

### Manual trigger

```bash
python scripts/run_research_cycle.py
```

## Webhook Events

The agent fires webhook events to registered endpoints:

| Event | Trigger |
|-------|---------|
| `consensus_reached` | Debate reached agreement |
| `manual_review_required` | Max rounds exceeded |
| `cycle_error` | Exception during processing |
| `campaign_created` | New campaign registered |
| `campaign_deleted` | Campaign deleted |

## Security

- All Google Ads write operations are **denied by default** via `CapabilityGuard`
- Only `google_ads.add_keywords` is explicitly allowed
- Campaign `api_key_token` is stripped before passing to agents
- Webhook payloads are HMAC-SHA256 signed

## Testing

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## Project Structure

```
src/
  agents/           # Green Team, Red Team, Coordinator agents
  api/              # FastAPI routes and schemas
  cron/             # Daily research cycle script
  db/               # Database adapter and schema
  llm/              # LLM adapter (MiniMax)
  mcp/              # Google Ads MCP server and capability guard
  research/         # Validator, wiki writer, research sources
  services/         # Audit and webhook services
  config.py         # Environment configuration
  main.py           # FastAPI app entrypoint
```

## License

Proprietary — All rights reserved.