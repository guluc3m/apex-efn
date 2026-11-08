"""Swappable scheduling seam: schedule specs, the job registry and the ``Scheduler`` protocol.

Only this module and the job bodies are backend-neutral. ``arq_adapter.py`` is the single place that
knows Arq (ADR-401). Field order is the standard five-field cron order ``minute hour day month weekday``
(``weekday`` last, Monday = 0 as in ``arq.cron``). A field is either ``*`` (any) or a set of integers in
range. Cron-only on purpose: it is the one shape Arq supports natively, and every scheduled job here is
calendar-based.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from apex.common.clock import Clock

# (min, max) inclusive per cron field.
_FIELD_RANGES: Mapping[str, tuple[int, int]] = {
    "minute": (0, 59),
    "hour": (0, 23),
    "weekday": (0, 6),  # Monday = 0, as in arq.cron
    "day": (1, 31),
    "month": (1, 12),
}

JobCallable = Callable[..., Awaitable[dict[str, Any]]]


class ScheduleError(ValueError):
    """Invalid schedule specification (raised at configuration load, never at run time)."""


@dataclass(frozen=True)
class CronSpec:
    """Calendar schedule. ``None`` on a field means "every value" for that field."""

    minute: frozenset[int] | None = None
    hour: frozenset[int] | None = None
    weekday: frozenset[int] | None = None
    day: frozenset[int] | None = None
    month: frozenset[int] | None = None

    def __post_init__(self) -> None:
        for name, (low, high) in _FIELD_RANGES.items():
            values: frozenset[int] | None = getattr(self, name)
            if values is None:
                continue
            if not values:
                raise ScheduleError(f"cron field {name!r} must not be empty")
            bad = sorted(v for v in values if not low <= v <= high)
            if bad:
                raise ScheduleError(f"cron field {name!r} out of range [{low},{high}]: {bad}")

    @classmethod
    def parse(cls, expression: str) -> CronSpec:
        """Parse a five-field expression ``minute hour day month weekday``.

        ``*`` means any; otherwise comma-separated integers, e.g. ``"0 6 * * *"`` or ``"30 2 * * 1,3"``
        (02:30 on Mondays and Wednesdays).
        Ranges and steps are deliberately not supported: keep schedules auditable.
        """
        parts = expression.split()
        if len(parts) != 5:
            raise ScheduleError(f"expected 5 cron fields, got {len(parts)}: {expression!r}")
        names = ("minute", "hour", "day", "month", "weekday")
        parsed: dict[str, frozenset[int] | None] = {}
        for name, token in zip(names, parts, strict=True):
            if token == "*":
                parsed[name] = None
                continue
            try:
                parsed[name] = frozenset(int(v) for v in token.split(","))
            except ValueError as exc:
                raise ScheduleError(f"invalid cron field {name!r}: {token!r}") from exc
        return cls(**parsed)

    def matches(self, at: datetime) -> bool:
        """Does ``at`` (UTC) fall on this schedule's minute? Used by in-process schedulers and tests."""
        moment = at.astimezone(UTC)
        checks: list[tuple[frozenset[int] | None, int]] = [
            (self.minute, moment.minute),
            (self.hour, moment.hour),
            (self.weekday, moment.weekday()),
            (self.day, moment.day),
            (self.month, moment.month),
        ]
        return all(allowed is None or value in allowed for allowed, value in checks)

    def next_after(self, after: datetime, *, horizon_days: int = 366) -> datetime:
        """First matching minute strictly after ``after``. Raises if none within the horizon."""
        candidate = after.astimezone(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = candidate + timedelta(days=horizon_days)
        while candidate <= limit:
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise ScheduleError("no matching slot within the horizon")


@dataclass(frozen=True)
class JobDefinition:
    """A named job, its schedule and the callable. The callable takes the injected clock first."""

    name: str
    schedule: CronSpec
    func: JobCallable
    max_tries: int = 1

    def __post_init__(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ScheduleError(f"job name must be snake_case alphanumeric: {self.name!r}")
        if self.max_tries < 1:
            raise ScheduleError("max_tries must be >= 1")


class JobRegistry:
    """Holds job definitions by name. Duplicate names are a configuration error."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobDefinition] = {}

    def register(self, job: JobDefinition) -> None:
        if job.name in self._jobs:
            raise ScheduleError(f"job already registered: {job.name!r}")
        self._jobs[job.name] = job

    def get(self, name: str) -> JobDefinition:
        try:
            return self._jobs[name]
        except KeyError as exc:
            raise ScheduleError(f"unknown job: {name!r}") from exc

    def all(self) -> list[JobDefinition]:
        return sorted(self._jobs.values(), key=lambda j: j.name)

    def __len__(self) -> int:
        return len(self._jobs)


class Scheduler(Protocol):
    """Backend seam. Implementations: ``arq_adapter`` (production), ``InProcessScheduler`` (tests, dev)."""

    def due_jobs(self, now: datetime) -> list[JobDefinition]: ...


class InProcessScheduler:
    """Computes which jobs are due at an injected instant. No sleeping, no background loop."""

    def __init__(self, registry: JobRegistry, clock: Clock) -> None:
        self._registry = registry
        self._clock = clock

    def due_jobs(self, now: datetime | None = None) -> list[JobDefinition]:
        at = (now or self._clock.now()).astimezone(UTC).replace(second=0, microsecond=0)
        return [job for job in self._registry.all() if job.schedule.matches(at)]


def slot_key(job_name: str, scheduled_for: datetime) -> str:
    """Deterministic job id for a scheduled slot. Duplicate enqueues from replicas collapse to one."""
    stamp = scheduled_for.astimezone(UTC).strftime("%Y%m%dT%H%M")
    return f"{job_name}:{stamp}"


__all__ = [
    "CronSpec",
    "InProcessScheduler",
    "JobDefinition",
    "JobRegistry",
    "ScheduleError",
    "Scheduler",
    "slot_key",
]
