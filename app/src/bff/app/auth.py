"""Token validation and the On-Behalf-Of exchange.

The whole point of this module: Work IQ is a *delegated* data source. It returns
what the signed-in user can see. So the agent must be called with a token that
represents the user, not the app. That means:

    1. validate the access token the SPA sent us (signature, issuer, audience)
    2. exchange it, on behalf of that user, for a token scoped to Foundry
    3. call the agent with the exchanged token

If step 2 fails we surface the error rather than silently falling back to the
app identity, because a fallback would return an *empty but plausible* answer -
the worst possible failure for a demo, since nothing looks broken.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

from .config import settings

logger = logging.getLogger("auth")

_jwk_client: PyJWKClient | None = None
_obo_cache: dict[str, tuple[str, float]] = {}


class User:
    def __init__(self, claims: dict[str, Any], raw_token: str):
        self.claims = claims
        self.raw_token = raw_token
        self.oid: str = claims.get("oid", "")
        self.upn: str = (
            claims.get("preferred_username") or claims.get("upn") or claims.get("email") or ""
        )
        self.name: str = claims.get("name", self.upn)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.upn}>"


def _jwks() -> PyJWKClient:
    global _jwk_client
    _require_auth(require_secret=False)
    if _jwk_client is None:
        _jwk_client = PyJWKClient(settings.jwks_uri, cache_keys=True)
    return _jwk_client


def _require_auth(*, require_secret: bool = True) -> None:
    if settings.mock_mode:
        raise HTTPException(status_code=503, detail="Authentication is disabled in MOCK_MODE.")
    error = settings.auth_config_error(require_secret=require_secret)
    if error:
        raise HTTPException(status_code=500, detail=f"Auth is not configured: {error}")


def validate_token(raw: str) -> User:
    """Verify the SPA's access token against Entra's published signing keys."""
    _require_auth(require_secret=False)
    try:
        key = _jwks().get_signing_key_from_jwt(raw).key
        claims = jwt.decode(
            raw,
            key,
            algorithms=["RS256"],
            audience=list(settings.audiences),
            issuer=list(settings.issuers),
            options={"verify_exp": True},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("token validation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid token.") from None

    scopes = (claims.get("scp") or "").split()
    if "access_as_user" not in scopes:
        raise HTTPException(
            status_code=403,
            detail="Token is missing the access_as_user scope.",
        )
    return User(claims, raw)


async def current_user(request: Request) -> User:
    """FastAPI dependency. Mock mode bypasses auth for local UI work only."""
    if settings.mock_mode:
        return User(
            {"oid": "mock", "preferred_username": "demo.user@example.invalid",
             "name": "Demo User (mock)", "roles": ["Coverage"]},
            "",
        )
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return validate_token(header[7:])


async def exchange_obo(user: User, scope: str | None = None) -> str:
    """Swap the user's token for a downstream token, on behalf of that user.

    RFC 8693 token exchange, as implemented by the Microsoft identity platform.
    Cached per (user, scope) until shortly before expiry.
    """
    _require_auth()
    scope = settings.foundry_scope if scope is None else scope
    if not scope.strip():
        raise HTTPException(status_code=500, detail="Set FOUNDRY_SCOPE or a non-empty downstream scope.")
    if not user.raw_token.strip():
        raise HTTPException(status_code=401, detail="A user bearer token is required for On-Behalf-Of.")
    cache_key = f"{user.oid}:{scope}"
    hit = _obo_cache.get(cache_key)
    if hit and hit[1] > time.time() + 120:
        return hit[0]

    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "assertion": user.raw_token,
        "scope": scope,
        "requested_token_use": "on_behalf_of",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{settings.authority}/oauth2/v2.0/token", data=data)

    if resp.status_code != 200:
        body = resp.text[:600]
        logger.error("OBO exchange failed (%s)", resp.status_code)
        # AADSTS65001 = the user or admin has not consented to the downstream API.
        hint = ""
        if "65001" in body:
            hint = (" The user has not consented to the downstream API. Grant admin "
                    "consent for the BFF app registration, or sign in once "
                    "interactively to consent.")
        raise HTTPException(
            status_code=502,
            detail=f"On-Behalf-Of exchange failed (HTTP {resp.status_code}).{hint}",
        )

    payload = resp.json()
    token = payload["access_token"]
    _obo_cache[cache_key] = (token, time.time() + int(payload.get("expires_in", 3600)))
    logger.info("OBO exchange ok for %s -> %s", user.upn, scope)
    return token
