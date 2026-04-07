#!/usr/bin/env python3
"""
Manually trigger a research cycle — useful for testing or on-demand runs.
Must be run from the project root or with PYTHONPATH set.

Usage:
    python scripts/run_research_cycle.py                 # run all campaigns
    python scripts/run_research_cycle.py --campaign-id <uuid>  # run single campaign
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _main() -> None:
    """Parse CLI args and run the research cycle."""
    parser = argparse.ArgumentParser(
        description="Manually trigger a research cycle",
    )
    parser.add_argument(
        "--campaign-id",
        dest="campaign_id",
        default=None,
        help="Run research for a specific campaign UUID only (omit for all campaigns)",
    )
    args = parser.parse_args()

    from src.cron.daily_research import run_daily_research
    run_daily_research(target_campaign_id=args.campaign_id)


if __name__ == "__main__":
    _main()
