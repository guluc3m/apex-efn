"""FastAPI dependencies for the config router.

TODO(DEV-1 / D1-05): replace ``get_tenant_id`` with ``apex.auth.deps.current_principal`` and use
``principal.tenant_id``. Until then the tenant comes from the ``X-Tenant-Id`` header, which is only
acceptable for local development and must never reach production.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status


def get_tenant_id(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
) -> str:
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing tenant (TODO: replaced by current_principal, D1-05)",
        )
    return x_tenant_id
