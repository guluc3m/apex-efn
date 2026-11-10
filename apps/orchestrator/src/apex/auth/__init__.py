"""Authentication and RBAC owned by DEV-1.

This package validates Keycloak access tokens and exposes the caller as a :class:`Principal`:

- :func:`apex.auth.deps.current_principal` — FastAPI dependency, 401 problem on failure.
- :func:`apex.auth.deps.require_role` / :func:`apex.auth.deps.require_signer` — 403 problem unless the
  caller holds one of the roles. ``viewer`` never signs.
- :func:`apex.auth.tokens.verify_access_token` — RS256-pinned verification against JWKS, with the
  injected clock and the closed reason set of :mod:`apex.auth.errors`.

The token is never logged or echoed. Settings come from ``APEX_AUTH_*`` variables and are documented in
``docs/security/rbac.md`` and ``docs/adr/101-orchestrator-jwt-validation.md``.
"""

from apex.auth.deps import (
    current_principal,
    get_auth_clock,
    get_auth_settings,
    get_jwks_provider,
    require_role,
    require_signer,
)
from apex.auth.errors import AUTH_REASONS, AuthError
from apex.auth.models import KNOWN_ROLES, Principal
from apex.auth.tokens import SIGNING_ROLES, VerifiedToken, verify_access_token

__all__ = [
    "AUTH_REASONS",
    "AuthError",
    "KNOWN_ROLES",
    "Principal",
    "SIGNING_ROLES",
    "VerifiedToken",
    "current_principal",
    "get_auth_clock",
    "get_auth_settings",
    "get_jwks_provider",
    "require_role",
    "require_signer",
    "verify_access_token",
]
