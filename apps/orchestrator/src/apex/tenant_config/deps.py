"""FastAPI dependencies for the config router.

The dev-only ``X-Tenant-Id`` header now lives in :mod:`apex.common.tenant` so every router shares one
implementation and one switch. TODO(DEV-1 / D1-05): replace it with ``apex.auth.deps.current_principal``.
"""

from __future__ import annotations

from apex.common.tenant import ALLOW_TENANT_HEADER_ENV, get_tenant_id, tenant_header_enabled

__all__ = ["ALLOW_TENANT_HEADER_ENV", "get_tenant_id", "tenant_header_enabled"]
