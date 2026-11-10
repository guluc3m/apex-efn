"""FastAPI dependencies for authentication and authorisation (D1-05, DEV-1).

Routers depend on :func:`current_principal`, or on :func:`get_tenant_id` / :func:`get_roles` from
``apex.common.tenant``, which delegate here. A router never reads a tenant or a role from a body or a
header: both come from a verified access token.

Local development keeps an explicit, opt-in escape hatch: with ``APEX_ALLOW_TENANT_HEADER=true`` and
**no** bearer token, the caller becomes a development principal whose tenant is the ``X-Tenant-Id``
header and whose roles come from ``APEX_DEV_ROLES``. A valid bearer token always wins over the header.
The hatch is off by default, and any public deployment must leave it off.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from apex.auth.errors import MALFORMED, MISSING_TOKEN, AuthError
from apex.auth.jwks import JwksProvider
from apex.auth.models import Principal
from apex.auth.settings import AuthSettings
from apex.auth.tokens import KNOWN_ROLES, SIGNING_ROLES, verify_access_token
from apex.common.errors import Problem

ALLOW_TENANT_HEADER_ENV = "APEX_ALLOW_TENANT_HEADER"
DEV_ROLES_ENV = "APEX_DEV_ROLES"

UNAUTHORIZED_TITLE = "Unauthorized"
FORBIDDEN_TITLE = "Forbidden"

RoleDependency = Callable[..., Awaitable[Principal]]
Clock = Callable[[], datetime]


def get_auth_clock() -> Clock:
    """Wall clock used for token time checks. Tests override this dependency to freeze time."""
    return lambda: datetime.now(UTC)


def tenant_header_enabled() -> bool:
    """Whether the development tenant header is allowed. Read per request so tests can toggle it."""
    return os.environ.get(ALLOW_TENANT_HEADER_ENV, "").strip().lower() == "true"


def _dev_roles() -> tuple[str, ...]:
    raw = os.environ.get(DEV_ROLES_ENV, "")
    requested = {part.strip() for part in raw.split(",") if part.strip()}
    return tuple(role for role in KNOWN_ROLES if role in requested)


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    """Authentication settings from the environment. Cached; tests override this dependency."""
    return AuthSettings.from_env()


@lru_cache(maxsize=8)
def _provider_for(settings: AuthSettings) -> JwksProvider:
    return JwksProvider(settings)


def get_jwks_provider(
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> JwksProvider:
    return _provider_for(settings)


def reset_auth_caches() -> None:
    """Drop the cached settings and key providers. Used by tests and after a configuration reload."""
    get_auth_settings.cache_clear()
    _provider_for.cache_clear()


def _unauthorized(reason: str, detail: str | None = None) -> Problem:
    return Problem(
        401,
        UNAUTHORIZED_TITLE,
        detail=detail or f"access token rejected: {reason}",
        headers={
            "WWW-Authenticate": (
                f'Bearer realm="apex", error="invalid_token", error_description="{reason}"'
            )
        },
    )


async def current_principal(
    request: Request,
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
    provider: Annotated[JwksProvider, Depends(get_jwks_provider)],
    clock: Annotated[Clock, Depends(get_auth_clock)],
) -> Principal:
    """The authenticated caller of this request, or a 401 problem."""
    if settings.auth_disabled:
        # Explicitly disabled must never mean "everyone is anonymous": that would be a silent opening.
        raise Problem(
            503,
            "Authentication unavailable",
            detail="APEX_AUTH_DISABLED is set; refusing to authenticate any caller",
        )

    authorization = request.headers.get("authorization")
    if authorization:
        scheme, _, raw_token = authorization.partition(" ")
        token = raw_token.strip()
        if scheme.lower() != "bearer" or not token:
            raise _unauthorized(MALFORMED, "expected 'Authorization: Bearer <token>'")
        try:
            verified = await verify_access_token(
                token, provider=provider, settings=settings, now=clock()
            )
        except AuthError as exc:
            raise _unauthorized(exc.reason, exc.detail) from exc
        return Principal(
            user_id=verified.user_id,
            tenant_id=verified.tenant_id,
            roles=verified.roles,
            auth_time=verified.auth_time,
        )

    if tenant_header_enabled():
        tenant_id = (request.headers.get("x-tenant-id") or "").strip()
        if not tenant_id:
            raise _unauthorized(MISSING_TOKEN, "missing X-Tenant-Id")
        return Principal(user_id="dev", tenant_id=tenant_id, roles=_dev_roles(), auth_time=None)

    raise _unauthorized(MISSING_TOKEN, "missing bearer token")


def require_role(*roles: str) -> RoleDependency:
    """Dependency factory: allow the request only if the principal holds one of ``roles``."""
    unknown = [role for role in roles if role not in KNOWN_ROLES]
    if unknown:
        raise ValueError(f"unknown role(s): {', '.join(unknown)}")
    allowed = tuple(dict.fromkeys(roles))
    if not allowed:
        raise ValueError("require_role needs at least one role")

    async def dependency(
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> Principal:
        if not principal.has_role(*allowed):
            raise Problem(
                403,
                FORBIDDEN_TITLE,
                detail=f"requires one of: {', '.join(allowed)}",
            )
        return principal

    return dependency


def require_signer() -> RoleDependency:
    """Dependency factory: only the roles that may sign decisions (``viewer`` never signs)."""
    return require_role(*SIGNING_ROLES)


__all__ = [
    "ALLOW_TENANT_HEADER_ENV",
    "DEV_ROLES_ENV",
    "current_principal",
    "get_auth_clock",
    "get_auth_settings",
    "get_jwks_provider",
    "require_role",
    "require_signer",
    "reset_auth_caches",
    "tenant_header_enabled",
]
