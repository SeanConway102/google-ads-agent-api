"""
RED: Write the failing test first.
Tests for src/api/routes/wiki.py — Wiki CRUD + search endpoints.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.wiki import router


@pytest.fixture
def mock_adapter(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.api.routes.wiki.PostgresAdapter", lambda: mock)
    return mock


@pytest.fixture
def wiki_app(mock_adapter):
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(wiki_app):
    return TestClient(wiki_app, raise_server_exceptions=False)


def make_wiki_row(
    title: str = "Keyword Research",
    slug: str = "keyword-research",
    content: str = "Research on keywords...",
) -> dict:
    return {
        "id": uuid.uuid4(),
        "title": title,
        "slug": slug,
        "content": content,
        "sources": [],
        "green_rationale": None,
        "red_objections": [],
        "consensus_note": None,
        "tags": [],
        "created_at": datetime(2026, 4, 6, 10, 0, 0),
        "updated_at": datetime(2026, 4, 6, 10, 0, 0),
        "verified_at": None,
        "invalidated_at": None,
    }


class TestSearchWiki:

    def test_search_returns_results(self, client, mock_adapter):
        row = make_wiki_row()
        mock_adapter.search_wiki.return_value = [row]

        response = client.get("/wiki/search?query=keywords&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "keywords"
        assert data["limit"] == 10
        assert len(data["entries"]) == 1
        assert data["entries"][0]["title"] == "Keyword Research"
        mock_adapter.search_wiki.assert_called_once_with("keywords", limit=10)

    def test_search_empty_results(self, client, mock_adapter):
        mock_adapter.search_wiki.return_value = []

        response = client.get("/wiki/search?query=nonexistent")

        assert response.status_code == 200
        assert response.json()["entries"] == []

    def test_search_requires_query(self, client):
        response = client.get("/wiki/search")
        assert response.status_code == 422


class TestCreateWikiEntry:

    def test_create_returns_201(self, client, mock_adapter):
        row = make_wiki_row()
        mock_adapter.create_wiki_entry.return_value = row

        response = client.post(
            "/wiki",
            json={
                "title": "Keyword Research",
                "slug": "keyword-research",
                "content": "Research on keywords...",
                "api_key_token": "tok_abc",
            },
        )

        assert response.status_code == 201
        assert response.json()["title"] == "Keyword Research"

    def test_create_requires_title(self, client):
        response = client.post("/wiki", json={"slug": "s", "content": "c", "api_key_token": "tok"})
        assert response.status_code == 422

    def test_create_requires_content(self, client):
        response = client.post("/wiki", json={"title": "t", "slug": "s", "api_key_token": "tok"})
        assert response.status_code == 422


class TestGetWikiEntry:

    def test_get_returns_200(self, client, mock_adapter):
        entry_id = uuid.uuid4()
        row = make_wiki_row()
        row["id"] = entry_id
        mock_adapter.get_wiki_entry.return_value = row

        response = client.get(f"/wiki/{entry_id}")

        assert response.status_code == 200
        assert response.json()["title"] == "Keyword Research"

    def test_get_not_found_returns_404(self, client, mock_adapter):
        mock_adapter.get_wiki_entry.return_value = None
        unknown_id = uuid.uuid4()

        response = client.get(f"/wiki/{unknown_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Wiki entry not found"


class TestInvalidateWikiEntry:

    def test_invalidate_returns_204(self, client, mock_adapter):
        entry_id = uuid.uuid4()
        row = make_wiki_row()
        row["id"] = entry_id
        mock_adapter.get_wiki_entry.return_value = row

        response = client.delete(f"/wiki/{entry_id}?reason=outdated")

        assert response.status_code == 204
        mock_adapter.invalidate_wiki_entry.assert_called_once_with(entry_id, "outdated")

    def test_invalidate_not_found_returns_404(self, client, mock_adapter):
        mock_adapter.get_wiki_entry.return_value = None
        unknown_id = uuid.uuid4()

        response = client.delete(f"/wiki/{unknown_id}?reason=old")

        assert response.status_code == 404

    def test_invalidate_requires_reason(self, client):
        entry_id = uuid.uuid4()
        response = client.delete(f"/wiki/{entry_id}")
        assert response.status_code == 422
