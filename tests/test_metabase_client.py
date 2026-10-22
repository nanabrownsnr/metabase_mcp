"""Tests for the Metabase REST API client (mocked httpx)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.metabase_client import (
    MetabaseError,
    add_dashboard_card,
    create_collection,
    create_dashboard,
    describe_table,
    get_dashboard,
    health,
    list_databases,
    list_dashboards,
    list_tables,
    preview_table,
    run_sql,
    save_question,
    search,
)

BASE = "https://metabase.test"
KEY = "sk-test"


def _ok(status=200, json_data=None, text=""):
    r = httpx.Response(status, request=httpx.Request("GET", BASE))
    if json_data is not None:
        import json as _json
        r._content = _json.dumps(json_data).encode()
        r.headers["content-type"] = "application/json"
    else:
        r._content = text.encode()
    return r


def _mock_client(response):
    client = AsyncMock()
    client.get.return_value = response
    client.post.return_value = response
    from unittest.mock import MagicMock
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return cls, client


@pytest.mark.asyncio
async def test_health_returns_profile():
    cls, client = _mock_client(_ok(200, {"id": 1, "first_name": "Ada", "email": "ada@x.com"}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        result = await health(BASE, KEY)
        assert result["first_name"] == "Ada"
        _, kwargs = client.get.call_args
        assert kwargs["headers"]["X-API-Key"] == KEY


@pytest.mark.asyncio
async def test_search_builds_query():
    cls, client = _mock_client(_ok(200, {"results": [{"id": 5, "model": "card"}]}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        result = await search(BASE, KEY, "revenue", ["card", "dashboard"])
        assert result["results"][0]["id"] == 5
        _, kwargs = client.get.call_args
        assert kwargs["params"]["term"] == "revenue"
        assert kwargs["params"]["models"] == "card,dashboard"


@pytest.mark.asyncio
async def test_list_databases_returns_list():
    cls, client = _mock_client(_ok(200, {"data": [{"id": 1, "name": "Sales", "engine": "postgres"}]}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        dbs = await list_databases(BASE, KEY)
        assert dbs[0]["name"] == "Sales"


@pytest.mark.asyncio
async def test_list_dashboards_scoped_by_collection():
    cls, client = _mock_client(_ok(200, {"data": [{"id": 9, "name": "KPI"}]}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        dash = await list_dashboards(BASE, KEY, collection_id=2)
        assert dash[0]["id"] == 9
        _, kwargs = client.get.call_args
        assert kwargs["params"]["collection_id"] == 2


@pytest.mark.asyncio
async def test_get_dashboard_url():
    cls, client = _mock_client(_ok(200, {"id": 9, "name": "KPI", "dashcards": [{"card_id": 7}]}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        d = await get_dashboard(BASE, KEY, 9)
        assert d["dashcards"][0]["card_id"] == 7
        args, _ = client.get.call_args
        assert args[0].endswith("/api/dashboard/9")


@pytest.mark.asyncio
async def test_list_tables_url_and_shape():
    cls, client = _mock_client(
        _ok(200, {"data": [{"id": 1, "name": "gl", "schema": "public", "row_count": 10}]})
    )
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        tables = await list_tables(BASE, KEY, 1)
        assert tables[0]["name"] == "gl"
        args, _ = client.get.call_args
        assert args[0].endswith("/api/database/1/metadata/tables")


@pytest.mark.asyncio
async def test_describe_table_url_and_shape():
    cls, client = _mock_client(
        _ok(200, {"id": 42, "name": "gl", "fields": [{"id": 1, "name": "account"}]})
    )
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        table = await describe_table(BASE, KEY, 42)
        assert table["fields"][0]["name"] == "account"
        args, _ = client.get.call_args
        assert args[0].endswith("/api/table/42")


@pytest.mark.asyncio
async def test_run_sql_posts_dataset():
    cls, client = _mock_client(
        _ok(200, {"data": {"columns": [{"name": "x"}], "rows": [[1]]}})
    )
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        r = await run_sql(BASE, KEY, 1, "SELECT 1", max_rows=10)
        assert r["data"]["rows"] == [[1]]
        args, kwargs = client.post.call_args
        assert args[0].endswith("/api/dataset")
        body = kwargs["json"]
        assert body["database"] == 1
        assert body["type"] == "native"
        # SQL must be nested under native.query (Metabase's /api/dataset shape)
        assert body["native"]["query"] == "SELECT 1"
        assert body["native"]["parameterized"] is False


@pytest.mark.asyncio
async def test_save_question_posts_card():
    cls, client = _mock_client(_ok(200, {"id": 42, "name": "Monthly Revenue"}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        card = await save_question(BASE, KEY, "Monthly Revenue", 1, "SELECT 1", display="bar")
        assert card["id"] == 42
        args, kwargs = client.post.call_args
        assert args[0].endswith("/api/card")
        body = kwargs["json"]
        assert body["name"] == "Monthly Revenue"
        assert body["display"] == "bar"
        assert body["database_id"] == 1
        # Native SQL nested under dataset_query.native
        assert body["dataset_query"]["type"] == "native"
        assert body["dataset_query"]["native"]["query"] == "SELECT 1"


@pytest.mark.asyncio
async def test_create_dashboard_posts_dashboard():
    cls, client = _mock_client(_ok(200, {"id": 7, "name": "Q3 Overview"}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        dash = await create_dashboard(BASE, KEY, "Q3 Overview", collection_id=5)
        assert dash["id"] == 7
        args, kwargs = client.post.call_args
        assert args[0].endswith("/api/dashboard")
        assert kwargs["json"]["name"] == "Q3 Overview"
        assert kwargs["json"]["collection_id"] == 5


@pytest.mark.asyncio
async def test_add_dashboard_card_posts_dashcard():
    cls, client = _mock_client(_ok(200, {"id": 99, "card_id": 42}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        placed = await add_dashboard_card(BASE, KEY, 7, 42, viz_type="bar", size=(6, 4))
        assert placed["card_id"] == 42
        args, kwargs = client.post.call_args
        assert args[0].endswith("/api/dashboard/7/card")
        body = kwargs["json"]
        assert body["card_id"] == 42
        assert body["visualization_type"] == "bar"
        assert body["size"] == [6, 4]


@pytest.mark.asyncio
async def test_create_collection_posts_collection():
    cls, client = _mock_client(_ok(200, {"id": 5, "name": "Finance"}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        col = await create_collection(BASE, KEY, "Finance")
        assert col["id"] == 5
        args, kwargs = client.post.call_args
        assert args[0].endswith("/api/collection")
        assert kwargs["json"]["name"] == "Finance"


@pytest.mark.asyncio
async def test_preview_table_posts_table_query():
    cls, client = _mock_client(
        _ok(200, {"data": {"columns": [{"name": "a"}], "rows": [[1], [2]]}})
    )
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        r = await preview_table(BASE, KEY, 42, max_rows=5)
        assert r["data"]["rows"] == [[1], [2]]
        args, _ = client.post.call_args
        assert args[0].endswith("/api/table/42/query")


@pytest.mark.asyncio
async def test_error_raises_metabase_error():
    cls, client = _mock_client(_ok(401, {"error": "unauthorized"}))
    with patch("app.metabase_client.httpx.AsyncClient", cls):
        with pytest.raises(MetabaseError) as ei:
            await health(BASE, KEY)
        assert ei.value.status_code == 401
        assert "unauthorized" in str(ei.value)
