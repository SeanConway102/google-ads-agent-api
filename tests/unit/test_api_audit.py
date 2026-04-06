"""
RED: Write the failing test first.
Tests for src/api/routes/audit.py — Audit log query endpoint.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.audit import router


@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.audit.PostgresAdapter", lambda: mock)
    return mock


@pytest.fixture
def audit_app(mock_adapter):
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(audit_app):
    return TestClient(audit_app, raise_server_exceptions=False)


def make_audit_row(
    action_type: str = "campaign_created",
    campaign_id: uuid.UUID | None = None,
) -> dict:
    return {
        "id": 1,
        "cycle_date": "2026-04-06",
        "campaign_id": campaign_id or uuid.uuid4(),
        "action_type": action_type,
        "target": {"campaign_id": "cmp_001"},
        "green_proposal": None,
        "red_objections": None,
        "coordinator_note": None,
        "debate_rounds": None,
        "performed_at": datetime(2026, 4, 6, 10, 0, 0),
    }


class TestQueryAuditLog:

    def test_query_returns_all_entries(self, client, mock_adapter):
        rows = [make_audit_row(), make_audit_row("wiki_created")]
        mock_adapter.query_audit_log.return_value = rows

        response = client.get("/audit")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_query_filters_by_campaign_id(self, client, mock_adapter):
        campaign_id = uuid.uuid4()
        rows = [make_audit_row(campaign_id=campaign_id)]
        mock_adapter.query_audit_log.return_value = rows

        response = client.get(f"/audit?campaign_id={campaign_id}")

        assert response.status_code == 200
        mock_adapter.query_audit_log.assert_called_once()
        call_kwargs = mock_adapter.query_audit_log.call_args.kwargs
        assert call_kwargs["campaign_id"] == campaign_id

    def test_query_filters_by_action_type(self, client, mock_adapter):
        rows = [make_audit_row("consensus_reached")]
        mock_adapter.query_audit_log.return_value = rows

        response = client.get("/audit?action_type=consensus_reached")

        assert response.status_code == 200
        call_kwargs = mock_adapter.query_audit_log.call_args.kwargs
        assert call_kwargs["action_type"] == "consensus_reached"

    def test_query_filters_by_cycle_date(self, client, mock_adapter):
        rows = [make_audit_row()]
        mock_adapter.query_audit_log.return_value = rows

        response = client.get("/audit?cycle_date=2026-04-06")

        assert response.status_code == 200
        call_kwargs = mock_adapter.query_audit_log.call_args.kwargs
        assert call_kwargs["cycle_date"] == "2026-04-06"

    def test_query_respects_limit(self, client, mock_adapter):
        mock_adapter.query_audit_log.return_value = []

        response = client.get("/audit?limit=50")

        call_kwargs = mock_adapter.query_audit_log.call_args.kwargs
        assert call_kwargs["limit"] == 50

    def test_query_default_limit_is_100(self, client, mock_adapter):
        mock_adapter.query_audit_log.return_value = []

        response = client.get("/audit")

        call_kwargs = mock_adapter.query_audit_log.call_args.kwargs
        assert call_kwargs["limit"] == 100
