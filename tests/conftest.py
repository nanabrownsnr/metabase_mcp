"""Shared pytest fixtures: env defaults + in-memory Mongo stand-in + Fernet key."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet

# Set env defaults BEFORE importing app.* so Settings() construction succeeds.
os.environ.setdefault("USAGE_REPORT_ENDPOINT", "http://usage.invalid/report")
os.environ.setdefault("ACCOUNT_SERVICE_URL", "http://account.invalid")
os.environ.setdefault("ACCOUNT_SERVICE_JWKS_ENDPOINT", "/.well-known/jwks.json")
os.environ.setdefault("ACCOUNT_SERVICE_JWKS_CACHE_TTL", "300")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("DATABASE_NAME", "test_mcp")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("PUBLIC_URL", "http://localhost:8000")
os.environ.setdefault("LICENSE_KEY", "test-license")
os.environ.setdefault("LICENSE_SERVER_BASE_URL", "http://license.invalid")
os.environ.setdefault("LICENSE_SERVER_JWKS_ENDPOINT", "/.well-known/jwks.json")
os.environ.setdefault("LICENSE_SERVER_ACTIVATION_ENDPOINT", "/activate")

from app import connection_store  # noqa: E402


class FakeCollection:
    """Minimal async stand-in for a pymongo collection used by ConnectionStore."""

    def __init__(self):
        self.docs = {}
        self.indexes = []

    async def create_index(self, keys, unique=False):
        self.indexes.append((keys, unique))

    async def update_one(self, filter, update, upsert=False):
        key = (filter["user_id"], filter["persona_id"])
        if key in self.docs:
            self.docs[key]["values"].update(update.get("$set", {}).get("values", {}))
            self.docs[key]["modified"] = update.get("$set", {}).get("modified")
            return _UpsertResult(None)
        doc = {
            "_id": object(),
            "values": dict(update.get("$set", {}).get("values", {})),
            "modified": update.get("$set", {}).get("modified"),
            "created": update.get("$setOnInsert", {}).get("created"),
        }
        self.docs[key] = doc
        return _UpsertResult(id(doc["_id"]))

    async def find_one(self, filter, projection=None):
        key = (filter.get("user_id"), filter.get("persona_id"))
        doc = self.docs.get(key)
        if not doc:
            return None
        if projection and isinstance(projection, dict):
            out = {"_id": doc["_id"], "values": {}}
            for field in projection:
                if field.startswith("values."):
                    sub = field.split(".", 1)[1]
                    if sub in doc["values"]:
                        out["values"][sub] = doc["values"][sub]
                elif field in doc:
                    out[field] = doc[field]
            return out
        return dict(doc)


class _UpsertResult:
    def __init__(self, upserted_id):
        self.upserted_id = upserted_id


@pytest.fixture
def fake_collection():
    return FakeCollection()


@pytest.fixture
def store(fake_collection):
    key = os.environ["ENCRYPTION_KEY"]
    s = connection_store.ConnectionStore(fake_collection, key)
    connection_store.set_active_store(s)
    yield s
    connection_store.set_active_store(None)
