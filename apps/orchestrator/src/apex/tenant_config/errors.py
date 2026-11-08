"""Errors raised by the tenant configuration service (ADR-400)."""

from __future__ import annotations


class TenantConfigError(Exception):
    """Base class for tenant configuration errors."""


class ConfigKeyUnset(TenantConfigError):
    """A required key is "sin definir" (unset). Loud by design: never defaulted (ADR-400 §3)."""

    def __init__(self, key: str, scope: str | None = None) -> None:
        self.key = key
        self.scope = scope
        where = f" (scope={scope})" if scope else ""
        super().__init__(
            f"config key '{key}' is unset ('sin definir'){where}; the tenant must supply it"
        )


class ConfigValidationError(TenantConfigError):
    """A patch or resolved mapping violates the typed schema or a cross-field rule."""


class NonConfigurableKeyError(ConfigValidationError):
    """The patch touches a key that may not be changed (e.g. ``money.supported_currencies``)."""


class StaleBaseVersionError(TenantConfigError):
    """The change was proposed against an outdated ``config_version`` (optimistic concurrency)."""

    def __init__(self, tenant_id: str, base: int, current: int) -> None:
        self.tenant_id = tenant_id
        self.base = base
        self.current = current
        super().__init__(
            f"tenant {tenant_id}: change based on config_version {base} but current is {current}"
        )


class ContentHashMismatchError(TenantConfigError):
    """Recomputing a stored version does not reproduce its ``content_hash`` (integrity failure)."""


class PendingChangeError(TenantConfigError):
    """No signed decision exists yet for this change; nothing was appended."""
