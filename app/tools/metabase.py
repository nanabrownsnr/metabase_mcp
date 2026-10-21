"""Metabase MCP tools.

Core read-only tools over the Metabase API, scoped to the connecting user's
stored Metabase connection (base_url + api_key).

Every tool returns a ToolResult. A missing/misconfigured connection is returned
as an actionable error result (status=error), not raised, so the MCP client
always gets a structured answer.
"""

from typing import Any, Dict, List, Optional

from fastmcp.apps import AppConfig
from fastmcp.tools import ToolResult

from app.metabase_client import (
    MetabaseError,
    get_dashboard,
    health,
    list_databases,
    list_dashboards,
    run_card,
    search,
)
from app.tools.connection import get_current_connection

# Link tools to the Metabase UI resource when an MCP-Apps client is present.
VIEW_URI = "ui://metabase/index.html"


def _app_config() -> AppConfig:
    return AppConfig(resource_uri=VIEW_URI, visibility=["model", "app"])


def _meta() -> dict:
    return {"ui": {"resourceUri": VIEW_URI}, "ui/resourceUri": VIEW_URI}


async def _connection() -> dict | None:
    """Return decrypted ``{base_url, api_key}`` or None when unconfigured."""
    connection = await get_current_connection()
    if not connection:
        return None
    base_url = connection.get("base_url")
    api_key = connection.get("api_key")
    if not base_url or not api_key:
        return None
    return {"base_url": base_url, "api_key": api_key}


def _error_result(message: str, status_code: int | None = None) -> ToolResult:
    sc: Dict[str, Any] = {"status": "error", "error": message}
    if status_code is not None:
        sc["status_code"] = status_code
    return ToolResult(content=message, structured_content=sc, meta=_meta())


def register_tools(mcp):
    """Register the Metabase tools with the FastMCP server."""

    @mcp.tool(app=_app_config())
    async def check_metabase_connection() -> ToolResult:
        """Verify the configured Metabase connection is valid and reachable.

        Returns:
            A ToolResult with the authenticated user's profile if the API key works.

        Examples:
            ``check_metabase_connection()``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _error_result(
                    "No Metabase connection configured. Use /api/v1/configuration to set "
                    "your Metabase base URL and API key."
                )
            profile = await health(conn["base_url"], conn["api_key"])
            name = profile.get("first_name") or profile.get("email") or profile.get("id")
            return ToolResult(
                content=f"Metabase connection OK (authenticated as {name}).",
                structured_content={"status": "connected", "user": name},
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Metabase connection failed: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def metabase_search(term: str, models: Optional[List[str]] = None) -> ToolResult:
        """Search Metabase for cards, dashboards, collections, and more.

        Args:
            term: The search term to look for.
            models: Optional list of model types to search, e.g.
                ["card", "dashboard", "collection"]. Defaults to all.

        Returns:
            A ToolResult with matching Metabase entities and their IDs.

        Examples:
            ``metabase_search(term="revenue", models=["card", "dashboard"])``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _error_result(
                    "No Metabase connection configured. Use /api/v1/configuration to set "
                    "your Metabase base URL and API key."
                )
            result = await search(conn["base_url"], conn["api_key"], term, models)
            rows = result.get("results", result) if isinstance(result, dict) else result
            count = len(rows) if isinstance(rows, list) else "some"
            return ToolResult(
                content=f"Found {count} Metabase results for '{term}'.",
                structured_content={"status": "success", "term": term, "results": rows},
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Metabase search failed: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def list_databases_tool() -> ToolResult:
        """List the databases connected to this Metabase instance.

        Returns:
            A ToolResult with each database's id, name, and engine.

        Examples:
            ``list_databases_tool()``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _error_result(
                    "No Metabase connection configured. Use /api/v1/configuration to set "
                    "your Metabase base URL and API key."
                )
            dbs = await list_databases(conn["base_url"], conn["api_key"])
            summary = [
                {"id": d.get("id"), "name": d.get("name"), "engine": d.get("engine")}
                for d in dbs
            ]
            return ToolResult(
                content=f"Found {len(summary)} databases in Metabase.",
                structured_content={"status": "success", "databases": summary},
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to list databases: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def list_dashboards_tool(collection_id: Optional[int] = None) -> ToolResult:
        """List dashboards, optionally filtered to a single collection.

        Args:
            collection_id: Optional collection id to scope the list. Defaults
                to all dashboards the user can access.

        Returns:
            A ToolResult with each dashboard's id, name, and collection.

        Examples:
            ``list_dashboards_tool()`` or ``list_dashboards_tool(collection_id=2)``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _error_result(
                    "No Metabase connection configured. Use /api/v1/configuration to set "
                    "your Metabase base URL and API key."
                )
            dashboards = await list_dashboards(conn["base_url"], conn["api_key"], collection_id)
            summary = [
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "description": d.get("description"),
                    "collection_id": d.get("collection_id"),
                }
                for d in dashboards
            ]
            return ToolResult(
                content=f"Found {len(summary)} dashboards in Metabase.",
                structured_content={"status": "success", "dashboards": summary},
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to list dashboards: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def get_dashboard_tool(dashboard_id: int) -> ToolResult:
        """Fetch a single Metabase dashboard including its cards.

        Args:
            dashboard_id: The Metabase dashboard id to fetch.

        Returns:
            A ToolResult with the dashboard and its card list.

        Examples:
            ``get_dashboard_tool(dashboard_id=4)``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _error_result(
                    "No Metabase connection configured. Use /api/v1/configuration to set "
                    "your Metabase base URL and API key."
                )
            dashboard = await get_dashboard(conn["base_url"], conn["api_key"], dashboard_id)
            cards = dashboard.get("dashcards", [])
            card_ids = [c.get("card_id") for c in cards]
            return ToolResult(
                content=f"Dashboard '{dashboard.get('name')}' has {len(card_ids)} cards: {card_ids}.",
                structured_content={
                    "status": "success",
                    "dashboard": dashboard,
                    "card_ids": card_ids,
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to get dashboard {dashboard_id}: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def run_card_tool(card_id: int, parameters: Optional[Dict[str, Any]] = None) -> ToolResult:
        """Execute a saved Metabase question (card) and return its data.

        This runs the card's underlying query and returns the rows — the
        primary way for an LLM to answer data questions using vetted,
        saved Metabase logic.

        Args:
            card_id: The Metabase card (saved question) id to run.
            parameters: Optional map of Metabase parameter ids to values to
                apply to the card (e.g. date filters).

        Returns:
            A ToolResult with the query's columns and rows.

        Examples:
            ``run_card_tool(card_id=7)``
            ``run_card_tool(card_id=7, parameters={"card-7-date": "2026-10-01"})``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _error_result(
                    "No Metabase connection configured. Use /api/v1/configuration to set "
                    "your Metabase base URL and API key."
                )
            result = await run_card(conn["base_url"], conn["api_key"], card_id, parameters)
            data = result.get("data", result) if isinstance(result, dict) else result
            cols = [c.get("name") for c in data.get("cols", [])] if isinstance(data, dict) else []
            rows = data.get("rows", []) if isinstance(data, dict) else []
            return ToolResult(
                content=f"Ran card {card_id}: {len(rows)} rows, columns: {cols}.",
                structured_content={
                    "status": "success",
                    "card_id": card_id,
                    "columns": cols,
                    "rows": rows,
                    "data": data,
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to run card {card_id}: {e}", e.status_code)
