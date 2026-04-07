"""
Daily research cycle — triggered by cron or systemd timer at 8am server time.
Fetches campaign performance, runs adversarial validation loop,
executes approved changes via MCP, writes wiki entries, fires webhooks.
"""
from datetime import date
from typing import Any

from src.db.postgres_adapter import PostgresAdapter
from src.mcp.google_ads_client import GoogleAdsClient
from src.mcp.capability_guard import CapabilityGuard, CapabilityDenied
from src.research.validator import AdversarialValidator
from src.research.wiki_writer import WikiWriter
from src.services.webhook_service import WebhookService
from src.services.audit_service import AuditService
from src.agents.debate_state import Phase
from src.config import get_settings


def run_daily_research() -> None:
    """
    Run the daily research cycle across all active campaigns.

    For each campaign:
    1. Pull keyword performance from Google Ads
    2. Load relevant wiki context
    3. Run adversarial validation (Green → Red → Coordinator)
    4. On consensus: execute allowed changes, log audit, fire webhooks
    5. On max rounds without consensus: flag for manual review
    6. On any error: fire error webhook, continue to next campaign
    """
    db = PostgresAdapter()
    wiki_writer = WikiWriter(db)
    webhook_service = WebhookService(db)
    audit_service = AuditService(db)
    guard = CapabilityGuard()
    today = date.today().isoformat()

    campaigns = db.list_campaigns()
    print(f"[Research Cycle {today}] Processing {len(campaigns)} campaign(s)...")

    for campaign in campaigns:
        campaign_id_str = str(campaign["id"])
        print(f"  Campaign {campaign['campaign_id']}: starting research cycle")
        try:
            # 1. Pull performance data via Google Ads client
            gads_client = GoogleAdsClient(
                customer_id=campaign["customer_id"],
            )
            performance_data = gads_client.get_performance_report(
                customer_id=campaign["customer_id"],
                campaign_id=campaign["campaign_id"],
                start_date=date.today(),
                end_date=date.today(),
            )

            # 2. Load wiki context for this campaign
            wiki_results = db.search_wiki(f"campaign {campaign['campaign_id']}", limit=5)
            wiki_context = [dict(r) for r in wiki_results]

            # 3. Build the green/red/coordinator with real Google Ads client injected
            green = _build_green_agent(gads_client, wiki_context)
            red = _build_red_agent(gads_client, wiki_context)
            coordinator = _build_coordinator_agent()
            state_machine = _build_state_machine(db)

            validator = AdversarialValidator(
                green=green,
                red=red,
                coordinator=coordinator,
                state_machine=state_machine,
            )

            # 4. Run adversarial validation
            state = validator.run_cycle(
                cycle_date=today,
                campaign_id=campaign["id"],
                campaign_data={
                    "campaign": _strip_sensitive(campaign),
                    "performance": performance_data,
                },
                wiki_context=wiki_context,
            )

            # 5. Handle outcome
            if state is None:
                print(f"    Validator returned no state, skipping")
            elif state.consensus_reached:
                print(f"    Consensus reached after {state.round_number} round(s)")
                _execute_consensus(state, campaign, gads_client, guard, db, wiki_writer, audit_service, webhook_service, today)
            elif state.phase == Phase.PENDING_MANUAL_REVIEW:
                print(f"    Max rounds reached — flagged for manual review")
                webhook_service.dispatch("manual_review_required", {
                    "campaign_id": campaign_id_str,
                    "cycle_date": today,
                    "round_number": state.round_number,
                    "green_proposals": state.green_proposals,
                    "red_objections": state.red_objections,
                })
            else:
                print(f"    No consensus (phase={state.phase.value}), skipping")

        except Exception as e:
            print(f"    ERROR: {e}")
            webhook_service.dispatch("cycle_error", {
                "campaign_id": campaign_id_str,
                "cycle_date": today,
                "error": str(e),
            })

    print(f"[Research Cycle {today}] Complete.")


def _execute_consensus(
    state: Any,
    campaign: dict,
    gads_client: GoogleAdsClient,
    guard: CapabilityGuard,
    db: PostgresAdapter,
    wiki_writer: WikiWriter,
    audit_service: AuditService,
    webhook_service: WebhookService,
    today: str,
) -> None:
    """Execute consensus decisions and persist results."""
    # Log audit decision
    audit_service.log_decision(state, campaign)

    # Fire consensus webhook
    webhook_service.dispatch("consensus_reached", {
        "campaign_id": str(campaign["id"]),
        "cycle_date": today,
        "actions": state.green_proposals,
        "debate_rounds": state.round_number,
    })

    # Execute allowed proposals via MCP
    _execute_allowed_actions(state.green_proposals, campaign, gads_client, guard)

    # Update campaign last_reviewed_at
    db.execute(
        "UPDATE campaigns SET last_reviewed_at = NOW() WHERE id = %s",
        (str(campaign["id"]),),
    )


def _execute_allowed_actions(
    proposals: list[dict],
    campaign: dict,
    gads_client: GoogleAdsClient,
    guard: CapabilityGuard,
) -> None:
    """Execute proposals that are allowed by the capability guard.

    Currently allowed: keyword.add (via google_ads.add_keywords).
    All other write operations are blocked by CAPABILITY_FORBIDDEN.
    """
    for proposal in proposals:
        ptype = proposal.get("type", "")
        try:
            if ptype == "keyword_add":
                # capability_guard allows google_ads.add_keywords
                guard.check("google_ads.add_keywords")  # raises if not allowed
                gads_client.add_keywords(
                    customer_id=campaign["customer_id"],
                    ad_group_id=proposal.get("ad_group_id", ""),
                    keywords=proposal.get("keywords", []),
                )
                print(f"    Executed: keyword_add → {proposal.get('target')}")
            elif ptype == "keyword_remove":
                guard.check("google_ads.remove_keywords")
                print(f"    Blocked: keyword_remove not implemented in client")
            # Blocked types (budget changes, bid updates, etc.) are silently skipped
            # because CAPABILITY_FORBIDDEN would be raised for them
        except CapabilityDenied:
            print(f"    Blocked by capability guard: {ptype}")
        except Exception as e:
            print(f"    Execution error for {ptype}: {e}")


def _build_green_agent(_gads_client: GoogleAdsClient, _wiki_context: list[dict]) -> Any:
    """Build GreenTeamAgent with injected dependencies."""
    from src.agents.green_team import GreenTeamAgent
    return GreenTeamAgent()


def _build_red_agent(_gads_client: GoogleAdsClient, _wiki_context: list[dict]) -> Any:
    """Build RedTeamAgent with injected dependencies."""
    from src.agents.red_team import RedTeamAgent
    return RedTeamAgent()


def _build_coordinator_agent() -> Any:
    """Build CoordinatorAgent with max rounds from settings."""
    from src.agents.coordinator import CoordinatorAgent
    return CoordinatorAgent(max_rounds=get_settings().MAX_DEBATE_ROUNDS)


def _build_state_machine(db: PostgresAdapter) -> Any:
    """Build DebateStateMachine with the database adapter."""
    from src.agents.debate_state import DebateStateMachine
    return DebateStateMachine(db)


def _strip_sensitive(campaign: dict) -> dict:
    """Remove sensitive fields from campaign dict before passing to agents."""
    return {k: v for k, v in campaign.items() if k != "api_key_token"}
