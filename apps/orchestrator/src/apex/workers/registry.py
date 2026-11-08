"""Wires the scheduled jobs into a ``JobRegistry`` from configuration.

Schedules are configuration (``WorkerSchedules``): each job's cron expression is a field that
operations can change without a deploy. The model has no default cron expressions, so a deployment
must state when each job runs. Business thresholds (``JobParams``) are required too.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from pydantic import BaseModel, ConfigDict

from apex.workers.jobs import (
    JobParams,
    ingest_fx_rates,
    mark_stale_financials,
    refresh_seller_snapshots,
    send_gate_sla_reminders,
    supervise_missions,
    verify_audit_chain,
)
from apex.workers.ports import WorkerPorts
from apex.workers.scheduler import CronSpec, JobCallable, JobDefinition, JobRegistry

JOB_FX = "fx_ingestion"
JOB_AUDIT = "audit_chain_verify"
JOB_GATE = "gate_sla_reminders"
JOB_SNAPSHOTS = "seller_snapshot_refresh"
JOB_FINANCIALS = "financials_stale_marking"
JOB_SUPERVISOR = "supervisor_tick"


class WorkerSchedules(BaseModel):
    """Cron expressions per job (``minute hour weekday day month``). Required, no defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fx_ingestion: str
    audit_chain_verify: str
    gate_sla_reminders: str
    seller_snapshot_refresh: str
    financials_stale_marking: str
    supervisor_tick: str


def build_registry(
    *,
    schedules: WorkerSchedules,
    ports: WorkerPorts,
    params: JobParams,
    max_tries: Mapping[str, int] | None = None,
) -> JobRegistry:
    """Create a registry with every scheduled job. ``max_tries`` may override the default of 1 per job.

    The clock is not bound here: the scheduler adapter injects it at run time, so the same registry
    works under ``SystemClock`` in production and ``FixedClock`` in tests.
    """
    overrides = dict(max_tries or {})
    entries: list[tuple[str, str, JobCallable]] = [
        (
            JOB_FX,
            schedules.fx_ingestion,
            partial(ingest_fx_rates, ports=ports, schedule=CronSpec.parse(schedules.fx_ingestion)),
        ),
        (JOB_AUDIT, schedules.audit_chain_verify, partial(verify_audit_chain, ports=ports)),
        (JOB_GATE, schedules.gate_sla_reminders, partial(send_gate_sla_reminders, ports=ports)),
        (
            JOB_SNAPSHOTS,
            schedules.seller_snapshot_refresh,
            partial(refresh_seller_snapshots, ports=ports, params=params),
        ),
        (
            JOB_FINANCIALS,
            schedules.financials_stale_marking,
            partial(mark_stale_financials, ports=ports, params=params),
        ),
        (JOB_SUPERVISOR, schedules.supervisor_tick, partial(supervise_missions, ports=ports)),
    ]
    registry = JobRegistry()
    for name, expression, func in entries:
        registry.register(
            JobDefinition(
                name=name,
                schedule=CronSpec.parse(expression),
                func=func,
                max_tries=overrides.get(name, 1),
            )
        )
    return registry


__all__ = [
    "JOB_AUDIT",
    "JOB_FINANCIALS",
    "JOB_FX",
    "JOB_GATE",
    "JOB_SNAPSHOTS",
    "JOB_SUPERVISOR",
    "WorkerSchedules",
    "build_registry",
]
