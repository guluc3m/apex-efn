"""Onboarding: the company profile, the financial snapshot and its activation (D4-07, spec §3.1).

Two rules drive this module:

1. **Onboarding is not complete without an active financial snapshot.** A mission cannot launch otherwise
   (criterion 1). The check lives here so every caller asks the same question.
2. **A snapshot is activated by a signed decision, all-or-nothing.** Uploading a CSV never activates
   anything: it returns an import report. Activation supersedes the previous snapshot, which stays
   immutable, and needs immediate re-authentication (spec §5.10).

The CSV parsing, the derived envelopes and the buying capacity belong to DEV-3 (D3-04): this module calls
them through a port and stores the result. It never parses money itself.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from apex.agents.ports import DecisionPort, DecisionRef


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OnboardingStatus(StrEnum):
    STARTED = "started"
    PROFILED = "profiled"
    AWAITING_SNAPSHOT_ACTIVATION = "awaiting_snapshot_activation"
    COMPLETE = "complete"


class SnapshotStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class CompanyProfile(_Model):
    """What the buyer told us. Every field is optional: the wizard is progressive."""

    legal_name: str | None = None
    sector: str | None = None
    country: str | None = None
    base_currency: str | None = Field(default=None, pattern="^(EUR|USD|CNY)$")
    budget_eur_minor: int | None = Field(default=None, ge=0)


class OnboardingSession(_Model):
    id: str
    tenant_id: str
    status: OnboardingStatus
    profile: CompanyProfile
    created_at: datetime
    updated_at: datetime
    active_snapshot_id: str | None = None
    pending_snapshot_id: str | None = None


class FinancialSnapshot(_Model):
    """An imported financial file. ``report`` is DEV-3's ``ImportReport`` verbatim, never re-derived here."""

    id: str
    tenant_id: str
    session_id: str
    status: SnapshotStatus
    stored_object: str
    """Key of the original file in object storage. The original is kept, never rewritten."""
    report: dict[str, Any]
    config_version: str
    imported_at: datetime
    activated_at: datetime | None = None
    superseded_at: datetime | None = None
    activation_decision_id: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status is SnapshotStatus.ACTIVE


class ImportResultLike(Protocol):
    """The part of DEV-3's ``ImportResult`` this module needs."""

    @property
    def report(self) -> Mapping[str, Any]: ...


class CsvImporter(Protocol):
    """DEV-3's ``apex.domain.finance.csv_import.parse`` (D3-04)."""

    async def parse(
        self, content: bytes, *, base_currency: str, tenant_id: str, now: datetime
    ) -> ImportResultLike: ...


class ObjectStore(Protocol):
    """S3/MinIO. Only the original bytes are stored; the report lives in the database."""

    async def put(self, key: str, content: bytes, *, content_type: str) -> str: ...


class OnboardingStore(Protocol):
    async def save_session(self, session: OnboardingSession) -> OnboardingSession: ...

    async def get_session(self, tenant_id: str, session_id: str) -> OnboardingSession | None: ...

    async def add_snapshot(self, snapshot: FinancialSnapshot) -> FinancialSnapshot: ...

    async def get_snapshot(self, tenant_id: str, snapshot_id: str) -> FinancialSnapshot | None: ...

    async def save_snapshot(self, snapshot: FinancialSnapshot) -> FinancialSnapshot: ...

    async def list_snapshots(self, tenant_id: str, session_id: str) -> list[FinancialSnapshot]: ...

    async def active_snapshot(self, tenant_id: str) -> FinancialSnapshot | None: ...


class InMemoryOnboardingStore:
    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], OnboardingSession] = {}
        self._snapshots: dict[tuple[str, str], FinancialSnapshot] = {}

    async def save_session(self, session: OnboardingSession) -> OnboardingSession:
        self._sessions[(session.tenant_id, session.id)] = session
        return session

    async def get_session(self, tenant_id: str, session_id: str) -> OnboardingSession | None:
        return self._sessions.get((tenant_id, session_id))

    async def add_snapshot(self, snapshot: FinancialSnapshot) -> FinancialSnapshot:
        self._snapshots[(snapshot.tenant_id, snapshot.id)] = snapshot
        return snapshot

    async def get_snapshot(self, tenant_id: str, snapshot_id: str) -> FinancialSnapshot | None:
        return self._snapshots.get((tenant_id, snapshot_id))

    async def save_snapshot(self, snapshot: FinancialSnapshot) -> FinancialSnapshot:
        self._snapshots[(snapshot.tenant_id, snapshot.id)] = snapshot
        return snapshot

    async def list_snapshots(self, tenant_id: str, session_id: str) -> list[FinancialSnapshot]:
        found = [
            s
            for (t, _), s in self._snapshots.items()
            if t == tenant_id and s.session_id == session_id
        ]
        return sorted(found, key=lambda s: (s.imported_at, s.id))

    async def active_snapshot(self, tenant_id: str) -> FinancialSnapshot | None:
        for (t, _), snapshot in self._snapshots.items():
            if t == tenant_id and snapshot.status is SnapshotStatus.ACTIVE:
                return snapshot
        return None


@dataclass(frozen=True)
class OnboardingDeps:
    store: OnboardingStore
    importer: CsvImporter
    objects: ObjectStore
    decisions: DecisionPort
    clock: Any
    ids: Any
    stale_after_days: int
    """``finance.stale_after_days`` from tenant config. Required: no default."""
    config_version: Callable[[str], str]
    """``tenant_id -> config_version``, supplied by the tenant config service (D4-03)."""


class OnboardingIncomplete(Exception):
    """The tenant has no active financial snapshot. Missions cannot launch (criterion 1)."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__(f"tenant {tenant_id} has no active financial snapshot")
        self.tenant_id = tenant_id


class SnapshotNotActivatable(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class OnboardingService:
    def __init__(self, deps: OnboardingDeps) -> None:
        self._deps = deps

    # ------------------------------------------------------------------ sessions

    async def start_session(self, *, tenant_id: str) -> OnboardingSession:
        now = self._deps.clock.now()
        session = OnboardingSession(
            id=self._deps.ids.new_id(),
            tenant_id=tenant_id,
            status=OnboardingStatus.STARTED,
            profile=CompanyProfile(),
            created_at=now,
            updated_at=now,
        )
        return await self._deps.store.save_session(session)

    async def update_profile(
        self, *, tenant_id: str, session_id: str, profile: CompanyProfile
    ) -> OnboardingSession:
        session = await self._require_session(tenant_id, session_id)
        updated = session.model_copy(
            update={
                "profile": profile,
                "status": OnboardingStatus.PROFILED,
                "updated_at": self._deps.clock.now(),
            }
        )
        return await self._deps.store.save_session(updated)

    # ------------------------------------------------------------------ financial CSV

    async def upload_financial_csv(
        self,
        *,
        tenant_id: str,
        session_id: str,
        content: bytes,
        filename: str,
        base_currency: str,
    ) -> FinancialSnapshot:
        """Store the original and import it. **Never activates anything** (spec §3.1.1)."""
        session = await self._require_session(tenant_id, session_id)
        now = self._deps.clock.now()
        snapshot_id = self._deps.ids.new_id()
        key = f"financial-csv/{tenant_id}/{session_id}/{snapshot_id}/{filename}"
        stored = await self._deps.objects.put(key, content, content_type="text/csv")
        result = await self._deps.importer.parse(
            content, base_currency=base_currency, tenant_id=tenant_id, now=now
        )
        snapshot = FinancialSnapshot(
            id=snapshot_id,
            tenant_id=tenant_id,
            session_id=session_id,
            status=SnapshotStatus.DRAFT,
            stored_object=stored,
            report=dict(result.report),
            config_version=self._deps.config_version(tenant_id),
            imported_at=now,
        )
        await self._deps.store.add_snapshot(snapshot)
        await self._deps.store.save_session(
            session.model_copy(
                update={
                    "pending_snapshot_id": snapshot.id,
                    "status": OnboardingStatus.AWAITING_SNAPSHOT_ACTIVATION,
                    "updated_at": now,
                }
            )
        )
        return snapshot

    async def request_activation(
        self, *, tenant_id: str, session_id: str, snapshot_id: str
    ) -> DecisionRef:
        """Create the signed decision that activation requires. Nothing changes until it is signed."""
        snapshot = await self._require_snapshot(tenant_id, snapshot_id)
        if snapshot.session_id != session_id:
            raise SnapshotNotActivatable("snapshot does not belong to this onboarding session")
        if snapshot.status is not SnapshotStatus.DRAFT:
            raise SnapshotNotActivatable(f"snapshot is already {snapshot.status.value}")
        return await self._deps.decisions.create_decision(
            "financial_snapshot_activation",
            f"financial_snapshot:{snapshot.id}",
            {
                "snapshot_id": snapshot.id,
                "session_id": session_id,
                "stored_object": snapshot.stored_object,
                "config_version": snapshot.config_version,
                "report_digest": _digest(snapshot.report),
            },
            tenant_id=tenant_id,
        )

    async def activate(
        self, *, tenant_id: str, session_id: str, snapshot_id: str, decision_id: str
    ) -> FinancialSnapshot:
        """Activate after ``require_signed``. All-or-nothing: the previous snapshot becomes ``superseded``."""
        signed = await self._deps.decisions.require_signed(decision_id, tenant_id=tenant_id)
        snapshot = await self._require_snapshot(tenant_id, snapshot_id)
        if signed.subject_ref != f"financial_snapshot:{snapshot.id}":
            raise SnapshotNotActivatable("the signed decision is for another snapshot")
        if signed.payload.get("report_digest") != _digest(snapshot.report):
            raise SnapshotNotActivatable("the import report changed since it was signed")
        session = await self._require_session(tenant_id, session_id)
        now = self._deps.clock.now()
        previous = await self._deps.store.active_snapshot(tenant_id)
        if previous is not None and previous.id != snapshot.id:
            await self._deps.store.save_snapshot(
                previous.model_copy(
                    update={"status": SnapshotStatus.SUPERSEDED, "superseded_at": now}
                )
            )
        activated = snapshot.model_copy(
            update={
                "status": SnapshotStatus.ACTIVE,
                "activated_at": now,
                "activation_decision_id": decision_id,
            }
        )
        await self._deps.store.save_snapshot(activated)
        await self._deps.store.save_session(
            session.model_copy(
                update={
                    "status": OnboardingStatus.COMPLETE,
                    "active_snapshot_id": activated.id,
                    "pending_snapshot_id": None,
                    "updated_at": now,
                }
            )
        )
        return activated

    # ------------------------------------------------------------------ gates

    async def require_active_snapshot(self, *, tenant_id: str) -> FinancialSnapshot:
        """Criterion 1: no mission without an active snapshot."""
        snapshot = await self._deps.store.active_snapshot(tenant_id)
        if snapshot is None:
            raise OnboardingIncomplete(tenant_id)
        return snapshot

    async def is_financials_stale(self, *, tenant_id: str) -> bool:
        """``financials_stale`` after ``finance.stale_after_days`` (spec §3.5). No active snapshot is stale."""
        snapshot = await self._deps.store.active_snapshot(tenant_id)
        if snapshot is None or snapshot.activated_at is None:
            return True
        age: timedelta = self._deps.clock.now() - snapshot.activated_at
        return bool(age > timedelta(days=self._deps.stale_after_days))

    async def _require_session(self, tenant_id: str, session_id: str) -> OnboardingSession:
        session = await self._deps.store.get_session(tenant_id, session_id)
        if session is None:
            raise LookupError(f"onboarding session {session_id} not found")
        return session

    async def _require_snapshot(self, tenant_id: str, snapshot_id: str) -> FinancialSnapshot:
        snapshot = await self._deps.store.get_snapshot(tenant_id, snapshot_id)
        if snapshot is None:
            raise LookupError(f"financial snapshot {snapshot_id} not found")
        return snapshot


def _digest(report: Mapping[str, Any]) -> str:
    """Stable digest of the import report, so a signed activation binds the exact numbers."""
    import hashlib
    import json

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "CompanyProfile",
    "CsvImporter",
    "FinancialSnapshot",
    "InMemoryOnboardingStore",
    "ObjectStore",
    "OnboardingDeps",
    "OnboardingIncomplete",
    "OnboardingService",
    "OnboardingSession",
    "OnboardingStatus",
    "OnboardingStore",
    "SnapshotNotActivatable",
    "SnapshotStatus",
]
