"""Tenant resolution for HTTP endpoints (temporary, until DEV-1's D1-05 lands).

Once ``apex.auth.deps.current_principal()`` exists, every router depends on it and takes ``tenant_id`` from
the principal. Until then the tenant comes from the ``X-Tenant-Id`` header, which lets any caller act as any
tenant. That is only acceptable on a developer machine, so the header is honoured **only** when
``APEX_ALLOW_TENANT_HEADER=true``; otherwise every request is refused with 401 and the endpoints are closed.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Header, HTTPException, status

ALLOW_TENANT_HEADER_ENV = "APEX_ALLOW_TENANT_HEADER"


def tenant_header_enabled() -> bool:
    return os.environ.get(ALLOW_TENANT_HEADER_ENV, "").strip().lower() == "true"


def get_tenant_id(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
) -> str:
    if not tenant_header_enabled():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="tenant authentication is not wired yet (D1-05); these endpoints are closed",
        )
    if not x_tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing tenant")
    return x_tenant_id


__all__ = ["ALLOW_TENANT_HEADER_ENV", "get_tenant_id", "tenant_header_enabled"]
