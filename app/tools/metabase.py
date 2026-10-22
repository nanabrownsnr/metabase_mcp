"""Metabase MCP tools.

Read + query + create-analytics tools over the Metabase API, scoped to the
connecting user's stored Metabase connection (base_url + api_key).

Every tool returns a ToolResult. A missing/misconfigured connection is
returned as an actionable error result (status=error), not raised, so the MCP
client always gets a structured answer.

Tool set (12):
  Explore:
  - metabase_search     : search cards/dashboards/collections
  - list_databases_tool : list connected databases
  - list_dashboards_tool: list dashboards (optionally by collection)
  - get_dashboard_tool  : fetch a dashboard + its cards ("view dashboard")
  - list_tables_tool    : list schemas + tables for a database
  - describe_table_tool : columns + types for a table
  - preview_table_tool  : sample first N rows of a table
  Query:
  - run_sql             : run native SQL via /api/dataset (raw querying power)
  Create-analytics:
  - save_question_tool  : persist a SQL query as a saved question (card)
  - create_dashboard_tool : create a new dashboard
  - add_dashboard_card_tool : place a saved question on a dashboard
  - create_collection_tool  : create a folder (collection)
"""

from typing import Any, Dict, List, Optional

from fastmcp.apps import AppConfig
from fastmcp.tools import ToolResult

from app.metabase_client import (
    MetabaseError,
    add_dashboard_card,
    create_collection,
    create_dashboard as _create_dashboard_client,
    describe_table,
    get_dashboard,
    list_databases,
    list_dashboards,
    list_tables,
    preview_table,
    save_question,
    search,
)
from app.metabase_client import run_sql as _run_sql_client
from app.tools.connection import get_current_connection

# Link tools to the Metabase UI resource when an MCP-Apps client is present.
VIEW_URI = "ui://metabase/index.html"

# Default cap on rows returned by run_sql (CFO trial balances can be large, but
# unbounded results would blow up the model context). Override per-call.
DEFAULT_MAX_ROWS = 5000


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


def _no_connection_result() -> ToolResult:
    return _error_result(
        "No Metabase connection configured. Use /api/v1/configuration to set "
        "your Metabase base URL and API key."
    )


def register_tools(mcp):
    """Register the Metabase tools with the FastMCP server."""

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
                return _no_connection_result()
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
            A ToolResult with each database's id, name, and engine. The id is
            needed by list_tables_tool, describe_table_tool, and run_sql.

        Examples:
            ``list_databases_tool()``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _no_connection_result()
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
                return _no_connection_result()
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
                return _no_connection_result()
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
    async def list_tables_tool(database_id: int) -> ToolResult:
        """List the schemas and tables in a Metabase database.

        Use this to discover what tables exist (e.g. GL, journal entries,
        accounts) before writing SQL. Returns each table's id, schema, name,
        and row count.

        Args:
            database_id: The Metabase database id (from list_databases_tool).

        Returns:
            A ToolResult with the tables grouped by schema.

        Examples:
            ``list_tables_tool(database_id=1)``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _no_connection_result()
            tables = await list_tables(conn["base_url"], conn["api_key"], database_id)
            # Group by schema for readability.
            by_schema: Dict[str, List[Dict[str, Any]]] = {}
            for t in tables:
                schema = t.get("schema") or "public"
                entry = {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "display_name": t.get("display_name") or t.get("name"),
                    "row_count": t.get("row_count"),
                }
                by_schema.setdefault(schema, []).append(entry)
            flat = [
                {"schema": schema, **t} for schema, ts in by_schema.items() for t in ts
            ]
            return ToolResult(
                content=f"Found {len(flat)} tables across {len(by_schema)} schemas in database {database_id}.",
                structured_content={
                    "status": "success",
                    "database_id": database_id,
                    "tables_by_schema": by_schema,
                    "tables": flat,
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to list tables: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def describe_table_tool(table_id: int) -> ToolResult:
        """Describe a table's columns (name, type, description, flags).

        Call this before writing SQL against a table so the LLM uses correct
        column names and types.

        Args:
            table_id: The Metabase table id (from list_tables_tool).

        Returns:
            A ToolResult with the table's columns and metadata.

        Examples:
            ``describe_table_tool(table_id=42)``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _no_connection_result()
            table = await describe_table(conn["base_url"], conn["api_key"], table_id)
            fields = table.get("fields", [])
            columns = [
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "display_name": f.get("display_name") or f.get("name"),
                    "type": f.get("source_metadata", {}).get("type") or f.get("base_type"),
                    "description": f.get("description"),
                    "fiscal_type": f.get("fiscal_type"),
                    "nullable": f.get("nullable"),
                }
                for f in fields
            ]
            return ToolResult(
                content=f"Table '{table.get('display_name') or table.get('name')}' has {len(columns)} columns.",
                structured_content={
                    "status": "success",
                    "table_id": table_id,
                    "name": table.get("name"),
                    "display_name": table.get("display_name"),
                    "schema": table.get("schema"),
                    "database_id": table.get("dbid"),
                    "columns": columns,
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to describe table {table_id}: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def run_sql(
        database_id: int,
        sql: str,
        max_rows: int = DEFAULT_MAX_ROWS,
    ) -> ToolResult:
        """Run a native SQL query against a Metabase database.

        This is the primary raw-querying tool: write SQL, get the rows back.
        Ideal for financial analysis (trial balances, ledgers, P&L, balance
        sheets). The query runs under the connecting user's Metabase
        permissions.

        Args:
            database_id: The Metabase database id to query (from
                list_databases_tool).
            sql: The native SQL to run (SELECT recommended; the engine's
                native query language, e.g. PostgreSQL/MySQL/SQL Server).
            max_rows: Maximum rows to return (default 5000). Results beyond
                this are truncated and flagged.

        Returns:
            A ToolResult with the query's columns, rows, row count,
            truncation flag, and the SQL that ran (for audit).

        Examples:
            ``run_sql(database_id=1, sql="SELECT account, SUM(debit), SUM(credit) FROM gl_entries GROUP BY account")``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _no_connection_result()
            result = await _run_sql_client(
                conn["base_url"], conn["api_key"], database_id, sql, max_rows
            )
            data = result.get("data", result) if isinstance(result, dict) else result
            # Metabase /api/dataset returns {"data": {"columns": [...], "rows": [...]}}
            # (key is "columns", not "cols").
            cols_raw = data.get("columns", []) if isinstance(data, dict) else []
            rows = data.get("rows", []) if isinstance(data, dict) else []
            columns = [c.get("name") for c in cols_raw]
            truncated = len(rows) >= max_rows
            # Metabase also reports total size when available.
            total = data.get("row_count") if isinstance(data, dict) else None
            return ToolResult(
                content=(
                    f"Ran SQL on database {database_id}: {len(rows)} rows"
                    + (f" (truncated at {max_rows})" if truncated else "")
                    + f", columns: {columns}."
                ),
                structured_content={
                    "status": "success",
                    "database_id": database_id,
                    "sql": sql,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "total_row_count": total,
                    "truncated": truncated,
                    "max_rows": max_rows,
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"SQL query failed: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def preview_table_tool(table_id: int, max_rows: int = 10) -> ToolResult:
        """Sample the first N rows of a table to understand its data shape.

        Useful before writing SQL: see actual values, not just column names.

        Args:
            table_id: The Metabase table id (from list_tables_tool).
            max_rows: Maximum rows to return (default 10).

        Returns:
            A ToolResult with the table's columns and sample rows.

        Examples:
            ``preview_table_tool(table_id=42, max_rows=5)``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _no_connection_result()
            result = await preview_table(conn["base_url"], conn["api_key"], table_id, max_rows)
            data = result.get("data", result) if isinstance(result, dict) else result
            cols_raw = data.get("columns", []) if isinstance(data, dict) else []
            rows = data.get("rows", []) if isinstance(data, dict) else []
            rows = rows[:max_rows]
            columns = [c.get("name") for c in cols_raw]
            return ToolResult(
                content=f"Preview of table {table_id}: {len(rows)} sample rows, columns: {columns}.",
                structured_content={
                    "status": "success",
                    "table_id": table_id,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to preview table {table_id}: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def save_question_tool(
        name: str,
        database_id: int,
        sql: str,
        collection_id: Optional[int] = None,
        display: str = "table",
        description: Optional[str] = None,
    ) -> ToolResult:
        """Save a SQL query as a reusable saved question (card) in Metabase.

        This is the "I like this query, keep it" flow. The saved question can
        be added to a dashboard (add_dashboard_card_tool) or run later.
        Requires the connecting user's Metabase API key to have write
        permission on the database.

        Args:
            name: The question's title (shown in Metabase).
            database_id: The Metabase database id the SQL runs against.
            sql: The native SQL to save (SELECT recommended).
            collection_id: Optional folder id to save it in (default: personal).
            display: Visualization type: table, bar, line, pie, scatter, area,
                gauge, row, combo, pivot, scalar, smartscalar, progress, funnel,
                map, waterfall, sankey. Default "table".
            description: Optional one-line description of what the question
                answers.

        Returns:
            A ToolResult with the saved question's id and name (use the id with
            add_dashboard_card_tool).

        Examples:
            ``save_question_tool(name="Monthly Revenue", database_id=1, sql="SELECT month, SUM(amount) FROM sales GROUP BY month", display="bar")``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _no_connection_result()
            card = await save_question(
                conn["base_url"], conn["api_key"],
                name=name, database_id=database_id, sql=sql,
                collection_id=collection_id, display=display,
                description=description,
            )
            return ToolResult(
                content=f"Saved question '{name}' (id={card.get('id')}, display={display}).",
                structured_content={
                    "status": "success",
                    "card_id": card.get("id"),
                    "name": name,
                    "display": display,
                    "database_id": database_id,
                    "collection_id": collection_id,
                    "url": card.get("url"),
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to save question: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def create_dashboard_tool(
        name: str,
        collection_id: Optional[int] = None,
        description: Optional[str] = None,
    ) -> ToolResult:
        """Create a new (empty) dashboard in Metabase.

        Follow up with add_dashboard_card_tool to place saved questions on it.
        Requires the connecting user's Metabase API key to have write
        permission.

        Args:
            name: The dashboard's title.
            collection_id: Optional folder id to create it in (default: personal).
            description: Optional description.

        Returns:
            A ToolResult with the new dashboard's id and name (use the id with
            add_dashboard_card_tool).

        Examples:
            ``create_dashboard_tool(name="Q3 Finance Overview", collection_id=5)``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _no_connection_result()
            dash = await _create_dashboard_client(
                conn["base_url"], conn["api_key"],
                name=name, collection_id=collection_id, description=description,
            )
            return ToolResult(
                content=f"Created dashboard '{name}' (id={dash.get('id')}).",
                structured_content={
                    "status": "success",
                    "dashboard_id": dash.get("id"),
                    "name": name,
                    "collection_id": collection_id,
                    "url": dash.get("url"),
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to create dashboard: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def add_dashboard_card_tool(
        dashboard_id: int,
        card_id: int,
        viz_type: str = "table",
        col_span: int = 6,
        row_span: int = 4,
    ) -> ToolResult:
        """Place a saved question onto a dashboard as a chart.

        Args:
            dashboard_id: The dashboard id (from create_dashboard_tool or
                list_dashboards_tool).
            card_id: The saved question id (from save_question_tool or
                metabase_search).
            viz_type: Visualization type: table, bar, line, pie, scatter, area,
                gauge, row, combo, pivot, scalar, smartscalar, progress, funnel,
                map, waterfall, sankey. Default "table".
            col_span: Width in grid units (dashboard is 12 units wide).
                Default 6 (half width).
            row_span: Height in grid units. Default 4.

        Returns:
            A ToolResult with the placed card's id and position.

        Examples:
            ``add_dashboard_card_tool(dashboard_id=7, card_id=42, viz_type="bar", col_span=6, row_span=4)``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _no_connection_result()
            placed = await add_dashboard_card(
                conn["base_url"], conn["api_key"],
                dashboard_id=dashboard_id, card_id=card_id,
                viz_type=viz_type, size=(col_span, row_span),
            )
            return ToolResult(
                content=f"Added card {card_id} to dashboard {dashboard_id} as {viz_type} ({col_span}x{row_span}).",
                structured_content={
                    "status": "success",
                    "dashboard_id": dashboard_id,
                    "card_id": card_id,
                    "dashboard_card_id": placed.get("id") if isinstance(placed, dict) else None,
                    "viz_type": viz_type,
                    "size": [col_span, row_span],
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to add card to dashboard: {e}", e.status_code)

    @mcp.tool(app=_app_config())
    async def create_collection_tool(
        name: str,
        parent_id: Optional[int] = None,
    ) -> ToolResult:
        """Create a new collection (folder) in Metabase to organize content.

        Use it to group related questions and dashboards.

        Args:
            name: The folder's name.
            parent_id: Optional parent folder id to nest it under (default: top-level).

        Returns:
            A ToolResult with the new collection's id (use it as collection_id
            in save_question_tool / create_dashboard_tool).

        Examples:
            ``create_collection_tool(name="Finance")``
        """
        try:
            conn = await _connection()
            if conn is None:
                return _no_connection_result()
            col = await create_collection(
                conn["base_url"], conn["api_key"],
                name=name, parent_id=parent_id,
            )
            return ToolResult(
                content=f"Created collection '{name}' (id={col.get('id')}).",
                structured_content={
                    "status": "success",
                    "collection_id": col.get("id"),
                    "name": name,
                    "parent_id": parent_id,
                },
                meta=_meta(),
            )
        except MetabaseError as e:
            return _error_result(f"Failed to create collection: {e}", e.status_code)
