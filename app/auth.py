"""JWT and Twynity persona identity helpers.

FastMCP's JWTVerifier protects MCP transport requests. Starlette custom routes
are separate, so they explicitly verify the bearer token against account-service
JWKS here before trusting identity claims.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import httpx
from fastmcp.server.auth.providers.jwt import JWTVerifier
from jose import JWTError, jwt
from starlette.exceptions import HTTPException
from starlette.requests import Request

from app.config import settings


@dataclass(frozen=True)
class TwynityIdentity:
    user_id: str
    persona_id: str | None


def get_auth_provider() -> JWTVerifier:
    """Build FastMCP's bearer-token verifier for the MCP transport."""
    jwks_url = (
        f"{settings.ACCOUNT_SERVICE_URL.rstrip('/')}"
        f"/{settings.ACCOUNT_SERVICE_JWKS_ENDPOINT.lstrip('/')}"
    )
    return JWTVerifier(jwks_uri=jwks_url, algorithm="RS256")


async def get_identity(request: Request) -> TwynityIdentity:
    """Verify a request JWT and resolve its trusted user ID.

    ``persona_id`` is optional here — it is only needed when scoping a stored
    connection. Tool calls work with a valid JWT alone; the configuration
    (connect) routes use :func:`get_identity_require_persona` instead.
    """
    return await get_identity_from_headers(request.headers)


async def get_identity_require_persona(request: Request) -> TwynityIdentity:
    """Like :func:`get_identity` but fail closed without a ``Persona-Id``.

    Used by the /api/v1/configuration routes: saving or reading a stored
    Metabase connection requires a persona to scope it.
    """
    identity = await get_identity_from_headers(request.headers)
    if not identity.persona_id:
        raise HTTPException(
            status_code=400,
            detail=f"Connecting a Metabase requires the '{settings.PERSONA_ID_HEADER}' header",
        )
    return identity


async def get_identity_from_headers(headers: Mapping[str, str]) -> TwynityIdentity:
    """Resolve trusted identity from HTTP/MCP headers.

    A valid Twynity bearer token is always required (401 without it).
    ``Persona-Id`` is optional: when absent, ``persona_id`` is ``None`` so
    callers can degrade to "no scoped connection" instead of a hard error.
    """
    authorization = headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    persona_id = headers.get(settings.PERSONA_ID_HEADER.lower())
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="A valid Twynity bearer token is required")

    jwks_url = (
        f"{settings.ACCOUNT_SERVICE_URL.rstrip('/')}"
        f"/{settings.ACCOUNT_SERVICE_JWKS_ENDPOINT.lstrip('/')}"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
        header = jwt.get_unverified_header(token)
        key = next(key for key in response.json()["keys"] if key.get("kid") == header.get("kid"))
        # No audience check: Twynity signs user JWTs for the platform, not per
        # service. The transport JWTVerifier (get_auth_provider) also omits
        # audience, so custom routes must match or they 401 on valid tokens.
        claims = jwt.decode(
            token, key, algorithms=["RS256"]
        )
    except (httpx.HTTPError, KeyError, StopIteration, JWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Twynity bearer token could not be verified") from exc

    user_id = claims.get("id") or claims.get("sub")
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(status_code=401, detail="Verified token has no user identity claim")
    persona_id = persona_id.strip() if isinstance(persona_id, str) and persona_id.strip() else None
    return TwynityIdentity(user_id=user_id, persona_id=persona_id)
