"""Ports (Protocols) this service depends on. All async (the async/sync question is open).

- ``ConfigRepository``: persistence of append-only versions. Implemented in memory here; the SQLAlchemy
  implementation is a TODO pending D2-05 (``apex.db``).
- ``DecisionPort``: a mirror of DEV-2's ``apex.signing.api`` (``create_decision`` / ``require_signed``).
  The real module does not exist yet; DEV-2 must match these signatures (see the interface request).
- ``Clock``: re-exported from ``apex.common.clock`` (D4-01a) so there is one injectable clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from apex.common.clock import Clock as Clock  # re-exported: one injectable clock (D4-01a)


@dataclass(frozen=True, slots=True)
class ConfigVersionRecord:
    """One immutable, append-only version of a tenant's configuration."""

    tenant_id: str
    config_version: int
    content_hash: str
    values: dict[str, Any]
    """Tenant-layer patch applied on top of the global defaults (plain nested mapping)."""
    created_at: datetime
    decision_id: str | None = None
    """Signed decision that created this version (None for the seeded v1 baseline)."""


@dataclass(frozen=True, slots=True)
class Decision:
    """Subset of DEV-2's ``Decision`` that this service needs."""

    id: str
    type: str
    subject_ref: str
    status: str
    """One of ``pending_signature | signed | rejected`` (DEV-2 owns the full state machine)."""
    payload: dict[str, Any] = field(default_factory=dict)


class PendingSignature(Exception):
    """Raised by ``require_signed`` when the decision has no valid signature yet (DEV-2 contract)."""


@runtime_checkable
class DecisionPort(Protocol):
    async def create_decision(
        self, type: str, subject_ref: str, payload: dict[str, Any]
    ) -> Decision:
        """Create a ``pending_signature`` decision. Mirror of ``apex.signing.api.create_decision``."""
        ...

    async def require_signed(self, decision_id: str) -> Decision:
        """Return the signed decision, or raise ``PendingSignature``. Mirror of ``require_signed``."""
        ...


@runtime_checkable
class ConfigRepository(Protocol):
    async def latest_version(self, tenant_id: str) -> ConfigVersionRecord | None: ...

    async def get_version(
        self, tenant_id: str, config_version: int
    ) -> ConfigVersionRecord | None: ...

    async def list_versions(self, tenant_id: str) -> list[ConfigVersionRecord]: ...

    async def append_version(self, record: ConfigVersionRecord) -> None:
        """Append only. Must reject a ``config_version`` that is not ``latest + 1`` (monotonic)."""
        ...
