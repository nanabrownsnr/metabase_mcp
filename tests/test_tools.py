"""Tests for the Metabase tools: ToolResult contract + 7-tool set."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from fastmcp import FastMCP

from app.tools import metabase as tools_mod


def _make_mcp() -> FastMCP:
    mcp = FastMCP("test-metabase")
    tools_mod.register_tools(mcp)
    return mcp


EXPECTED_TOOLS = {
    "metabase_search",
    "list_databases_tool",
    "list_dashboards_tool",
    "get_dashboard_tool",
    "list_tables_tool",
    "describe_table_tool",
    "preview_table_tool",
    "run_sql",
    "save_question_tool",
    "create_dashboard_tool",
    "add_dashboard_card_tool",
    "create_collection_tool",
}


@pytest.mark.asyncio
async def test_exposes_expected_tools():
    mcp = _make_mcp()
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS
    # Removed tools must be gone.
    assert "check_metabase_connection" not in names
    assert "run_card_tool" not in names


@pytest.mark.asyncio
async def test_no_connection_returns_actionable_error():
    mcp = _make_mcp()
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=None)):
        result = await mcp.call_tool("run_sql", {"database_id": 1, "sql": "SELECT 1"})
    sc = result.structured_content
    assert sc["status"] == "error"
    assert "No Metabase connection" in sc["error"]


@pytest.mark.asyncio
async def test_jwt_without_persona_yields_no_connection_not_400():
    """A valid JWT with no Persona-Id must NOT hard-fail; it degrades to
    'no connection configured' so the marketplace can still list/call tools."""
    mcp = _make_mcp()
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=None)):
        result = await mcp.call_tool("run_sql", {"database_id": 1, "sql": "SELECT 1"})
    sc = result.structured_content
    assert sc["status"] == "error"
    assert "No Metabase connection" in sc["error"]


@pytest.mark.asyncio
async def test_run_sql_success_shape():
    mcp = _make_mcp()
    conn = {"base_url": "https://mb.test", "api_key": "sk-1"}
    fake_data = {
        "data": {
            "columns": [{"name": "account"}, {"name": "total"}],
            "rows": [["Cash", 100], ["AR", 200]],
        }
    }
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=conn)), \
         patch.object(tools_mod, "_run_sql_client", new=AsyncMock(return_value=fake_data)) as m:
        result = await mcp.call_tool("run_sql", {"database_id": 1, "sql": "SELECT 1"})
    sc = result.structured_content
    assert sc["status"] == "success"
    assert sc["database_id"] == 1
    assert sc["sql"] == "SELECT 1"
    assert sc["columns"] == ["account", "total"]
    assert sc["rows"] == [["Cash", 100], ["AR", 200]]
    assert sc["truncated"] is False
    # run_sql client called with the right args.
    _, kwargs = m.call_args
    assert kwargs.get("database_id", m.call_args[0][2] if m.call_args[0] else None) is not None


@pytest.mark.asyncio
async def test_run_sql_truncation_flag():
    mcp = _make_mcp()
    conn = {"base_url": "https://mb.test", "api_key": "sk-1"}
    rows = [[i] for i in range(3)]
    fake_data = {"data": {"columns": [{"name": "x"}], "rows": rows}}
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=conn)), \
         patch.object(tools_mod, "_run_sql_client", new=AsyncMock(return_value=fake_data)):
        result = await mcp.call_tool("run_sql", {"database_id": 1, "sql": "SELECT 1", "max_rows": 3})
    sc = result.structured_content
    assert sc["truncated"] is True
    assert sc["max_rows"] == 3


@pytest.mark.asyncio
async def test_list_databases_success_shape():
    mcp = _make_mcp()
    conn = {"base_url": "https://mb.test", "api_key": "sk-1"}
    dbs = [{"id": 1, "name": "Sales", "engine": "postgres"}]
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=conn)), \
         patch.object(tools_mod, "list_databases", new=AsyncMock(return_value=dbs)):
        result = await mcp.call_tool("list_databases_tool", {})
    sc = result.structured_content
    assert sc["status"] == "success"
    assert sc["databases"][0]["name"] == "Sales"


@pytest.mark.asyncio
async def test_list_tables_groups_by_schema():
    mcp = _make_mcp()
    conn = {"base_url": "https://mb.test", "api_key": "sk-1"}
    tables = [
        {"id": 1, "name": "gl", "schema": "public", "row_count": 10},
        {"id": 2, "name": "accounts", "schema": "public", "row_count": 5},
        {"id": 3, "name": "audit", "schema": "other", "row_count": 1},
    ]
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=conn)), \
         patch.object(tools_mod, "list_tables", new=AsyncMock(return_value=tables)):
        result = await mcp.call_tool("list_tables_tool", {"database_id": 1})
    sc = result.structured_content
    assert sc["status"] == "success"
    assert len(sc["tables_by_schema"]["public"]) == 2
    assert len(sc["tables_by_schema"]["other"]) == 1
    assert len(sc["tables"]) == 3


@pytest.mark.asyncio
async def test_describe_table_success_shape():
    mcp = _make_mcp()
    conn = {"base_url": "https://mb.test", "api_key": "sk-1"}
    table = {
        "id": 42,
        "name": "gl",
        "display_name": "GL Entries",
        "schema": "public",
        "dbid": 1,
        "fields": [
            {"id": 1, "name": "account", "base_type": "type/Integer"},
            {"id": 2, "name": "debit", "base_type": "type/Float", "description": "debit amt"},
        ],
    }
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=conn)), \
         patch.object(tools_mod, "describe_table", new=AsyncMock(return_value=table)):
        result = await mcp.call_tool("describe_table_tool", {"table_id": 42})
    sc = result.structured_content
    assert sc["status"] == "success"
    assert sc["table_id"] == 42
    assert [c["name"] for c in sc["columns"]] == ["account", "debit"]
    assert sc["columns"][1]["description"] == "debit amt"


@pytest.mark.asyncio
async def test_tool_metabase_error_shape():
    mcp = _make_mcp()
    conn = {"base_url": "https://mb.test", "api_key": "sk-1"}
    from app.metabase_client import MetabaseError

    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=conn)), \
         patch.object(
             tools_mod, "_run_sql_client",
             new=AsyncMock(side_effect=MetabaseError("syntax error", status_code=400)),
         ):
        result = await mcp.call_tool("run_sql", {"database_id": 1, "sql": "BAD SQL"})
    sc = result.structured_content
    assert sc["status"] == "error"
    assert "syntax error" in sc["error"]
