"""FastAPI dependencies for the config router.

TODO(DEV-1 / D1-05): replace ``get_tenant_id`` with ``apex.auth.deps.current_principal`` and use
``principal.tenant_id``.

Until then the tenant would come from the ``X-Tenant-Id`` header, which lets any caller read or change any
tenant's configuration. That is only acceptable on a developer machine, so the header is honoured **only**
when ``APEX_ALLOW_TENANT_HEADER`` is set to ``true``. Without it every request is refused (401) and the router
is effectively closed. Never set it in a shared or production environment (ADR-900 review of #107).
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
            detail="tenant authentication is not wired yet (D1-05); config endpoints are closed",
        )
    if not x_tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing tenant")
    return x_tenant_id
