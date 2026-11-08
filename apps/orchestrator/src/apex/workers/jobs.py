"""Scheduled job bodies (issue #58, step 2).

The five infrastructure jobs plus the supervisor tick are plain async functions that takes an injected ``Clock``, the ``WorkerPorts`` and its
parameters. None imports Arq: the adapter in ``arq_adapter.py`` wraps them. Jobs never read the wall
clock and never hardcode business numbers; thresholds are passed in from configuration.

Idempotent re-run: every job is safe to execute twice for the same scheduled slot. The FX ingest is
keyed by the instant of the slot; audit verification is read-only; reminders and refreshes are guarded
by their ports, which must be idempotent per ``now`` slot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apex.common.clock import Clock
from apex.workers.ports import WorkerPorts


@dataclass(frozen=True)
class JobParams:
    """Thresholds read from configuration by the caller. Required; there are no defaults here."""

    snapshot_max_age_days: int
    financials_stale_after_days: int


async def ingest_fx_rates(clock: Clock, ports: WorkerPorts) -> dict[str, Any]:
    """Daily FX ingestion (D3-03). The slot's instant is the ``as_of`` of the rates."""
    as_of = clock.now()
    result = await ports.fx.ingest_for(as_of)
    return {
        "job": "fx_ingestion",
        "as_of": result.as_of.isoformat(),
        "inserted": result.inserted,
        "already_present": result.already_present,
    }


async def verify_audit_chain(clock: Clock, ports: WorkerPorts) -> dict[str, Any]:
    """Re-verify the whole audit hash chain (D2-10). Read-only; the clock stamps the report."""
    result = await ports.audit.verify_chain()
    return {
        "job": "audit_chain_verify",
        "verified_at": clock.now().isoformat(),
        "chain_ok": result.chain_ok,
        "events_checked": result.events_checked,
        "first_broken_seq": result.first_broken_seq,
    }


async def send_gate_sla_reminders(clock: Clock, ports: WorkerPorts) -> dict[str, Any]:
    """Gate SLA reminders (D4-11). SLA maths uses the injected ``now``."""
    now = clock.now()
    result = await ports.gate.remind(now)
    return {
        "job": "gate_sla_reminders",
        "now": now.isoformat(),
        "reminders_sent": result.reminders_sent,
        "breached": result.breached,
    }


async def refresh_seller_snapshots(
    clock: Clock, ports: WorkerPorts, params: JobParams
) -> dict[str, Any]:
    """Recompute seller snapshots older than ``seller.snapshot_max_age_days`` (D4-10)."""
    now = clock.now()
    result = await ports.snapshots.refresh_older_than(now, params.snapshot_max_age_days)
    return {
        "job": "seller_snapshot_refresh",
        "now": now.isoformat(),
        "refreshed": result.refreshed,
    }


async def mark_stale_financials(
    clock: Clock, ports: WorkerPorts, params: JobParams
) -> dict[str, Any]:
    """Mark financial snapshots stale after ``finance.stale_after_days`` (D4-07)."""
    now = clock.now()
    result = await ports.financials.mark_stale(now, params.financials_stale_after_days)
    return {
        "job": "financials_stale_marking",
        "now": now.isoformat(),
        "marked_stale": result.marked_stale,
    }


async def supervise_missions(clock: Clock, ports: WorkerPorts) -> dict[str, Any]:
    """Run one SupervisorAgent tick (D4-13): stuck missions, token budget, escalation."""
    now = clock.now()
    report = await ports.supervisor.tick(now)
    actions: dict[str, int] = {}
    for assessment in report.assessments:
        for action in assessment.actions:
            actions[action.value] = actions.get(action.value, 0) + 1
    return {
        "job": "supervisor_tick",
        "checked_at": now.isoformat(),
        "missions_checked": len(report.assessments),
        "escalations": len(report.escalations),
        "actions": actions,
    }


__all__ = [
    "JobParams",
    "ingest_fx_rates",
    "mark_stale_financials",
    "refresh_seller_snapshots",
    "send_gate_sla_reminders",
    "supervise_missions",
    "verify_audit_chain",
]
