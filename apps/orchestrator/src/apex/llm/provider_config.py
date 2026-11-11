"""Tenant-aware decorators for the gateway's role config and secret resolution.

The gateway consumes two ports (:class:`~apex.llm.config.RoleConfigProvider` and
:class:`~apex.llm.config.SecretResolver`). These wrappers keep the environment/``LLM_GATEWAY_*``
configuration as the fallback and overlay the per-tenant provider settings written through the
dashboard when they exist.

The endpoint id embeds the settings version (``tenant-<id>-v<n>``) on purpose: the gateway caches one
transport per endpoint id, so a settings change must produce a new id or the old base URL/key would
keep being used until a restart.
"""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from apex.llm.config import (
    LLMRole,
    LLMRolesConfig,
    RoleConfigProvider,
    RoleEndpointConfig,
    SecretResolver,
)
from apex.llm.provider_store import TenantProviderStore

TENANT_REF_PREFIX = "tenant:"
"""Prefix of an ``api_key_ref`` that points at the tenant provider store instead of the fallback."""


class TenantRoleConfigProvider:
    """Overlay a tenant's provider settings on top of the default role configuration.

    When the tenant has no settings, the defaults are returned untouched. When it does, every role points
    at the tenant's ``base_url``/``model`` with a tenant-scoped secret reference and a versioned endpoint
    id. The shared ``endpoints`` registry contains the canonical endpoint so the gateway can resolve the
    id from either a role or a fallback hop.
    """

    def __init__(self, defaults: RoleConfigProvider, store: TenantProviderStore) -> None:
        self._defaults = defaults
        self._store = store

    def llm_roles(self, tenant_id: str) -> LLMRolesConfig:
        defaults = self._defaults.llm_roles(tenant_id)
        settings = self._store.get(tenant_id)
        if settings is None:
            return defaults

        endpoint_id = f"tenant-{tenant_id}-v{settings.version}"
        api_key_ref = f"{TENANT_REF_PREFIX}{tenant_id}"
        roles: dict[LLMRole, RoleEndpointConfig] = {}
        canonical: RoleEndpointConfig | None = None
        for role, role_config in defaults.roles.items():
            update: dict[str, Any] = {
                "endpoint_id": endpoint_id,
                "base_url": settings.base_url,
                "model": settings.model,
                "api_key_ref": api_key_ref,
                # The defaults' fallbacks reference default endpoint ids that are not part of the
                # tenant overlay. Falling back to another provider would also silently move data
                # outside the provider the tenant chose, so the tenant endpoint stands alone.
                "fallback": [],
            }
            overridden = role_config.model_copy(update=update)
            roles[role] = overridden
            if canonical is None:
                canonical = overridden

        if canonical is None:
            raise RuntimeError("the default role configuration declares no LLM roles")

        return LLMRolesConfig(
            roles=roles,
            endpoints={endpoint_id: canonical},
            resilience=defaults.resilience,
        )


class TenantSecretResolver:
    """Resolve ``tenant:<id>`` references from the store and delegate every other ref."""

    def __init__(self, store: TenantProviderStore, fallback: SecretResolver) -> None:
        self._store = store
        self._fallback = fallback

    def resolve(self, ref: str) -> SecretStr:
        if not ref.startswith(TENANT_REF_PREFIX):
            return self._fallback.resolve(ref)

        tenant_id = ref[len(TENANT_REF_PREFIX) :]
        if not tenant_id:
            raise KeyError("tenant secret reference has no tenant id")
        settings = self._store.get(tenant_id)
        if settings is None or settings.api_key is None:
            raise KeyError(f"no API key configured for tenant {tenant_id!r}")
        return settings.api_key


__all__ = ["TENANT_REF_PREFIX", "TenantRoleConfigProvider", "TenantSecretResolver"]
