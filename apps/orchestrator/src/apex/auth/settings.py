"""Authentication settings for the orchestrator (D1-05, DEV-1).

Read from the environment on purpose: ``apex/config.py`` belongs to DEV-4, and this module is the
integration seam other lanes import. The variables are documented in ``docs/security/rbac.md`` and
``docs/adr/101-orchestrator-jwt-validation.md``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_ISSUER = "http://localhost:8080/realms/apex"
DEFAULT_AUDIENCE = "apex-orchestrator"
DEFAULT_JWKS_CACHE_TTL_SECONDS = 300.0
DEFAULT_JWKS_REFETCH_COOLDOWN_SECONDS = 10.0
DEFAULT_CLOCK_SKEW_SECONDS = 30
DEFAULT_HTTP_TIMEOUT_SECONDS = 5.0

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class AuthConfigurationError(RuntimeError):
    """The authentication configuration is unusable. Raised at startup, never per request."""


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_number(name: str, default: float, *, integer: bool = False) -> float | int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw) if integer else float(raw)
    except ValueError as exc:
        raise AuthConfigurationError(f"{name} must be a number, got {raw!r}") from exc


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """Validated authentication configuration.

    ``issuer`` and ``audience`` are checked against every access token. ``jwks_url`` is where the
    RS256 public keys are fetched from; it defaults to Keycloak's discovery path.
    """

    issuer: str
    audience: str
    jwks_url: str
    cache_ttl_seconds: float = DEFAULT_JWKS_CACHE_TTL_SECONDS
    refetch_cooldown_seconds: float = DEFAULT_JWKS_REFETCH_COOLDOWN_SECONDS
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS
    http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS
    auth_disabled: bool = False

    def __post_init__(self) -> None:
        self._validate_issuer()
        if not self.audience:
            raise AuthConfigurationError("APEX_AUTH_AUDIENCE must not be empty")
        if not self.jwks_url:
            raise AuthConfigurationError("APEX_AUTH_JWKS_URL must not be empty")
        if self.cache_ttl_seconds <= 0:
            raise AuthConfigurationError("APEX_AUTH_JWKS_CACHE_TTL_SECONDS must be positive")
        if self.refetch_cooldown_seconds < 0:
            raise AuthConfigurationError(
                "APEX_AUTH_JWKS_REFETCH_COOLDOWN_SECONDS must not be negative"
            )
        if self.clock_skew_seconds < 0:
            raise AuthConfigurationError("APEX_AUTH_CLOCK_SKEW_SECONDS must not be negative")
        if self.http_timeout_seconds <= 0:
            raise AuthConfigurationError("APEX_AUTH_HTTP_TIMEOUT_SECONDS must be positive")

    def _validate_issuer(self) -> None:
        parsed = urlparse(self.issuer)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AuthConfigurationError(
                f"APEX_AUTH_ISSUER must be an absolute URL, got {self.issuer!r}"
            )
        # Plain HTTP is only acceptable against a local development IdP. A remote issuer over HTTP
        # would let anyone on the network replace the keys we trust.
        if parsed.scheme == "http" and (parsed.hostname or "") not in _LOOPBACK_HOSTS:
            raise AuthConfigurationError(
                "APEX_AUTH_ISSUER must use https unless it points at localhost/127.0.0.1"
            )

    @classmethod
    def from_env(cls) -> AuthSettings:
        issuer = _env("APEX_AUTH_ISSUER", DEFAULT_ISSUER).rstrip("/")
        return cls(
            issuer=issuer,
            audience=_env("APEX_AUTH_AUDIENCE", DEFAULT_AUDIENCE),
            jwks_url=_env("APEX_AUTH_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"),
            cache_ttl_seconds=float(
                _env_number("APEX_AUTH_JWKS_CACHE_TTL_SECONDS", DEFAULT_JWKS_CACHE_TTL_SECONDS)
            ),
            refetch_cooldown_seconds=float(
                _env_number(
                    "APEX_AUTH_JWKS_REFETCH_COOLDOWN_SECONDS", DEFAULT_JWKS_REFETCH_COOLDOWN_SECONDS
                )
            ),
            clock_skew_seconds=int(
                _env_number(
                    "APEX_AUTH_CLOCK_SKEW_SECONDS", DEFAULT_CLOCK_SKEW_SECONDS, integer=True
                )
            ),
            http_timeout_seconds=float(
                _env_number("APEX_AUTH_HTTP_TIMEOUT_SECONDS", DEFAULT_HTTP_TIMEOUT_SECONDS)
            ),
            auth_disabled=_env_flag("APEX_AUTH_DISABLED", False),
        )


__all__ = [
    "AuthConfigurationError",
    "AuthSettings",
    "DEFAULT_AUDIENCE",
    "DEFAULT_ISSUER",
]
