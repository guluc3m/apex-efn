"""Scheduled job bodies: injected clock, injected ports, no wall clock and no hardcoded numbers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from apex.agents.supervisor import (
    BudgetState,
    MissionAssessment,
    MissionHealth,
    SupervisorAction,
    SupervisorReport,
)
from apex.common.clock import FixedClock
from apex.workers.jobs import (
    JobParams,
    ingest_fx_rates,
    mark_stale_financials,
    refresh_seller_snapshots,
    send_gate_sla_reminders,
    supervise_missions,
    verify_audit_chain,
)
from apex.workers.ports import (
    AuditVerifyResult,
    FxIngestResult,
    GateReminderResult,
    SnapshotRefreshResult,
    StaleFinancialsResult,
    WorkerPorts,
)

NOW = datetime(2026, 3, 1, 6, 0, tzinfo=UTC)


@dataclass
class _FakeFx:
    calls: list[datetime]

    async def ingest_for(self, as_of: datetime) -> FxIngestResult:
        self.calls.append(as_of)
        return FxIngestResult(as_of=as_of, inserted=2, already_present=1)


@dataclass
class _FakeAudit:
    chain_ok: bool
    first_broken_seq: int | None = None
    calls: int = 0

    async def verify_chain(self) -> AuditVerifyResult:
        self.calls += 1
        return AuditVerifyResult(
            chain_ok=self.chain_ok, events_checked=42, first_broken_seq=self.first_broken_seq
        )


@dataclass
class _FakeGate:
    calls: list[datetime]

    async def remind(self, now: datetime) -> GateReminderResult:
        self.calls.append(now)
        return GateReminderResult(reminders_sent=3, breached=1)


@dataclass
class _FakeSnapshots:
    calls: list[tuple[datetime, int]]

    async def refresh_older_than(
        self, now: datetime, max_age_days: int
    ) -> SnapshotRefreshResult:
        self.calls.append((now, max_age_days))
        return SnapshotRefreshResult(refreshed=7)


@dataclass
class _FakeFinancials:
    calls: list[tuple[datetime, int]]

    async def mark_stale(self, now: datetime, stale_after_days: int) -> StaleFinancialsResult:
        self.calls.append((now, stale_after_days))
        return StaleFinancialsResult(marked_stale=4)


@dataclass
class _FakeSupervisor:
    calls: list[datetime]

    async def tick(self, now: datetime) -> SupervisorReport:
        self.calls.append(now)
        stuck = MissionAssessment(
            mission_id="m-1",
            health=MissionHealth.STUCK,
            budget=BudgetState.WITHIN_BUDGET,
            actions=(SupervisorAction.ESCALATE_STUCK,),
            escalation=None,
        )
        healthy = MissionAssessment(
            mission_id="m-2",
            health=MissionHealth.HEALTHY,
            budget=BudgetState.WITHIN_BUDGET,
            actions=(SupervisorAction.NONE,),
            escalation=None,
        )
        return SupervisorReport(checked_at=now, assessments=(stuck, healthy))


@dataclass
class _Recorder:
    fx: _FakeFx
    audit: _FakeAudit
    gate: _FakeGate
    snapshots: _FakeSnapshots
    financials: _FakeFinancials
    supervisor: _FakeSupervisor

    def ports(self) -> WorkerPorts:
        return WorkerPorts(
            fx=self.fx,
            audit=self.audit,
            gate=self.gate,
            snapshots=self.snapshots,
            financials=self.financials,
            supervisor=self.supervisor,
        )


def _recorder() -> _Recorder:
    return _Recorder(
        fx=_FakeFx(calls=[]),
        audit=_FakeAudit(chain_ok=True),
        gate=_FakeGate(calls=[]),
        snapshots=_FakeSnapshots(calls=[]),
        financials=_FakeFinancials(calls=[]),
        supervisor=_FakeSupervisor(calls=[]),
    )


PARAMS = JobParams(snapshot_max_age_days=7, financials_stale_after_days=30)


async def test_fx_ingestion_uses_injected_clock_as_as_of() -> None:
    rec = _recorder()
    clock = FixedClock(NOW)
    out = await ingest_fx_rates(clock, rec.ports())
    assert rec.fx.calls == [NOW]
    assert out == {
        "job": "fx_ingestion",
        "as_of": NOW.isoformat(),
        "inserted": 2,
        "already_present": 1,
    }


async def test_fx_ingestion_follows_clock_advance() -> None:
    rec = _recorder()
    clock = FixedClock(NOW)
    await ingest_fx_rates(clock, rec.ports())
    clock.advance(timedelta(days=1))
    await ingest_fx_rates(clock, rec.ports())
    assert rec.fx.calls == [NOW, NOW + timedelta(days=1)]


async def test_audit_verify_reports_broken_link() -> None:
    rec = _recorder()
    rec.audit = _FakeAudit(chain_ok=False, first_broken_seq=17)
    out = await verify_audit_chain(FixedClock(NOW), rec.ports())
    assert out["chain_ok"] is False
    assert out["first_broken_seq"] == 17
    assert out["verified_at"] == NOW.isoformat()


async def test_audit_verify_is_read_only_and_repeatable() -> None:
    rec = _recorder()
    first = await verify_audit_chain(FixedClock(NOW), rec.ports())
    second = await verify_audit_chain(FixedClock(NOW), rec.ports())
    assert first == second
    assert rec.audit.calls == 2


async def test_gate_reminders_receive_injected_now() -> None:
    rec = _recorder()
    out = await send_gate_sla_reminders(FixedClock(NOW), rec.ports())
    assert rec.gate.calls == [NOW]
    assert out["reminders_sent"] == 3 and out["breached"] == 1


async def test_snapshot_refresh_passes_configured_max_age() -> None:
    rec = _recorder()
    out = await refresh_seller_snapshots(FixedClock(NOW), rec.ports(), PARAMS)
    assert rec.snapshots.calls == [(NOW, 7)]
    assert out["refreshed"] == 7


async def test_stale_financials_passes_configured_window() -> None:
    rec = _recorder()
    out = await mark_stale_financials(FixedClock(NOW), rec.ports(), PARAMS)
    assert rec.financials.calls == [(NOW, 30)]
    assert out["marked_stale"] == 4


async def test_supervisor_tick_uses_injected_clock_and_counts_actions() -> None:
    rec = _recorder()
    out = await supervise_missions(FixedClock(NOW), rec.ports())
    assert rec.supervisor.calls == [NOW]
    assert out["missions_checked"] == 2
    assert out["escalations"] == 0
    assert out["actions"] == {"escalate_stuck": 1, "none": 1}


async def test_supervisor_port_fails_loudly_when_unwired() -> None:
    with pytest.raises(NotImplementedError, match="D4-06"):
        await supervise_missions(FixedClock(NOW), WorkerPorts.unwired())


@pytest.mark.parametrize(
    ("job", "owner_hint"),
    [
        (ingest_fx_rates, "D3-03"),
        (verify_audit_chain, "D2-10"),
        (send_gate_sla_reminders, "D4-11"),
    ],
)
async def test_unwired_ports_fail_loudly_naming_the_owner(
    job: object, owner_hint: str
) -> None:
    with pytest.raises(NotImplementedError, match=owner_hint):
        await job(FixedClock(NOW), WorkerPorts.unwired())  # type: ignore[operator]


@pytest.mark.parametrize("job", [refresh_seller_snapshots, mark_stale_financials])
async def test_unwired_parameterised_jobs_fail_loudly(job: object) -> None:
    with pytest.raises(NotImplementedError, match="D4-"):
        await job(FixedClock(NOW), WorkerPorts.unwired(), PARAMS)  # type: ignore[operator]


def test_job_params_has_no_defaults() -> None:
    with pytest.raises(TypeError):
        JobParams()  # type: ignore[call-arg]
