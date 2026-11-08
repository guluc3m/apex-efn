"""Registry wiring, in-process scheduler and the Arq adapter (no Redis, no worker process, no sleeps)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from arq.connections import RedisSettings
from arq.cron import CronJob
from pydantic import ValidationError

from apex.common.clock import FixedClock
from apex.workers.arq_adapter import (
    CLOCK_CTX_KEY,
    arq_cron_jobs,
    build_worker_settings,
    worker_settings_factory,
)
from apex.workers.jobs import JobParams
from apex.workers.ports import (
    AuditVerifyResult,
    FxIngestResult,
    GateReminderResult,
    SnapshotRefreshResult,
    StaleFinancialsResult,
    WorkerPorts,
)
from apex.workers.registry import (
    JOB_AUDIT,
    JOB_FINANCIALS,
    JOB_FX,
    JOB_GATE,
    JOB_SNAPSHOTS,
    WorkerSchedules,
    build_registry,
)
from apex.workers.scheduler import InProcessScheduler, ScheduleError

NOW = datetime(2026, 3, 1, 6, 0, tzinfo=UTC)
SCHEDULES = WorkerSchedules(
    fx_ingestion="0 6 * * *",
    audit_chain_verify="0 3 * * *",
    gate_sla_reminders="0 8 * * 0,1,2,3",
    seller_snapshot_refresh="30 4 * * *",
    financials_stale_marking="0 5 * * *",
)
PARAMS = JobParams(snapshot_max_age_days=7, financials_stale_after_days=30)


class _Fx:
    async def ingest_for(self, as_of: datetime) -> FxIngestResult:
        return FxIngestResult(as_of=as_of, inserted=1, already_present=0)


class _Audit:
    async def verify_chain(self) -> AuditVerifyResult:
        return AuditVerifyResult(chain_ok=True, events_checked=1, first_broken_seq=None)


class _Gate:
    async def remind(self, now: datetime) -> GateReminderResult:
        return GateReminderResult(reminders_sent=0, breached=0)


class _Snapshots:
    async def refresh_older_than(self, now: datetime, max_age_days: int) -> SnapshotRefreshResult:
        return SnapshotRefreshResult(refreshed=0)


class _Financials:
    async def mark_stale(self, now: datetime, stale_after_days: int) -> StaleFinancialsResult:
        return StaleFinancialsResult(marked_stale=0)


def _ports() -> WorkerPorts:
    return WorkerPorts(
        fx=_Fx(), audit=_Audit(), gate=_Gate(), snapshots=_Snapshots(), financials=_Financials()
    )


def _registry() -> Any:
    return build_registry(schedules=SCHEDULES, ports=_ports(), params=PARAMS)


def test_registry_contains_the_five_jobs() -> None:
    names = [job.name for job in _registry().all()]
    assert names == sorted([JOB_AUDIT, JOB_FINANCIALS, JOB_FX, JOB_GATE, JOB_SNAPSHOTS])


def test_schedules_are_required_and_forbid_extra_keys() -> None:
    with pytest.raises(ValidationError):
        WorkerSchedules()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        WorkerSchedules(**SCHEDULES.model_dump(), unknown_job="* * * * *")


def test_invalid_cron_expression_fails_at_registry_build() -> None:
    bad = SCHEDULES.model_copy(update={"fx_ingestion": "70 * * * *"})
    with pytest.raises(ScheduleError):
        build_registry(schedules=bad, ports=_ports(), params=PARAMS)


def test_duplicate_registration_is_rejected() -> None:
    registry = _registry()
    with pytest.raises(ScheduleError):
        registry.register(registry.get(JOB_FX))


def test_in_process_scheduler_selects_due_jobs_at_injected_instant() -> None:
    scheduler = InProcessScheduler(_registry(), FixedClock(NOW))
    assert [job.name for job in scheduler.due_jobs()] == [JOB_FX]
    assert [job.name for job in scheduler.due_jobs(NOW + timedelta(minutes=1))] == []


def test_in_process_scheduler_weekday_field() -> None:
    # 2026-03-01 is a Sunday (weekday 6): the gate reminder runs Mon-Thu at 08:00.
    sunday_8 = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    monday_8 = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    friday_8 = datetime(2026, 3, 6, 8, 0, tzinfo=UTC)
    scheduler = InProcessScheduler(_registry(), FixedClock(sunday_8))
    assert JOB_GATE not in [job.name for job in scheduler.due_jobs()]
    assert JOB_GATE in [job.name for job in scheduler.due_jobs(monday_8)]
    assert JOB_GATE not in [job.name for job in scheduler.due_jobs(friday_8)]


def test_arq_cron_jobs_mirror_the_registry_including_max_tries() -> None:
    registry = build_registry(
        schedules=SCHEDULES, ports=_ports(), params=PARAMS, max_tries={JOB_FX: 3}
    )
    jobs = arq_cron_jobs(registry)
    assert [job.name for job in jobs] == [job.name for job in registry.all()]
    by_name = {job.name: job for job in jobs}
    assert by_name[JOB_FX].max_tries == 3
    assert by_name[JOB_AUDIT].max_tries == 1
    assert by_name[JOB_FX].hour == {6} and by_name[JOB_FX].minute == {0}
    assert by_name[JOB_FX].weekday is None
    assert by_name[JOB_GATE].weekday == {0, 1, 2, 3}


async def test_arq_cron_body_runs_the_job_with_the_context_clock() -> None:
    registry = _registry()
    fx_job = next(job for job in arq_cron_jobs(registry, clock=FixedClock(NOW)) if job.name == JOB_FX)
    assert isinstance(fx_job, CronJob)
    later = NOW + timedelta(hours=5)
    out = await fx_job.coroutine({CLOCK_CTX_KEY: FixedClock(later)})
    assert out["as_of"] == later.isoformat()


async def test_arq_cron_body_falls_back_to_the_captured_clock() -> None:
    registry = _registry()
    fx_job = next(job for job in arq_cron_jobs(registry, clock=FixedClock(NOW)) if job.name == JOB_FX)
    out = await fx_job.coroutine({})
    assert out["as_of"] == NOW.isoformat()


def test_build_worker_settings_shape() -> None:
    redis = RedisSettings(host="localhost", port=6379, database=0)
    settings = build_worker_settings(_registry(), redis_settings=redis, clock=FixedClock(NOW))
    assert settings["redis_settings"] is redis
    assert settings["functions"] == []
    assert len(settings["cron_jobs"]) == 5
    assert settings["ctx"][CLOCK_CTX_KEY].now() == NOW


def test_worker_settings_factory_binds_ports_without_side_effects() -> None:
    redis = RedisSettings()
    build = worker_settings_factory(
        schedules=SCHEDULES, ports=_ports(), params=PARAMS, redis_settings=redis
    )
    settings = build()
    assert [job.name for job in settings["cron_jobs"]] == [
        JOB_AUDIT,
        JOB_FINANCIALS,
        JOB_FX,
        JOB_GATE,
        JOB_SNAPSHOTS,
    ]
