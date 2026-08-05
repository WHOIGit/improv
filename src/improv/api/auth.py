"""Token authentication for the REST surface.

Scope-based, declared per endpoint (not verb-based). A route enforces auth by
depending on ``require_scope("read")`` / ``require_scope("write")``; endpoints
that omit it stay open.

The verifier is deliberately swappable. Today the only implementation is
``StaticTokenVerifier`` (one shared bearer token from ``IMPROV_API_TOKEN``).
When the service moves to per-client tokens, add a ``DbTokenVerifier`` with the
same ``verify`` interface and change the single construction site in
``create_app`` — routes, client, and tests are untouched.

``verify`` returns a ``Principal`` rather than a bool so that identity is
available from day one (for future audit logging and per-token scopes); the
static principal is trivial but the shape is the on-ramp.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Coarse scope set. The static token holds all of them; DB-backed tokens later
# hand out subsets per client.
READ = "read"
WRITE = "write"
ALL_SCOPES = frozenset({READ, WRITE})


@dataclass(frozen=True)
class Principal:
    """The authenticated identity behind a request.

    ``label`` is an opaque name for the caller ("service" for the shared static
    token; a per-client label once tokens are DB-backed). ``scopes`` is the set
    of scopes the token grants.
    """

    label: str
    scopes: frozenset[str] = field(default_factory=frozenset)


class TokenVerifier(Protocol):
    """Verifies a bearer token, returning the Principal or None if invalid."""

    def verify(self, token: str) -> Principal | None: ...


class StaticTokenVerifier:
    """Verifies against a single shared secret, in constant time.

    Grants all scopes on match — scope granularity only becomes meaningful with
    per-client (DB-backed) tokens.
    """

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("StaticTokenVerifier requires a non-empty token.")
        # Compared as bytes: secrets.compare_digest raises TypeError on str
        # inputs containing non-ASCII, and header values reach us as latin-1
        # decoded str, so a non-ASCII token would otherwise 500 instead of 401.
        self._token = token.encode("utf-8")

    def verify(self, token: str) -> Principal | None:
        if secrets.compare_digest(token.encode("utf-8"), self._token):
            return Principal(label="service", scopes=ALL_SCOPES)
        return None


# auto_error=False so a missing/malformed header yields None here and we raise a
# uniform 401 ourselves (rather than HTTPBearer's default 403).
_bearer = HTTPBearer(auto_error=False)


def require_scope(scope: str):
    """Build a dependency enforcing a bearer token that carries ``scope``.

    Missing/invalid token → 401; valid token lacking the scope → 403. Returns
    the ``Principal`` so handlers may accept it as a parameter when they need the
    caller's identity.
    """

    def dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> Principal:
        verifier: TokenVerifier | None = getattr(request.app.state, "verifier", None)
        if verifier is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication is not configured on this service instance.",
            )
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        principal = verifier.verify(credentials.credentials)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if scope not in principal.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token lacks required scope {scope!r}.",
            )
        return principal

    return dependency
