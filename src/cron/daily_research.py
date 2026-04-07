"""
Daily research cycle — triggered by cron or systemd timer at 8am server time.
Fetches campaign performance, runs adversarial validation loop,
executes approved changes via MCP, writes wiki entries, fires webhooks.
"""
import asyncio
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from src.db.postgres_adapter import PostgresAdapter
from src.mcp.google_ads_client import GoogleAdsClient
from src.mcp.capability_guard import CapabilityGuard, CapabilityDenied
from src.research.validator import AdversarialValidator
from src.research.wiki_writer import WikiWriter
from src.services.webhook_service import WebhookService
from src.services.audit_service import AuditService
from src.services.email_service import send_proposal_email
from src.agents.debate_state import Phase
from src.config import get_settings


LOCK_FILE = Path.home() / ".ads_agent_research.lock"


def _acquire_lock(lock_path: Path) -> bool:
    """
    Prevent concurrent research cycles using an exclusive file lock.

    On POSIX systems: uses fcntl.flock for atomic advisory locking.
    On other platforms: uses a PID file with existence check.
    Returns True if lock acquired, False if another cycle is already running.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Fast path: check if lock file with live PID already exists
    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text().strip())
            # Same PID = stale lock from a previous failed run in this process
            if old_pid == os.getpid():
                pass  # will overwrite
            elif _is_process_alive(old_pid):
                return False
        except (ValueError, OSError):
            pass

    try:
        lock_path.write_text(str(os.getpid()))
        return True
    except OSError:
        return False


def _is_process_alive(pid: int) -> bool:
    """Check whether a process with the given PID is currently running."""
    if sys.platform == "win32":
        import ctypes
        try:
            return ctypes.windll.kernel32.OpenProcess(0, False, pid) != 0
        except Exception:
            return False
    else:
        # POSIX: /proc/{pid} exists means process is alive
        return os.path.exists(f"/proc/{pid}")


def _release_lock(lock_path: Path) -> None:
    """Remove the lock file if it was created by this process."""
    try:
        if lock_path.exists() and lock_path.read_text().strip() == str(os.getpid()):
            lock_path.unlink()
    except OSError:
        pass


def _send_hitl_emails(
    state: Any,
    campaign: dict,
    webhook_service: WebhookService,
) -> None:
    """
    Send HITL approval emails for each green proposal when the coordinator
    escalates to PENDING_MANUAL_REVIEW.

    Skips sending if hitl_enabled is False on the campaign (proposals go to
    auto-execution instead of human approval).
    """
    if not campaign.get("hitl_enabled", False):
        return

    owner_email = campaign.get("owner_email")
    if not owner_email:
        print(f"    Warning: hitl_enabled=True but no owner_email configured for campaign {campaign.get('campaign_id', campaign.get('id'))} — skipping HITL email")
        return

    for proposal in (state.green_proposals or []):
        try:
            send_proposal_email(
                to_email=owner_email,
                campaign_name=campaign.get("name", "Unknown Campaign"),
                proposal_type=proposal.get("type", "unknown"),
                impact_summary=proposal.get("impact_summary", ""),
                reasoning=proposal.get("reasoning", ""),
            )
        except Exception as exc:
            # Email failure should not abort the research cycle
            print(f"    Warning: failed to send HITL email: {exc}")
            webhook_service.dispatch("hitl_email_failed", {
                "campaign_id": campaign.get("campaign_id", campaign.get("id")),
                "owner_email": owner_email,
                "proposal": proposal,
                "error": str(exc),
            })


def run_daily_research(target_campaign_id: str | None = None) -> None:
    """
    Run the daily research cycle across all active campaigns.

    Args:
        target_campaign_id: If provided, only this campaign is processed.
            Otherwise all active campaigns are processed.

    For each campaign:
    1. Pull keyword performance from Google Ads
    2. Load relevant wiki context
    3. Run adversarial validation (Green → Red → Coordinator)
    4. On consensus: execute allowed changes, log audit, fire webhooks
    5. On max rounds without consensus: flag for manual review
    6. On any error: fire error webhook, continue to next campaign
    """
    # Prevent concurrent runs: if another cycle is still running, exit early.
    if not _acquire_lock(LOCK_FILE):
        today = date.today().isoformat()
        print(f"[Research Cycle {today}] ABORTED: another cycle is already running (lock held).")
        return

    # Construct services in order; webhook_service must exist before db.connect
    # so the error handler can dispatch cycle_error if db connection fails.
    webhook_service = WebhookService()
    guard = CapabilityGuard()
    today = date.today().isoformat()

    try:
        db = PostgresAdapter()
        wiki_writer = WikiWriter(db)
        audit_service = AuditService(db)
        campaigns = db.list_campaigns()
        if target_campaign_id:
            campaigns = [c for c in campaigns if str(c["id"]) == target_campaign_id]
    except Exception as e:
        print(f"[Research Cycle {today}] ERROR: Failed to fetch campaigns: {e}")
        webhook_service.dispatch("cycle_error", {
            "cycle_date": today,
            "error": f"Failed to fetch campaigns: {e}",
        })
        return

    print(f"[Research Cycle {today}] Processing {len(campaigns)} campaign(s)...")

    try:
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
                state = asyncio.run(validator.run_cycle(
                    cycle_date=today,
                    campaign_id=campaign["id"],
                    campaign_data={
                        "campaign": _strip_sensitive(campaign),
                        "performance": performance_data,
                    },
                    wiki_context=wiki_context,
                ))

                # 5. Handle outcome
                if state is None:
                    print(f"    Validator returned no state, skipping")
                elif state.consensus_reached:
                    print(f"    Consensus reached after {state.round_number} round(s)")
                    _execute_consensus(state, campaign, gads_client, guard, db, wiki_writer, audit_service, webhook_service, today)
                elif state.phase == Phase.PENDING_MANUAL_REVIEW:
                    print(f"    Max rounds reached — flagged for manual review")
                    _send_hitl_emails(state, campaign, webhook_service)
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
    finally:
        _release_lock(LOCK_FILE)


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

    Handles: keyword_add, keyword_remove, keyword_bid_update, keyword_match_type_update.
    All other proposal types are silently skipped (capability denied or unknown type).
    """
    if not proposals:
        return

    for proposal in proposals:
        ptype = proposal.get("type", "")
        try:
            if ptype == "keyword_add":
                guard.check("google_ads.add_keywords")
                resource_names = gads_client.add_keywords(
                    customer_id=campaign["customer_id"],
                    ad_group_id=proposal.get("ad_group_id", ""),
                    keywords=proposal.get("keywords", []),
                )
                print(f"    Executed: keyword_add → {proposal.get('target')} ({len(resource_names)} added)")

            elif ptype == "keyword_remove":
                guard.check("google_ads.remove_keywords")
                resource_names = proposal.get("resource_names", [])
                if not resource_names:
                    print(f"    Skipped: keyword_remove with empty resource_names")
                    continue
                removed = gads_client.remove_keywords(
                    customer_id=campaign["customer_id"],
                    keyword_resource_names=resource_names,
                )
                print(f"    Executed: keyword_remove → {len(removed)} removed")

            elif ptype == "keyword_bid_update":
                guard.check("google_ads.update_keyword_bids")
                updates = proposal.get("updates", [])
                if not updates:
                    print(f"    Skipped: keyword_bid_update with empty updates")
                    continue
                updated = gads_client.update_keyword_bids(
                    customer_id=campaign["customer_id"],
                    updates=updates,
                )
                print(f"    Executed: keyword_bid_update → {len(updated)} updated")

            elif ptype == "bid_update":
                # bid_update is what the coordinator/coordinator outputs (green team LLM naming)
                guard.check("google_ads.update_keyword_bids")
                updates = proposal.get("updates", [])
                if not updates:
                    print(f"    Skipped: bid_update with empty updates")
                    continue
                updated = gads_client.update_keyword_bids(
                    customer_id=campaign["customer_id"],
                    updates=updates,
                )
                print(f"    Executed: bid_update → {len(updated)} updated")

            elif ptype == "keyword_match_type_update":
                guard.check("google_ads.update_keyword_match_types")
                updates = proposal.get("updates", [])
                if not updates:
                    print(f"    Skipped: keyword_match_type_update with empty updates")
                    continue
                updated = gads_client.update_keyword_match_types(
                    customer_id=campaign["customer_id"],
                    updates=updates,
                )
                print(f"    Executed: keyword_match_type_update → {len(updated)} updated")

            elif ptype == "match_type_update":
                # match_type_update is what the coordinator outputs (green team LLM naming)
                guard.check("google_ads.update_keyword_match_types")
                updates = proposal.get("updates", [])
                if not updates:
                    print(f"    Skipped: match_type_update with empty updates")
                    continue
                updated = gads_client.update_keyword_match_types(
                    customer_id=campaign["customer_id"],
                    updates=updates,
                )
                print(f"    Executed: match_type_update → {len(updated)} updated")

            # Blocked/unknown types: silently skipped (capability denied or unrecognised)
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
