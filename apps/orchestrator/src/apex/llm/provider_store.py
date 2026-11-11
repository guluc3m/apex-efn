"""Per-tenant LLM provider settings (base URL, API key, model).

The dashboard settings page writes these values through ``/v1/settings/llm-provider``; the
:class:`~apex.llm.provider_config.TenantRoleConfigProvider` reads them on every gateway call. The store
is deliberately in memory for now: persistence belongs to the data layer (D2-05), and keeping the
contract here lets the API and the gateway share one object without a database round trip.

Security rules:

* the raw key never leaves the process: :class:`LlmProviderSettings` hides it from ``repr`` and the API
  only exposes ``api_key_set``;
* versions are monotonic per tenant, even across ``clear()``, so the gateway's endpoint-id-keyed
  transport cache always rebuilds after a settings change;
* no wall-clock reads: the store takes an injectable :class:`~apex.common.clock.Clock` and ``set`` also
  accepts an explicit ``now`` for deterministic tests.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import SecretStr

from apex.common.clock import Clock, SystemClock


@dataclass(frozen=True, slots=True)
class LlmProviderSettings:
    """One tenant's OpenAI-compatible provider configuration.

    ``api_key`` is a :class:`~pydantic.SecretStr` and is excluded from ``repr``: a settings object may
    be logged on an error path, and the key must never appear there.
    """

    base_url: str
    model: str
    api_key: SecretStr | None = field(repr=False)
    version: int
    updated_at: datetime


class TenantProviderStore:
    """In-memory, thread-safe store of :class:`LlmProviderSettings` keyed by tenant id."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or SystemClock()
        self._settings: dict[str, LlmProviderSettings] = {}
        self._versions: dict[str, int] = {}
        self._lock = threading.Lock()

    def get(self, tenant_id: str) -> LlmProviderSettings | None:
        """The tenant's settings, or ``None`` when it has not configured a provider."""
        with self._lock:
            return self._settings.get(tenant_id)

    def set(
        self,
        tenant_id: str,
        base_url: str,
        model: str,
        api_key: SecretStr | str | None = None,
        now: datetime | None = None,
    ) -> LlmProviderSettings:
        """Create or replace a tenant's settings, bumping its monotonic version.

        ``now`` is explicit so tests never depend on the wall clock; production callers can omit it and
        the injected :class:`Clock` supplies the instant.
        """
        if not tenant_id.strip():
            raise ValueError("tenant_id must not be empty")
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")

        secret: SecretStr | None
        if api_key is None or isinstance(api_key, SecretStr):
            secret = api_key
        else:
            secret = SecretStr(api_key) if api_key else None

        with self._lock:
            version = self._versions.get(tenant_id, 0) + 1
            self._versions[tenant_id] = version
            settings = LlmProviderSettings(
                base_url=base_url,
                model=model,
                api_key=secret,
                version=version,
                updated_at=now or self._clock.now(),
            )
            self._settings[tenant_id] = settings
            return settings

    def clear(self, tenant_id: str) -> bool:
        """Remove a tenant's settings. Returns whether there was something to remove.

        The version counter is intentionally kept: a later ``set`` must produce a new endpoint id so the
        gateway cannot reuse a transport built for the cleared configuration.
        """
        with self._lock:
            return self._settings.pop(tenant_id, None) is not None


PROVIDER_STORE = TenantProviderStore()
"""Process-wide store shared by the settings API and the gateway wiring."""


__all__ = ["PROVIDER_STORE", "LlmProviderSettings", "TenantProviderStore"]
