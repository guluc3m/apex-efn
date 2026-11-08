"""Ports the scheduled jobs call. Each is implemented by the lane that owns the capability.

Until the owning lane lands, the default ``Unwired*`` implementations raise ``NotImplementedError``
with the owner named, so a job that is scheduled before its dependency is wired fails loudly instead
of silently doing nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class FxIngestResult:
    """Outcome of one daily FX ingestion. Rates are immutable history; re-ingesting is a no-op."""

    as_of: datetime
    inserted: int
    already_present: int


@dataclass(frozen=True)
class AuditVerifyResult:
    """Outcome of a full audit chain re-verification (D2-10)."""

    chain_ok: bool
    events_checked: int
    first_broken_seq: int | None


@dataclass(frozen=True)
class GateReminderResult:
    """Reminders sent for gate queue items approaching or past their SLA (D4-11)."""

    reminders_sent: int
    breached: int


@dataclass(frozen=True)
class SnapshotRefreshResult:
    """Seller snapshots recomputed because they were older than the configured maximum age."""

    refreshed: int


@dataclass(frozen=True)
class StaleFinancialsResult:
    """Financial snapshots marked stale after ``finance.stale_after_days`` (D4-07)."""

    marked_stale: int


class FxRateSource(Protocol):
    """Fetches and stores daily reference rates (D3-03). Must be insert-only and idempotent per day."""

    async def ingest_for(self, as_of: datetime) -> FxIngestResult: ...


class AuditChainVerifier(Protocol):
    """Re-verifies the whole audit hash chain (D2-10) and reports the first broken link."""

    async def verify_chain(self) -> AuditVerifyResult: ...


class GateReminder(Protocol):
    """Sends SLA reminders for gate items (D4-11). ``now`` is injected so SLA maths is testable."""

    async def remind(self, now: datetime) -> GateReminderResult: ...


class SnapshotRefresher(Protocol):
    """Refreshes seller confidence snapshots older than the configured max age (D4-10)."""

    async def refresh_older_than(
        self, now: datetime, max_age_days: int
    ) -> SnapshotRefreshResult: ...


class FinancialStalenessMarker(Protocol):
    """Marks financial snapshots stale past the configured window (D4-07)."""

    async def mark_stale(self, now: datetime, stale_after_days: int) -> StaleFinancialsResult: ...


class UnwiredFxRateSource:
    async def ingest_for(self, as_of: datetime) -> FxIngestResult:
        raise NotImplementedError("FX ingestion port is not wired yet (owner: DEV-3, D3-03)")


class UnwiredAuditChainVerifier:
    async def verify_chain(self) -> AuditVerifyResult:
        raise NotImplementedError("audit verifier port is not wired yet (owner: DEV-2, D2-10)")


class UnwiredGateReminder:
    async def remind(self, now: datetime) -> GateReminderResult:
        raise NotImplementedError("gate reminder port is not wired yet (owner: DEV-4, D4-11)")


class UnwiredSnapshotRefresher:
    async def refresh_older_than(self, now: datetime, max_age_days: int) -> SnapshotRefreshResult:
        raise NotImplementedError("seller snapshot port is not wired yet (owner: DEV-4, D4-10)")


class UnwiredFinancialStalenessMarker:
    async def mark_stale(self, now: datetime, stale_after_days: int) -> StaleFinancialsResult:
        raise NotImplementedError("financial staleness port is not wired yet (owner: DEV-4, D4-07)")


@dataclass(frozen=True)
class WorkerPorts:
    """Everything the jobs need. Build with ``WorkerPorts.unwired()`` and replace fields as lanes land."""

    fx: FxRateSource
    audit: AuditChainVerifier
    gate: GateReminder
    snapshots: SnapshotRefresher
    financials: FinancialStalenessMarker

    @classmethod
    def unwired(cls) -> WorkerPorts:
        return cls(
            fx=UnwiredFxRateSource(),
            audit=UnwiredAuditChainVerifier(),
            gate=UnwiredGateReminder(),
            snapshots=UnwiredSnapshotRefresher(),
            financials=UnwiredFinancialStalenessMarker(),
        )


__all__ = [
    "AuditChainVerifier",
    "AuditVerifyResult",
    "FinancialStalenessMarker",
    "FxIngestResult",
    "FxRateSource",
    "GateReminder",
    "GateReminderResult",
    "SnapshotRefresher",
    "SnapshotRefreshResult",
    "StaleFinancialsResult",
    "WorkerPorts",
]
