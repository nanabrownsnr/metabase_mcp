"""Tests for the Metabase REST API client (mocked httpx)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.metabase_client import (
    MetabaseError,
    get_dashboard,
    health,
    list_databases,
    list_dashboards,
    run_card,
    search,
)

BASE = "https://metabase.test"
KEY = "sk-test"


def _resp(status=200, json_data=None, text=""):
    r = httpx.Response(status, request=httpx.Request("GET", BASE))
    if json_data is not None:
        r._content = str(json_data).encode()
        r.headers["content-type"] = "application/json"
    else:
        r._content = text.encode()
    return r


@pytest.mark.asyncio
async def test_health_returns_profile():
    with patch("app.metabase_client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.return_value = httpx.Response(
            200,
            json={"id": 1, "first_name": "Ada", "email": "ada@x.com"},
            request=httpx.Request("GET", BASE),
        )
        client_cls.return_value.__aenter__.return_value = client
        result = await health(BASE, KEY)
        assert result["first_name"] == "Ada"
        # API key header must be set
        _, kwargs = client.get.call_args
        assert kwargs["headers"]["X-API-Key"] == KEY


@pytest.mark.asyncio
async def test_search_builds_query():
    with patch("app.metabase_client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.return_value = httpx.Response(
            200, json={"results": [{"id": 5, "model": "card"}]},
            request=httpx.Request("GET", BASE),
        )
        client_cls.return_value.__aenter__.return_value = client
        result = await search(BASE, KEY, "revenue", ["card", "dashboard"])
        assert result["results"][0]["id"] == 5
        _, kwargs = client.get.call_args
        assert kwargs["params"]["term"] == "revenue"
        assert kwargs["params"]["models"] == "card,dashboard"


@pytest.mark.asyncio
async def test_list_databases_returns_list():
    with patch("app.metabase_client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.return_value = httpx.Response(
            200, json={"data": [{"id": 1, "name": "Sales", "engine": "postgres"}]},
            request=httpx.Request("GET", BASE),
        )
        client_cls.return_value.__aenter__.return_value = client
        dbs = await list_databases(BASE, KEY)
        assert dbs[0]["name"] == "Sales"


@pytest.mark.asyncio
async def test_list_dashboards_scoped_by_collection():
    with patch("app.metabase_client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.return_value = httpx.Response(
            200, json={"data": [{"id": 9, "name": "KPI"}]},
            request=httpx.Request("GET", BASE),
        )
        client_cls.return_value.__aenter__.return_value = client
        dash = await list_dashboards(BASE, KEY, collection_id=2)
        assert dash[0]["id"] == 9
        _, kwargs = client.get.call_args
        assert kwargs["params"]["collection_id"] == 2


@pytest.mark.asyncio
async def test_get_dashboard_url():
    with patch("app.metabase_client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.return_value = httpx.Response(
            200, json={"id": 9, "name": "KPI", "dashcards": [{"card_id": 7}]},
            request=httpx.Request("GET", BASE),
        )
        client_cls.return_value.__aenter__.return_value = client
        d = await get_dashboard(BASE, KEY, 9)
        assert d["dashcards"][0]["card_id"] == 7
        args, _ = client.get.call_args
        assert args[0].endswith("/api/dashboard/9")


@pytest.mark.asyncio
async def test_run_card_posts_query():
    with patch("app.metabase_client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.post.return_value = httpx.Response(
            200,
            json={"data": {"cols": [{"name": "x"}], "rows": [[1]]}},
            request=httpx.Request("POST", BASE),
        )
        client_cls.return_value.__aenter__.return_value = client
        r = await run_card(BASE, KEY, 7, {"p1": "v"})
        assert r["data"]["rows"] == [[1]]
        args, kwargs = client.post.call_args
        assert args[0].endswith("/api/card/7/query")
        assert kwargs["json"] == {"parameters": {"p1": "v"}}


@pytest.mark.asyncio
async def test_error_raises_metabase_error():
    with patch("app.metabase_client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.return_value = httpx.Response(
            401, json={"error": "unauthorized"}, request=httpx.Request("GET", BASE)
        )
        client_cls.return_value.__aenter__.return_value = client
        with pytest.raises(MetabaseError) as ei:
            await health(BASE, KEY)
        assert ei.value.status_code == 401
        assert "unauthorized" in str(ei.value)
