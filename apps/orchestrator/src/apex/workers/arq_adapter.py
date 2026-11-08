"""Arq backend for the ``JobRegistry`` (ADR-401). The only module in the codebase that imports ``arq``.

``build_worker_settings`` turns the registry into Arq ``cron_jobs``. Each job body is run with the clock
from the Arq context (``SystemClock`` in production when absent); the job bodies themselves stay
unchanged and Arq-free.

The process entry point is the module attribute ``WorkerSettings``
(``arq apex.workers.arq_adapter.WorkerSettings``), resolved lazily from configuration. Until those
lanes land it fails loudly instead of inventing schedules or credentials; ``worker_settings_factory``
is the injectable path used by tests and by the wiring PR.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob

from apex.common.clock import Clock, SystemClock
from apex.workers.jobs import JobParams
from apex.workers.ports import WorkerPorts
from apex.workers.registry import WorkerSchedules, build_registry
from apex.workers.scheduler import CronSpec, JobDefinition, JobRegistry

#: Context key under which the injected clock travels through the Arq worker.
CLOCK_CTX_KEY = "clock"


def _as_arq(values: frozenset[int] | None) -> set[int] | None:
    return None if values is None else set(values)


def _to_arq_cron(job: JobDefinition, clock: Clock) -> CronJob:
    """Map one ``JobDefinition`` onto ``arq.cron``. ``None`` fields mean "any" for Arq too.

    The job body receives the clock from the worker context when present (tests and replays inject a
    ``FixedClock`` there), otherwise the clock captured here (``SystemClock`` in production).
    """

    async def _run(ctx: dict[str, Any]) -> dict[str, Any]:
        injected: Clock = ctx.get(CLOCK_CTX_KEY) or clock
        result: dict[str, Any] = await job.func(injected)
        return result

    _run.__name__ = job.name
    spec: CronSpec = job.schedule
    return cron(
        _run,
        name=job.name,
        minute=_as_arq(spec.minute),
        hour=_as_arq(spec.hour),
        weekday=_as_arq(spec.weekday),
        day=_as_arq(spec.day),
        month=_as_arq(spec.month),
        unique=True,
        max_tries=job.max_tries,
    )


def arq_cron_jobs(registry: JobRegistry, *, clock: Clock | None = None) -> list[CronJob]:
    """All registry jobs as Arq cron jobs, sorted by name for a stable worker configuration."""
    effective: Clock = clock or SystemClock()
    return [_to_arq_cron(job, effective) for job in registry.all()]


def build_worker_settings(
    registry: JobRegistry, *, redis_settings: Any, clock: Clock | None = None
) -> dict[str, Any]:
    """Return the keyword mapping an ``arq`` worker class expects.

    Returned as a plain dict so tests can inspect it without starting a worker, and so the process
    entry point can build ``WorkerSettings`` from it.
    """
    return {
        "functions": [],
        "cron_jobs": arq_cron_jobs(registry, clock=clock),
        "redis_settings": redis_settings,
        "ctx": {CLOCK_CTX_KEY: clock or SystemClock()},
        "on_startup": _noop_startup,
        "on_shutdown": _noop_shutdown,
    }


async def _noop_startup(ctx: dict[str, Any]) -> None:
    """Placeholder for telemetry/DB pool startup (D1-07, D2-05)."""


async def _noop_shutdown(ctx: dict[str, Any]) -> None:
    """Placeholder for telemetry/DB pool shutdown (D1-07, D2-05)."""


def worker_settings_factory(
    *,
    schedules: WorkerSchedules,
    ports: WorkerPorts,
    params: JobParams,
    redis_settings: RedisSettings,
    clock: Clock | None = None,
) -> Callable[[], dict[str, Any]]:
    """Bind the registry to concrete schedules/ports and return the Arq settings mapping factory."""

    def _build() -> dict[str, Any]:
        registry = build_registry(schedules=schedules, ports=ports, params=params)
        return build_worker_settings(registry, redis_settings=redis_settings, clock=clock)

    return _build


def _wired_settings() -> dict[str, Any]:
    """Build the Arq settings from the process environment.

    Placeholder until D4-03 (tenant config: schedules and thresholds) and D1-06 (Redis settings)
    land. It fails loudly instead of inventing schedules, thresholds or Redis credentials.
    """
    raise NotImplementedError(
        "WorkerSettings needs schedules and thresholds (D4-03) and Redis settings (D1-06); "
        "use worker_settings_factory() until those lanes are wired"
    )


def __getattr__(name: str) -> Any:
    """PEP 562: resolve ``WorkerSettings`` lazily.

    ``arq apex.workers.arq_adapter.WorkerSettings`` reads the module attribute, so it must exist, but
    importing this module (in tests, tooling or the API process) must not build a worker configuration.
    """
    if name == "WorkerSettings":
        return _wired_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CLOCK_CTX_KEY",
    "arq_cron_jobs",
    "build_worker_settings",
    "worker_settings_factory",
]

if TYPE_CHECKING:  # pragma: no cover - documents the lazily provided entry point
    WorkerSettings: dict[str, Any]
