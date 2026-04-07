"""
RED: README API path verification test.
Routes documented in README must match what the router actually mounts.
"""
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


def test_all_mounted_routes_are_documented_in_readme():
    """
    Every route mounted in the FastAPI app must be documented in README.md.
    This ensures API surface and documentation stay in sync.
    """
    import pathlib
    readme_path = pathlib.Path(__file__).parents[2] / "README.md"
    readme_content = readme_path.read_text(encoding="utf-8")

    # Collect all non-exempt mounted routes (skip docs/health/openapi/redoc)
    exempt_paths = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc", "/health"}
    routes = {
        r.path: list(r.methods - {"HEAD", "OPTIONS"})
        for r in app.routes
        if hasattr(r, 'methods')
    }

    undocumented = []
    for path, methods in routes.items():
        if path in exempt_paths:
            continue
        # Simple substring check — README uses literal paths like /campaigns/{id}
        if path not in readme_content:
            undocumented.append(f"{list(methods)} {path}")

    assert not undocumented, (
        f"The following routes are mounted but NOT documented in README.md:\n"
        + "\n".join(f"  {u}" for u in undocumented)
        + "\n\nUpdate README.md API Endpoints table to include these routes."
    )
