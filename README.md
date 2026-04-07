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
              │ ALLOWED:                          │
              │   - list_*, get_* (read ops)     │
              │   - add_keywords                  │
              │   - remove_keywords               │
              │   - update_keyword_*              │
              │ DENIED (always):                  │
              │   - delete_*                      │
              │   - transfer_*                    │
              │   - update_payment_*               │
              │   - change_daily_budget_*         │
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

All endpoints (except `/health` and `/webhooks/inbound-email`) require `X-API-Key` header.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth) |
| GET | `/campaigns` | List all campaigns |
| POST | `/campaigns` | Create a campaign |
| GET | `/campaigns/{campaign_id}` | Get a campaign |
| PATCH | `/campaigns/{campaign_id}` | Update HITL settings |
| DELETE | `/campaigns/{campaign_id}` | Delete a campaign |
| GET | `/campaigns/{campaign_id}/insights` | Get campaign with latest debate state |
| POST | `/campaigns/{campaign_id}/approve` | Approve pending proposals (HITL) |
| POST | `/campaigns/{campaign_id}/override` | Force action bypassing debate |
| GET | `/campaigns/{campaign_id}/hitl/proposals` | List HITL proposals |
| GET | `/campaigns/{campaign_id}/hitl/proposals/{proposal_id}` | Get single HITL proposal |
| POST | `/campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide` | Approve/reject HITL proposal |
| GET | `/wiki` | List all wiki entries |
| GET | `/wiki/search` | Search wiki entries by query |
| POST | `/wiki` | Create wiki entry |
| DELETE | `/wiki/{entry_id}` | Delete wiki entry |
| GET | `/audit` | Query audit logs |
| POST | `/webhooks` | Register webhook |
| GET | `/webhooks` | List webhooks |
| DELETE | `/webhooks/{webhook_id}` | Delete webhook |
| POST | `/webhooks/inbound-email` | Resend inbound email webhook (no auth) |
| POST | `/email-replies` | Process email reply to HITL proposal |
| POST | `/research/trigger` | Manually trigger research cycle |

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

- All Google Ads operations are **denied by default** via `CapabilityGuard`
- Allowed by default: read operations (`list_*`, `get_*`) and safe keyword writes (`add_*`, `remove_*`, `update_keyword_*`)
- Explicitly denied: `delete_*`, `transfer_*`, `update_payment_*`, `change_daily_budget_*`, and campaign mutations (`update_campaign_budget`, `update_campaign_status`) — blocked by guard even if capability guard rules are relaxed
- Campaign `api_key_token` is stripped before passing to agents
- Webhook payloads are HMAC-SHA256 signed

## Human-in-the-Loop (HITL) Email Approval

For high-impact proposals (budget changes >20%, keyword adds >5, keyword removals, match type changes), the agent routes proposals to email approval instead of auto-executing.

### How it works

1. Green Team proposes changes via the research cycle
2. Proposals above threshold are held for human approval
3. Email is sent to the campaign's `owner_email` with proposal details
4. Coordinator approves or rejects via the REST API
5. Approved proposals execute; rejected ones are logged and skipped

### HITL settings (per campaign)

| Field | Description |
|-------|-------------|
| `hitl_enabled` | Enable email approval for above-threshold proposals |
| `owner_email` | Email address to send approval requests |
| `hitl_threshold` | Threshold rules string (default: `budget>20pct,keyword_add>5`) |

Update via `PATCH /campaigns/{campaign_id}`:
```json
{
  "hitl_enabled": true,
  "owner_email": "ads-team@example.com"
}
```

### HITL REST API

```bash
# List pending proposals
GET /campaigns/{campaign_id}/hitl/proposals

# Approve a proposal
POST /campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide
{"decision": "approved", "notes": "LGTM"}

# Reject a proposal
POST /campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide
{"decision": "rejected", "notes": "Too aggressive"}
```

### Weekly Digest

Every Monday at 9am UTC, a digest email is sent to owners of HITL-enabled campaigns with:
- Week's impressions, clicks, spend, and CTR
- Count of pending/approved/rejected proposals

Set `HITL_WEEKLY_CRON=*/5 * * * *` (default: every 5 minutes) to configure the schedule.

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
  agents/           # Green Team, Red Team, Coordinator, debate state
  api/routes/       # FastAPI route handlers (campaigns, wiki, webhooks, hitl, etc.)
  api/schemas.py    # Pydantic request/response models
  api/middleware.py # X-API-Key authentication
  cron/             # Daily research cycle + weekly digest cron
  db/               # Database adapter and schema
  llm/              # LLM adapter (MiniMax, swappable)
  mcp/              # Google Ads MCP server and capability guard
  research/         # Validator, wiki writer, research sources
  services/         # Audit, webhook, email, and impact assessor services
  config.py         # Environment configuration
  main.py           # FastAPI app entrypoint
```

## License

Proprietary — All rights reserved.