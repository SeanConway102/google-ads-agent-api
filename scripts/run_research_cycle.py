#!/usr/bin/env python3
"""
Manually trigger a research cycle — useful for testing or on-demand runs.
Must be run from the project root or with PYTHONPATH set.
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cron.daily_research import run_daily_research

if __name__ == "__main__":
    run_daily_research()
