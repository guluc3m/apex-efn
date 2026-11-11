"""Inbound platform webhooks (D5-11, spec §8).

A marketplace calls us, not the other way round, so this endpoint is authenticated by an **HMAC signature**
over the raw body with a per-platform shared secret — never by a user token, and never by trusting the
payload. The rules:

* The signature is compared in constant time. A missing or wrong signature is a 401 and the body is not read
  further.
* Every event is deduplicated by ``platform_ref``: platforms retry aggressively, and a duplicate must not
  become a second state change.
* An unknown ``event_type`` is accepted and ignored (202). Platforms send many event types we do not model,
  and answering 4xx makes them retry forever.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

SIGNATURE_HEADER = "X-Platform-Signature"
SECRET_ENV_PREFIX = "APEX_WEBHOOK_SECRET_"


class WebhookRejected(Exception):
    """The event is not from the platform. ``reason`` is a closed code for the problem body."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class WebhookEvent:
    """The contract's ``PlatformWebhookEvent``, validated."""

    platform: str
    event_type: str
    platform_ref: str
    occurred_at: datetime
    data: Mapping[str, Any] = field(default_factory=dict)


class ReplayGuard(Protocol):
    """Deduplicates by ``platform_ref``. Returns True the first time it sees a ref."""

    async def first_seen(self, platform: str, platform_ref: str) -> bool: ...


@dataclass
class InMemoryReplayGuard:
    _seen: set[tuple[str, str]] = field(default_factory=set)

    async def first_seen(self, platform: str, platform_ref: str) -> bool:
        key = (platform, platform_ref)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


def secret_for(platform: str, environ: Mapping[str, str] | None = None) -> str | None:
    """The shared secret for a platform, from the environment.

    ``APEX_WEBHOOK_SECRET_<PLATFORM>`` with the platform id upper-cased and non-alphanumerics replaced by
    underscores, so ``mock-a`` reads ``APEX_WEBHOOK_SECRET_MOCK_A``.
    """
    env = os.environ if environ is None else environ
    key = SECRET_ENV_PREFIX + "".join(ch.upper() if ch.isalnum() else "_" for ch in platform)
    value = env.get(key)
    return value or None


def verify_signature(secret: str, body: bytes, signature: str | None) -> None:
    """Raise ``WebhookRejected`` unless ``signature`` is the hex HMAC-SHA256 of ``body``."""
    if not signature:
        raise WebhookRejected("missing_signature", f"{SIGNATURE_HEADER} is required")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature.strip().lower()
    if provided.startswith("sha256="):
        provided = provided[len("sha256=") :]
    if not hmac.compare_digest(expected, provided):
        raise WebhookRejected("invalid_signature", "the signature does not match the body")


def sign(secret: str, body: bytes) -> str:
    """The signature a platform would send. Used by tests and by the mock marketplace."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


Handler = Callable[[WebhookEvent], Any]


__all__ = [
    "Handler",
    "InMemoryReplayGuard",
    "ReplayGuard",
    "SECRET_ENV_PREFIX",
    "SIGNATURE_HEADER",
    "WebhookEvent",
    "WebhookRejected",
    "secret_for",
    "sign",
    "verify_signature",
]
