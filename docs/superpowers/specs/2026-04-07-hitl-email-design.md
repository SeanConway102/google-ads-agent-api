# HITL Email Approval — Design Spec

**Date:** 2026-04-07
**Feature:** Human-in-the-loop email approval via Resend
**Status:** Draft — pending approval

---

## Overview

Add an optional human-in-the-loop layer to the autonomous agent. When `hitl_enabled=true` on a campaign, high-impact Green Team proposals are held for email approval instead of auto-executing. The system sends a proposal email via Resend, the user replies with their decision, and the agent interprets the reply to approve or reject.

**Default behavior:** Weekly digest email summarizing all campaign performance and pending/approved proposals. User can reply to any email to intervene or ask questions.

---

## Decisions

| Decision | Choice |
|---|---|
| HITL trigger | Above threshold — only high-impact changes (budget >20%, large keyword additions) require approval |
| Subscription default | Weekly digest |
| Email backend | Resend (via `resend` Python SDK) |
| User identity | Per-campaign `owner_email` field, optional (falls back to `HITL_DEFAULT_EMAIL` env var) |
| Email threading | One-off per proposal — each approval is independent |

---

## Architecture

```
Green Team Proposal
        │
        ▼
┌───────────────────┐
│  Impact Assessor  │  ← new: src/services/impact_assessor.py
│  (small/threshold)│
└────────┬──────────┘
         │ low impact
         ▼
   Auto-Execute

         │ high impact + hitl_enabled=true
         ▼
┌───────────────────┐
│  Email Service    │  ← src/services/email_service.py
│  (Resend)         │
└────────┬──────────┘
         │
         ▼
   Proposal Email
   to owner_email
         │
         ▼
  Await Reply (up to 7 days)
         │
         ▼
  Reply Handler (IMAP/POP3 or Resend inbound webhook)
         │
         ├── "approve" / "yes" → execute proposal
         ├── "reject" / "no"  → discard, log
         └── question          → follow-up email response
```

---

## Database Changes

### `campaigns` table — add columns

```sql
ALTER TABLE campaigns ADD COLUMN hitl_enabled   BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE campaigns ADD COLUMN owner_email    TEXT;
ALTER TABLE campaigns ADD COLUMN hitl_threshold  TEXT DEFAULT 'budget>20pct,keyword_add>5';
```

### New table `hitl_proposals`

```sql
CREATE TABLE IF NOT EXISTS hitl_proposals (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id       UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    proposal_id       TEXT NOT NULL,          -- green_team_proposals.id
    proposal_type     TEXT NOT NULL,          -- 'budget_update', 'keyword_add', etc.
    impact_summary    TEXT NOT NULL,          -- human-readable description
    reasoning         TEXT NOT NULL,          -- Green Team rationale
    status            TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/rejected/expired
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at        TIMESTAMPTZ,
    replier_response  TEXT                     -- raw or parsed reply text
);

CREATE INDEX idx_hitl_proposals_campaign ON hitl_proposals(campaign_id);
CREATE INDEX idx_hitl_proposals_status   ON hitl_proposals(status) WHERE status = 'pending';
```

---

## New Files

| File | Responsibility |
|---|---|
| `src/services/email_service.py` | Resend SDK wrapper — send proposal emails, weekly digests |
| `src/services/impact_assessor.py` | Determine if a proposal is above threshold |
| `src/services/reply_handler.py` | Parse inbound email replies, update proposal status |
| `src/db/hitl_adapter.py` | CRUD for `hitl_proposals` table |
| `src/api/routes/hitl.py` | REST endpoints: list pending proposals, manually approve/reject |
| `src/agents/green_team.py` (modify) | After creating a proposal, check impact and route to email or auto-execute |
| `src/cron/weekly_digest.py` | New cron script — send weekly summary emails |

---

## Email Templates

### Proposal Approval Email
```
Subject: [AdsAgent] Action required: {proposal_type} on campaign "{campaign_name}"

Hi,

The Green Team has proposed a {proposal_type} for campaign "{campaign_name}":

  What:  {impact_summary}
  Why:   {reasoning}

To approve: reply with "approve", "yes", or "sounds good"
To reject:  reply with "reject", "no", or "not this time"
To ask:     reply with your question and I'll respond

This proposal will auto-expire in 7 days if no response.

— AdsAgent (autonomous Google Ads optimizer)
```

### Weekly Digest Email
```
Subject: [AdsAgent] Weekly update for {campaign_name}

Hi,

Here's your weekly summary for "{campaign_name}":

  📊 Performance (last 7 days)
  ─────────────────────────
  Impressions: {impressions}
  Clicks:     {clicks}
  Spend:      ${spend}
  CTR:        {ctr}%

  ✅ Proposals decided: {n_approved} approved, {n_rejected} rejected
  ⏳ Pending: {n_pending} proposal(s) awaiting your review

  [Reply "proposals" to see pending items]

— AdsAgent (autonomous Google Ads optimizer)
```

---

## API Changes

### `PATCH /campaigns/{uuid}` — update HITL settings

```json
{
  "hitl_enabled": true,
  "owner_email": "manager@company.com",
  "hitl_threshold": "budget>20pct,keyword_add>5"
}
```

### `GET /campaigns/{uuid}/hitl/proposals` — list proposals for a campaign

```json
[
  {
    "id": "uuid",
    "proposal_type": "budget_update",
    "impact_summary": "Increase daily budget from $50 to $75",
    "reasoning": "CTR has been 4.2% over past 30 days...",
    "status": "pending",
    "created_at": "2026-04-07T10:00:00Z"
  }
]
```

### `POST /campaigns/{uuid}/hitl/proposals/{proposal_id}/decide` — manual decision

```json
{ "decision": "approved" }   // or "rejected"
```

---

## Impact Thresholds

Default threshold rule: `"budget>20pct,keyword_add>5"`

| Proposal Type | Threshold | Above-threshold example |
|---|---|---|
| `budget_update` | budget change >20% | $50 → $75 (50% increase) |
| `keyword_add` | >5 keywords at once | Adding 10 new keywords |
| `keyword_remove` | any removal | Removing any keyword |
| `match_type_change` | any broad→exact | Changing 3+ keywords to exact match |

Below-threshold proposals auto-execute regardless of `hitl_enabled`.

---

## Reply Interpretation

`reply_handler.py` parses inbound email body (stripped of signature/quotes):

| Reply contains | Interpretation |
|---|---|
| `approve`, `yes`, `sounds good`, `do it`, `go ahead` | `approved` |
| `reject`, `no`, `not this time`, `decline`, `skip` | `rejected` |
| anything else | stored as `replier_response`, follow-up generated |

Inbound email: Resend inbound webhook POSTs to `POST /webhooks/inbound-email` — validated via `RESEND_INBOUND_SECRET`.

---

## Environment Variables

```env
RESEND_API_KEY=re_xxxxx               # Resend API key
RESEND_INBOUND_SECRET=xxxxx           # Webhook validation secret
HITL_ENABLED=false                     # Global kill-switch (default off)
HITL_DEFAULT_EMAIL=                   # Fallback recipient when owner_email not set
HITL_PROPOSAL_TTL_DAYS=7             # Auto-expire pending proposals after N days
HITL_WEEKLY_CRON=*/5 * * * *        # Every 5 minutes
```

---

## Implementation Order

1. **DB migration** — add columns + `hitl_proposals` table
2. **`email_service.py`** — Resend SDK wrapper, send methods only (no reply handling yet)
3. **`impact_assessor.py`** — threshold rules evaluator
4. **`hitl_adapter.py`** — CRUD for `hitl_proposals`
5. **Green Team modification** — check impact assessor after proposal creation
6. **`weekly_digest.py`** — weekly cron for digest emails
7. **`reply_handler.py`** + Resend inbound webhook endpoint
8. **`PATCH /campaigns/{uuid}`** — update hitl fields
9. **`GET /campaigns/{uuid}/hitl/proposals`** + **`POST .../decide`**
10. **Tests + adversarial review**

---

## Open Questions (flag for user review)

1. **Inbound email routing**: Resend inbound emails POST to a webhook URL. Does the droplet have a public URL for this, or should we use a forward-to-webhook approach?
2. **Proposal reasoning length**: Green Team reasoning can be long. Should the email include the full reasoning or a 2-3 sentence summary with a link to the full plan?
3. **Expiration action**: When a proposal expires after 7 days with no response — should it be `rejected` or just `expired` (a third state)?
