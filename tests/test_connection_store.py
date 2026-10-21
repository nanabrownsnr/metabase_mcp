"""Tests for ConnectionStore: encrypted per-(user_id, persona_id) Metabase creds."""

from __future__ import annotations

import pytest

from app import connection_store


@pytest.mark.asyncio
async def test_save_then_get_roundtrip(store):
    await store.save("u1", "p1", {"base_url": "https://mb.test", "api_key": "sk-abc"})
    got = await store.get("u1", "p1")
    assert got["base_url"] == "https://mb.test"
    assert got["api_key"] == "sk-abc"


@pytest.mark.asyncio
async def test_get_never_crosses_persona(store):
    await store.save("u1", "p1", {"base_url": "https://mb.test", "api_key": "sk-abc"})
    # Same user, different persona → no connection.
    assert await store.get("u1", "p2") is None
    # Different user → no connection.
    assert await store.get("u2", "p1") is None


@pytest.mark.asyncio
async def test_public_metadata_excludes_api_key(store):
    await store.save("u1", "p1", {"base_url": "https://mb.test", "api_key": "sk-secret"})
    meta = await store.public_metadata("u1", "p1")
    assert meta["base_url"] == "https://mb.test"
    assert "api_key" not in meta
    assert "sk-secret" not in str(meta)


@pytest.mark.asyncio
async def test_upsert_updates_existing(store):
    await store.save("u1", "p1", {"base_url": "https://old", "api_key": "k1"})
    await store.save("u1", "p1", {"base_url": "https://new", "api_key": "k2"})
    got = await store.get("u1", "p1")
    assert got["base_url"] == "https://new"
    assert got["api_key"] == "k2"
    # Only one doc for the pair.
    assert len(store.collection.docs) == 1


@pytest.mark.asyncio
async def test_setup_creates_unique_index(store):
    await store.setup()
    assert any(unique for _, unique in store.collection.indexes)
