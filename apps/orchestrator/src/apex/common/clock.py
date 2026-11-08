"""Injectable clock (AGENTS.md section 4, DEV-4 -> all).

Deterministic code never calls ``datetime.now()`` directly: it receives a ``Clock`` (or a ``now``
value) as a parameter. Production wires ``SystemClock``; tests wire ``FixedClock`` and move time
explicitly, with no sleeps.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


def _require_aware_utc(at: datetime) -> datetime:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("Clock values must be timezone-aware")
    return at.astimezone(UTC)


@runtime_checkable
class Clock(Protocol):
    """Source of the current instant. Always returns a timezone-aware UTC datetime."""

    def now(self) -> datetime: ...


class SystemClock:
    """Wall clock. The only place in the codebase allowed to read real time."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Manually driven clock for tests and deterministic replays."""

    def __init__(self, at: datetime) -> None:
        self._at = _require_aware_utc(at)

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = _require_aware_utc(at)

    def advance(self, delta: timedelta) -> datetime:
        if delta < timedelta(0):
            raise ValueError("FixedClock cannot move backwards via advance(); use set()")
        self._at = self._at + delta
        return self._at


_default_clock: Clock = SystemClock()


def get_clock() -> Clock:
    """FastAPI dependency. Override with ``app.dependency_overrides[get_clock]`` in tests."""
    return _default_clock


__all__ = ["Clock", "FixedClock", "SystemClock", "get_clock"]
