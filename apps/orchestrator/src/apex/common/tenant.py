"""Tenant and role resolution for HTTP endpoints.

The tenant and the roles of a caller come from the authenticated principal (D1-05, DEV-1):
``apex.auth.deps.current_principal``. Routers keep depending on ``get_tenant_id`` and ``get_roles`` so
nothing had to be rewired when authentication landed.

Local development keeps an opt-in escape hatch: with ``APEX_ALLOW_TENANT_HEADER=true`` and no bearer
token, the caller is a development principal whose tenant is ``X-Tenant-Id`` and whose roles come from
``APEX_DEV_ROLES``. A valid bearer token always wins over the header. The hatch is off by default and
must stay off outside a developer machine.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from apex.auth.deps import (
    ALLOW_TENANT_HEADER_ENV,
    current_principal,
    tenant_header_enabled,
)
from apex.auth.models import Principal

__all__ = [
    "ALLOW_TENANT_HEADER_ENV",
    "get_roles",
    "get_tenant_id",
    "tenant_header_enabled",
]


async def get_tenant_id(
    principal: Annotated[Principal, Depends(current_principal)],
) -> str:
    return principal.tenant_id


async def get_roles(
    principal: Annotated[Principal, Depends(current_principal)],
) -> tuple[str, ...]:
    """Roles of the caller. Never read from a request body or a client-supplied role header."""
    return principal.roles
