"""
RED: README API path verification test.
Routes documented in README must match what the router actually mounts.
"""
import pytest
from fastapi.routing import APIRoute
from src.main import app


def test_readme_campaign_routes_exist_at_documented_paths():
    """README says GET/POST /campaigns — verify these are registered."""
    routes = {r.path: r for r in app.routes if hasattr(r, 'path')}

    # Campaign CRUD (README: /campaigns)
    assert "/campaigns" in routes, "GET /campaigns not found in app"
    assert "/campaigns/{campaign_id}" in routes, "GET /campaigns/{id} not found"


def test_readme_wiki_routes_exist():
    """Wiki routes exist at /wiki (not /research/wiki)."""
    routes = {r.path: r for r in app.routes if hasattr(r, 'path')}
    assert "/wiki" in routes, "GET /wiki not found in app"


def test_readme_hitl_routes_exist():
    """README should document HITL routes for PATCH, list, decide."""
    routes = {r.path: r for r in app.routes if hasattr(r, 'path')}

    # HITL routes
    assert "/campaigns/{campaign_id}/hitl/proposals" in routes, "HITL proposals list route missing"
    assert "/campaigns/{campaign_id}/hitl/proposals/{proposal_id}" in routes, "HITL single proposal route missing"
    assert "/campaigns/{campaign_id}/hitl/proposals/{proposal_id}/decide" in routes, "HITL decide route missing"


def test_readme_audit_and_webhook_routes_exist():
    """README says /audit and /webhooks."""
    routes = {r.path: r for r in app.routes if hasattr(r, 'path')}
    assert "/audit" in routes, "GET /audit not found"
    assert "/webhooks" in routes, "/webhooks not found"
