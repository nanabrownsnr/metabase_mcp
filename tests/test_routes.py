"""In-process HTTP tests for the Twynity custom routes (no real Mongo needed).

Boots the FastMCP ASGI app with a stubbed Mongo + connection store, and exercises
/api/v1/* routes via starlette's TestClient (sync) wrapping the async app.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from fastmcp import FastMCP
from starlette.testclient import TestClient

from app import connection_store
from app.config import settings
from app.tools import metabase as tools_mod
from app.twynity import register_routes


def _build_app() -> FastMCP:
    mcp = FastMCP(settings.APP_TITLE)
    tools_mod.register_tools(mcp)
    register_routes(mcp)
    return mcp


class StubStore:
    """ConnectionStore stand-in backed by an in-memory dict."""

    def __init__(self):
        self.docs = {}

    async def save(self, user_id, persona_id, values):
        self.docs[(user_id, persona_id)] = dict(values)
        return "ok"

    async def get(self, user_id, persona_id):
        return self.docs.get((user_id, persona_id))

    async def public_metadata(self, user_id, persona_id):
        doc = self.docs.get((user_id, persona_id))
        if not doc:
            return None
        return {
            "id": "stub",
            "base_url": doc.get("base_url"),
            "api_key": "•" * 4,  # never expose the key
        }


@pytest.fixture
def client():
    app = _build_app()
    asgi = app.http_app()
    store = StubStore()
    from app import twynity as twynity_mod
    from app.tools import connection as conn_mod

    class _Id:
        user_id = "u1"
        persona_id = "p1"

    # twynity.py imports get_identity_require_persona by name for the
    # connection routes; tools/connection.py imports get_identity_from_context (MCP transport path).
    # Patch the references in those modules (not just the source module).
    with patch.object(twynity_mod, "get_active_store", return_value=store), \
         patch.object(conn_mod, "get_active_store", return_value=store), \
         patch.object(twynity_mod, "get_identity_require_persona", return_value=_Id()):
        with TestClient(asgi) as tc:
            yield tc, store


def test_health(client):
    tc, _ = client
    r = tc.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_manifest(client):
    tc, _ = client
    r = tc.get("/api/v1/.well-known/mcp.json")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == settings.APP_TITLE
    assert "base_url" in body


def test_schema_lists_two_fields(client):
    tc, _ = client
    r = tc.get("/api/v1/schema")
    assert r.status_code == 200
    body = r.json()
    assert set(body["schema"].keys()) == {"base_url", "api_key"}


def test_configuration_post_requires_both_fields(client):
    tc, store = client
    # Missing api_key → 422
    r = tc.post("/api/v1/configuration", json={"base_url": "https://mb.test"})
    assert r.status_code == 422
    assert "api_key" in r.json()["detail"]["missing_or_invalid_fields"]
    # Both present → configured
    r = tc.post(
        "/api/v1/configuration",
        json={"base_url": "https://mb.test", "api_key": "sk-1"},
    )
    assert r.status_code == 200
    assert r.json() == {"configured": True}
    assert store.docs[("u1", "p1")]["base_url"] == "https://mb.test"


def test_configuration_get_returns_metadata_not_secret(client):
    tc, store = client
    store.docs[("u1", "p1")] = {"base_url": "https://mb.test", "api_key": "sk-secret"}
    r = tc.get("/api/v1/configuration")
    assert r.status_code == 200
    body = r.json()
    assert body["item_count"] == 1
    assert body["items"][0]["base_url"] == "https://mb.test"
    assert "sk-secret" not in r.text


def test_external_connection_me(client):
    tc, store = client
    # Not configured
    assert tc.get("/api/v1/external-connection/me").json()["connected"] is False
    store.docs[("u1", "p1")] = {"base_url": "https://mb.test", "api_key": "sk-1"}
    assert tc.get("/api/v1/external-connection/me").json()["connected"] is True
