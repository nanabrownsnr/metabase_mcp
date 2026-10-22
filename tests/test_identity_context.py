"""Tests for get_identity_from_context (MCP-transport identity via access token).

This is the path tools use to resolve identity. The critical regression it
guards: FastMCP strips the `authorization` header from get_http_headers(), so
re-verifying from raw headers 401s on every tool call even though the transport
already verified the token. get_identity_from_context must read the verified
claims from the access token instead, and still pick up Persona-Id from headers.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from starlette.exceptions import HTTPException

from app.auth import TwynityIdentity, get_identity_from_context


def _fake_access_token(user_id="6a674b8d-user-1", sub=None):
    """Mimic FastMCP's AccessToken: verified claims + raw token."""
    claims = {"id": user_id, "sub": sub or user_id, "client_id": "twynity_public",
              "aud": ["metabase-mcp"]}
    return SimpleNamespace(token="verified-jwt", claims=claims,
                           client_id="twynity_public", scopes=None)


@pytest.mark.asyncio
async def test_identity_from_context_uses_verified_claims_not_headers():
    """The 401 bug: authorization is stripped from headers, but the access
    token is present in context, so identity MUST resolve from claims."""
    tok = _fake_access_token()
    # Simulate the real situation: headers have NO authorization (stripped),
    # but Persona-Id IS present.
    with patch("app.auth.get_access_token", return_value=tok), \
         patch("app.auth.get_http_headers", return_value={
             "persona-id": "persona-abc",
             # NOTE: no "authorization" key — it was stripped by FastMCP
         }):
        identity = await get_identity_from_context()
    assert identity == TwynityIdentity(user_id="6a674b8d-user-1", persona_id="persona-abc")


@pytest.mark.asyncio
async def test_identity_from_context_without_persona():
    """JWT alone (no Persona-Id) resolves user_id, persona_id is None."""
    tok = _fake_access_token(user_id="user-2")
    with patch("app.auth.get_access_token", return_value=tok), \
         patch("app.auth.get_http_headers", return_value={}):
        identity = await get_identity_from_context()
    assert identity == TwynityIdentity(user_id="user-2", persona_id=None)


@pytest.mark.asyncio
async def test_identity_from_context_falls_back_to_sub():
    """When no 'id' claim, 'sub' is used as user_id."""
    tok = _fake_access_token()
    tok.claims = {"sub": "sub-only-user", "aud": ["metabase-mcp"]}
    with patch("app.auth.get_access_token", return_value=tok), \
         patch("app.auth.get_http_headers", return_value={}):
        identity = await get_identity_from_context()
    assert identity.user_id == "sub-only-user"


@pytest.mark.asyncio
async def test_identity_from_context_401_when_no_token():
    """No access token in context -> 401 (the transport didn't authenticate)."""
    with patch("app.auth.get_access_token", return_value=None), \
         patch("app.auth.get_http_headers", return_value={}):
        with pytest.raises(HTTPException) as exc:
            await get_identity_from_context()
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_identity_from_context_401_when_no_user_claim():
    """Token present but no id/sub claim -> 401."""
    tok = SimpleNamespace(token="x", claims={"aud": ["metabase-mcp"]},
                          client_id="twynity_public", scopes=None)
    with patch("app.auth.get_access_token", return_value=tok), \
         patch("app.auth.get_http_headers", return_value={}):
        with pytest.raises(HTTPException) as exc:
            await get_identity_from_context()
    assert exc.value.status_code == 401
