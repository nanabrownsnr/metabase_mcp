"""Tests for the Metabase tools: ToolResult contract + no-connection error path."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from fastmcp import FastMCP

from app.tools import metabase as tools_mod


def _make_mcp() -> FastMCP:
    mcp = FastMCP("test-metabase")
    tools_mod.register_tools(mcp)
    return mcp


@pytest.mark.asyncio
async def test_no_connection_returns_actionable_error():
    mcp = _make_mcp()
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=None)):
        result = await mcp.call_tool("check_metabase_connection", {})
    sc = result.structured_content
    assert sc["status"] == "error"
    assert "No Metabase connection" in sc["error"] or "No Metabase connection" in (result.content or "")


@pytest.mark.asyncio
async def test_missing_fields_returns_error():
    mcp = _make_mcp()
    # api_key empty → treated as unconfigured → actionable error, not a crash.
    conn = {"base_url": "https://mb.test", "api_key": ""}
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=conn)):
        result = await mcp.call_tool("check_metabase_connection", {})
    sc = result.structured_content
    assert sc["status"] == "error"
    assert "connection" in sc["error"].lower()


@pytest.mark.asyncio
async def test_run_card_success_shape():
    mcp = _make_mcp()
    conn = {"base_url": "https://mb.test", "api_key": "sk-1"}
    fake_data = {"data": {"cols": [{"name": "revenue"}], "rows": [[100], [200]]}}
    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=conn)), \
         patch.object(tools_mod, "run_card", new=AsyncMock(return_value=fake_data)):
        result = await mcp.call_tool("run_card_tool", {"card_id": 7})
    sc = result.structured_content
    assert sc["status"] == "success"
    assert sc["card_id"] == 7
    assert sc["columns"] == ["revenue"]
    assert sc["rows"] == [[100], [200]]


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
async def test_tool_metabase_error_shape():
    mcp = _make_mcp()
    conn = {"base_url": "https://mb.test", "api_key": "sk-1"}
    from app.metabase_client import MetabaseError

    with patch.object(tools_mod, "get_current_connection", new=AsyncMock(return_value=conn)), \
         patch.object(
             tools_mod, "list_dashboards",
             new=AsyncMock(side_effect=MetabaseError("boom", status_code=500)),
         ):
        result = await mcp.call_tool("list_dashboards_tool", {})
    sc = result.structured_content
    assert sc["status"] == "error"
    assert "boom" in sc["error"]
