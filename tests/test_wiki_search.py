"""
RED: Failing tests for wiki search API end-to-end using full FastAPI app.
"""
import uuid
from datetime import datetime

import pytest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def mock_api_key(monkeypatch):
    monkeypatch.setattr("src.api.middleware.get_admin_api_key", lambda: "test-secret-key")


@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.wiki._adapter", lambda: mock)
    return mock


@pytest.fixture
def client(mock_api_key, mock_adapter):
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-secret-key"}


def _make_wiki_row(title: str, slug: str) -> dict:
    return {
        "id": uuid.uuid4(),
        "title": title,
        "slug": slug,
        "content": f"Content about {title}",
        "sources": [{"url": "https://example.com/ref", "title": "Reference"}],
        "green_rationale": "Green team rationale",
        "red_objections": [],
        "consensus_note": None,
        "tags": ["test"],
        "created_at": datetime(2026, 4, 7, 10, 0, 0),
        "updated_at": datetime(2026, 4, 7, 10, 0, 0),
        "verified_at": None,
        "invalidated_at": None,
        "invalidation_reason": None,
    }


def test_search_wiki(client, auth_headers, mock_adapter):
    mock_adapter.search_wiki.return_value = [_make_wiki_row("Keyword Optimization", "keyword-optimization")]

    response = client.get("/wiki/search?query=keyword+optimization", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["entries"]) == 1
    assert response.json()["entries"][0]["title"] == "Keyword Optimization"


def test_search_wiki_requires_auth(client):
    response = client.get("/wiki/search?query=keyword+optimization")
    assert response.status_code == 401


def test_get_wiki_entry(client, auth_headers, mock_adapter):
    entry_id = uuid.uuid4()
    mock_adapter.get_wiki_entry.return_value = {
        **_make_wiki_row("Quality Score", "quality-score"),
        "id": entry_id,
    }

    response = client.get(f"/wiki/{entry_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["title"] == "Quality Score"


def test_get_wiki_entry_not_found(client, auth_headers, mock_adapter):
    mock_adapter.get_wiki_entry.return_value = None

    response = client.get(f"/wiki/{uuid.uuid4()}", headers=auth_headers)

    assert response.status_code == 404
