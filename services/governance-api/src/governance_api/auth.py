"""Entra ID JWT authentication for the Governance API.

Implements TC-1 / TC-9 (caller and approver identity capture). The bearer
token is normally supplied by APIM (which forwards the original Authorization
header from the calling user / service). This module validates the token
against Microsoft Entra ID JWKS and exposes a `CallerIdentity` via a FastAPI
dependency so routers can attach identity to incidents, approvals, and audit
events.

Modes (env: ``AUTH_MODE``):
  - ``required``: Authorization header must be present and the token valid.
  - ``optional`` (default): if a token is present it is validated; if absent
    a synthetic local-dev identity is returned. Suitable for the PoC where
    APIM-fronted traffic carries tokens but unauthenticated probes / smoke
    tests still need to function.
  - ``disabled``: no validation; always returns the local-dev identity.
    Used by the unit tests so they do not need a live Entra tenant.

Configuration:
  - ``ENTRA_TENANT_ID``: tenant the token must be issued by.
  - ``ENTRA_AUDIENCE`` (or comma-separated ``ENTRA_ALLOWED_AUDIENCES``):
    accepted audience values.
  - ``ENTRA_ALLOWED_ISSUERS``: optional override; defaults to the v1 and v2
    issuer URLs for the configured tenant.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger("uc3.auth")

DEV_IDENTITY_OID = "00000000-0000-0000-0000-000000000000"
DEV_IDENTITY_UPN = "local-dev@uaip.local"
DEV_IDENTITY_NAME = "Local Dev User"

_JWKS_CACHE_TTL_SECONDS = 3600
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class CallerIdentity(BaseModel):
    """Validated caller identity extracted from an Entra ID JWT (or a dev stub)."""

    oid: str = Field(..., description="Entra object ID (stable per-user identifier).")
    upn: str = Field(..., description="User principal name / preferred username.")
    name: str | None = Field(None, description="Display name from the token.")
    tenant_id: str | None = Field(None, description="Issuing tenant ID.")
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    auth_mode: str = Field(..., description="entra | dev")
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def audit_dict(self) -> dict[str, Any]:
        """Compact dict suitable for embedding in workflow audit events."""
        return {
            "oid": self.oid,
            "upn": self.upn,
            "name": self.name,
            "tenant_id": self.tenant_id,
            "auth_mode": self.auth_mode,
            "captured_at": self.captured_at.isoformat(),
        }


def _dev_identity() -> CallerIdentity:
    return CallerIdentity(
        oid=DEV_IDENTITY_OID,
        upn=DEV_IDENTITY_UPN,
        name=DEV_IDENTITY_NAME,
        tenant_id=None,
        roles=[],
        scopes=[],
        auth_mode="dev",
    )


def _auth_mode() -> str:
    mode = os.environ.get("AUTH_MODE", "optional").strip().lower()
    if mode not in ("required", "optional", "disabled"):
        logger.warning("Unknown AUTH_MODE=%s, defaulting to 'optional'", mode)
        return "optional"
    return mode


def _allowed_audiences() -> list[str]:
    multi = os.environ.get("ENTRA_ALLOWED_AUDIENCES", "")
    if multi:
        return [a.strip() for a in multi.split(",") if a.strip()]
    single = os.environ.get("ENTRA_AUDIENCE", "")
    return [single] if single else []


def _allowed_issuers(tenant_id: str) -> list[str]:
    override = os.environ.get("ENTRA_ALLOWED_ISSUERS", "")
    if override:
        return [i.strip() for i in override.split(",") if i.strip()]
    return [
        f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        f"https://sts.windows.net/{tenant_id}/",
    ]


def _fetch_jwks(tenant_id: str) -> dict[str, Any]:
    now = time.time()
    cached = _jwks_cache.get(tenant_id)
    if cached and (now - cached[0]) < _JWKS_CACHE_TTL_SECONDS:
        return cached[1]

    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    jwks = resp.json()
    _jwks_cache[tenant_id] = (now, jwks)
    return jwks


def _decode_token(token: str) -> CallerIdentity:
    """Validate an Entra ID JWT and return the caller identity."""
    try:
        import jwt
        from jwt import PyJWKClient  # noqa: F401  (ensures cryptography extra installed)
        from jwt.algorithms import RSAAlgorithm
    except ImportError as e:  # pragma: no cover - dependency guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"JWT library unavailable: {e}",
        ) from e

    tenant_id = os.environ.get("ENTRA_TENANT_ID", "").strip()
    audiences = _allowed_audiences()
    if not tenant_id or not audiences:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth misconfigured: ENTRA_TENANT_ID and ENTRA_AUDIENCE required.",
        )

    try:
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Token missing 'kid' header.")

        jwks = _fetch_jwks(tenant_id)
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key_data is None:
            # Cache may be stale — refresh once.
            _jwks_cache.pop(tenant_id, None)
            jwks = _fetch_jwks(tenant_id)
            key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key_data is None:
            raise HTTPException(status_code=401, detail="Signing key not found in JWKS.")

        public_key = RSAAlgorithm.from_jwk(key_data)
        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            audience=audiences,
            issuer=_allowed_issuers(tenant_id),
            options={"require": ["exp", "iss", "aud"]},
        )
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Token expired.") from e
    except jwt.InvalidAudienceError as e:
        raise HTTPException(status_code=401, detail="Invalid audience.") from e
    except jwt.InvalidIssuerError as e:
        raise HTTPException(status_code=401, detail="Invalid issuer.") from e
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"JWKS fetch failed: {e}") from e

    upn = (
        claims.get("upn")
        or claims.get("preferred_username")
        or claims.get("unique_name")
        or claims.get("email")
        or claims.get("sub", "")
    )
    oid = claims.get("oid") or claims.get("sub", "")
    if not oid:
        raise HTTPException(status_code=401, detail="Token missing 'oid'/'sub' claim.")

    roles_claim = claims.get("roles", [])
    if isinstance(roles_claim, str):
        roles_claim = [roles_claim]
    scope_claim = claims.get("scp", "")
    scopes = scope_claim.split() if isinstance(scope_claim, str) and scope_claim else []

    return CallerIdentity(
        oid=oid,
        upn=upn,
        name=claims.get("name"),
        tenant_id=claims.get("tid") or tenant_id,
        roles=list(roles_claim),
        scopes=scopes,
        auth_mode="entra",
    )


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def get_caller_identity(
    authorization: str | None = Header(default=None),
) -> CallerIdentity:
    """FastAPI dependency that resolves the caller identity for the request."""
    mode = _auth_mode()
    if mode == "disabled":
        return _dev_identity()

    token = _extract_bearer(authorization)
    if token is None:
        if mode == "required":
            raise HTTPException(
                status_code=401,
                detail="Authorization bearer token required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _dev_identity()

    return _decode_token(token)


# Convenience type for routers
CallerDep = Depends(get_caller_identity)
