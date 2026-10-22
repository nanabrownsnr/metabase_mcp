"""Metabase REST API client.

Thin async wrapper over the Metabase HTTP API. Each call takes the user's
stored connection (``base_url`` + ``api_key``) and returns parsed JSON or
raises an actionable ``MetabaseError``.
"""

from typing import Any

import httpx


class MetabaseError(Exception):
    """Raised when a Metabase API call fails or returns an error payload."""

    def __init__(self, message: str, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key, "Accept": "application/json"}


def _check(data: Any, status_code: int) -> None:
    """Metabase returns errors as JSON with a 400/401/403/500 body."""
    if status_code >= 400:
        message = "error"
        if isinstance(data, dict):
            message = data.get("error") or data.get("message") or "request failed"
        elif isinstance(data, str) and data.strip():
            message = data.strip()
        raise MetabaseError(f"Metabase API error: {message}", status_code=status_code, detail=data)


async def _get(base_url: str, api_key: str, path: str, params: dict | None = None) -> Any:
    url = f"{_base_url(base_url)}/api{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers(api_key), params=params)
    data = _try_json(resp)
    _check(data, resp.status_code)
    return data


async def _post(base_url: str, api_key: str, path: str, json_body: dict | None = None) -> Any:
    url = f"{_base_url(base_url)}/api{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=_headers(api_key), json=json_body)
    data = _try_json(resp)
    _check(data, resp.status_code)
    return data


def _try_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except (ValueError, UnicodeDecodeError):
        return resp.text


async def health(base_url: str, api_key: str) -> dict:
    """Verify the API key is valid and the instance is reachable."""
    # /api/health requires no auth, so use an authenticated lightweight call.
    # /api/user/me is the canonical authenticated whoami endpoint.
    data = await _get(base_url, api_key, "/user/me")
    return data


async def search(base_url: str, api_key: str, term: str, models: list[str] | None = None) -> dict:
    """Search cards, dashboards, collections, etc. by term."""
    params: dict[str, Any] = {"term": term}
    if models:
        params["models"] = ",".join(models)
    return await _get(base_url, api_key, "/search", params=params)


async def list_databases(base_url: str, api_key: str) -> list[dict]:
    """List the databases connected to this Metabase instance."""
    data = await _get(base_url, api_key, "/database")
    return data.get("data", data) if isinstance(data, dict) else data


async def list_dashboards(
    base_url: str, api_key: str, collection_id: int | str | None = None
) -> list[dict]:
    """List dashboards, optionally filtered to a collection."""
    params: dict[str, Any] = {}
    if collection_id is not None:
        params["collection_id"] = collection_id
    data = await _get(base_url, api_key, "/dashboard", params=params or None)
    return data.get("data", data) if isinstance(data, dict) else data


async def get_dashboard(base_url: str, api_key: str, dashboard_id: int | str) -> dict:
    """Fetch a single dashboard (with its cards)."""
    return await _get(base_url, api_key, f"/dashboard/{dashboard_id}")


async def list_schemas(base_url: str, api_key: str, database_id: int | str) -> list[dict]:
    """List schemas for a database (Metabase groups tables under schemas)."""
    data = await _get(base_url, api_key, f"/database/{database_id}/metadata/tables")
    return data.get("data", data) if isinstance(data, dict) else data


async def list_tables(base_url: str, api_key: str, database_id: int | str) -> list[dict]:
    """List all tables (with schemas) for a database.

    Uses the same tables endpoint; returns the full list so the LLM can
    discover what's available before writing SQL.
    """
    return await list_schemas(base_url, api_key, database_id)


async def describe_table(base_url: str, api_key: str, table_id: int | str) -> dict:
    """Fetch a table's columns (name, type, description) and flags."""
    return await _get(base_url, api_key, f"/table/{table_id}")


async def run_sql(
    base_url: str,
    api_key: str,
    database_id: int | str,
    sql: str,
    max_rows: int = 5000,
) -> dict:
    """Run a native SQL query against a database via /api/dataset.

    Returns the raw Metabase dataset response (columns + rows). The caller is
    responsible for truncation/row-count reporting.
    """
    body: dict[str, Any] = {
        "database": database_id,
        "type": "native",
        "query": sql,
        "parameters": {},
    }
    return await _post(base_url, api_key, "/dataset", json_body=body)
