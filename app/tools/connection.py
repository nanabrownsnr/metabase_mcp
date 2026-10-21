"""Helpers for tools that need the active user's stored Metabase credentials."""

from fastmcp.server.dependencies import get_http_headers
from starlette.exceptions import HTTPException

from app.auth import get_identity_from_headers
from app.connection_store import get_active_store


async def get_current_connection() -> dict | None:
    """Return decrypted credentials for the verified user's scoped connection.

    A valid Twynity JWT is always required. The ``Persona-Id`` header scopes
    *which* stored connection to load: when it is present the connection for
    that exact (user_id, persona_id) pair is returned; when it is absent there
    is no scoped connection and ``None`` is returned so the tool can report
    "no connection configured" instead of erroring.

    Never accept user_id/persona_id as tool arguments: the MCP host supplies
    the verified bearer token (and Persona-Id, when scoping a connection).
    """
    identity = await get_identity_from_headers(get_http_headers())
    store = get_active_store()
    if store is None:
        raise HTTPException(status_code=503, detail="Connection storage is not available")
    if not identity.persona_id:
        # No persona → no scoped connection to load.
        return None
    return await store.get(identity.user_id, identity.persona_id)
