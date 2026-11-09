"""Mission records, their event log and the live event bus (D4-08, spec §8).

A mission is the durable handle for one sourcing run. Its state is a small, explicit machine; every change
appends an event with a monotonic ``seq`` per mission, which is what the SSE endpoint streams and what
``Last-Event-ID`` replays from. Events carry ids and counts, never credentials or financial values.

The store is a port: DEV-2's data layer (D2-05) replaces the in-memory one without touching callers.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from apex.agents.sourcing import SourcingPlan


class MissionStatus(StrEnum):
    """Lifecycle of a mission. ``PLANNED`` is where D4-09 (scraping) picks it up."""

    QUEUED = "queued"
    PLANNING = "planning"
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED}
)

ALLOWED_STATUS: dict[MissionStatus, frozenset[MissionStatus]] = {
    MissionStatus.QUEUED: frozenset(
        {MissionStatus.PLANNING, MissionStatus.FAILED, MissionStatus.CANCELLED}
    ),
    MissionStatus.PLANNING: frozenset(
        {MissionStatus.PLANNED, MissionStatus.FAILED, MissionStatus.CANCELLED}
    ),
    MissionStatus.PLANNED: frozenset(
        {MissionStatus.RUNNING, MissionStatus.FAILED, MissionStatus.CANCELLED}
    ),
    MissionStatus.RUNNING: frozenset(
        {MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED}
    ),
    MissionStatus.COMPLETED: frozenset(),
    MissionStatus.FAILED: frozenset(),
    MissionStatus.CANCELLED: frozenset(),
}


class InvalidMissionTransition(Exception):
    def __init__(self, source: MissionStatus, target: MissionStatus) -> None:
        super().__init__(f"mission status {source.value} -> {target.value} is not allowed")
        self.source = source
        self.target = target


def check_status(source: MissionStatus, target: MissionStatus) -> None:
    if target not in ALLOWED_STATUS[source]:
        raise InvalidMissionTransition(source, target)


class MissionEventType(StrEnum):
    """What the SSE stream can carry. One name per thing that actually happened."""

    MISSION_CREATED = "mission_created"
    PLANNING_STARTED = "planning_started"
    PLAN_READY = "plan_ready"
    SOURCING_STARTED = "sourcing_started"
    OFFERS_COLLECTED = "offers_collected"
    ANALYSIS_COMPLETED = "analysis_completed"
    MISSION_FAILED = "mission_failed"
    MISSION_CANCELLED = "mission_cancelled"


class MissionEvent(BaseModel):
    """One entry of a mission's log. ``seq`` is per mission, starting at 1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int = Field(ge=1)
    type: MissionEventType
    at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class Mission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    tenant_id: str
    sourcing_request_id: str
    quantity: int = Field(gt=0)
    """The quantity the mission searches for: the largest tier of its sourcing request, at least 1."""
    status: MissionStatus
    config_version: str
    created_at: datetime
    updated_at: datetime
    plan: SourcingPlan | None = None
    failure_reason: str | None = None
    events: list[MissionEvent] = Field(default_factory=list)

    @property
    def last_seq(self) -> int:
        return self.events[-1].seq if self.events else 0


class MissionNotFound(Exception):
    def __init__(self, mission_id: str) -> None:
        super().__init__(f"mission {mission_id} not found")
        self.mission_id = mission_id


class MissionStore(Protocol):
    """Durable mission storage. Tenant-scoped: implementations must apply RLS (D2-04)."""

    async def create(self, mission: Mission) -> Mission: ...

    async def get(self, tenant_id: str, mission_id: str) -> Mission | None: ...

    async def save(self, mission: Mission) -> Mission: ...


class InMemoryMissionStore:
    """Process-local store for tests and local runs. Keyed by ``(tenant_id, mission_id)``."""

    def __init__(self) -> None:
        self._missions: dict[tuple[str, str], Mission] = {}
        self._lock = asyncio.Lock()

    async def create(self, mission: Mission) -> Mission:
        async with self._lock:
            key = (mission.tenant_id, mission.id)
            if key in self._missions:
                raise ValueError(
                    f"mission {mission.id} already exists for tenant {mission.tenant_id}"
                )
            self._missions[key] = mission
            return mission

    async def get(self, tenant_id: str, mission_id: str) -> Mission | None:
        return self._missions.get((tenant_id, mission_id))

    async def save(self, mission: Mission) -> Mission:
        async with self._lock:
            self._missions[(mission.tenant_id, mission.id)] = mission
            return mission


class MissionEventBus:
    """Fan-out of mission events to live SSE subscribers.

    Publishing is fire-and-forget: a slow or vanished subscriber must never block a mission. Subscribers get
    a bounded queue and are dropped (with a ``None`` sentinel) when they fall too far behind.
    """

    def __init__(self, *, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._subscribers: dict[str, set[asyncio.Queue[MissionEvent | None]]] = {}

    def subscribe(self, mission_id: str) -> asyncio.Queue[MissionEvent | None]:
        queue: asyncio.Queue[MissionEvent | None] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.setdefault(mission_id, set()).add(queue)
        return queue

    def unsubscribe(self, mission_id: str, queue: asyncio.Queue[MissionEvent | None]) -> None:
        subscribers = self._subscribers.get(mission_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(mission_id, None)

    def publish(self, mission_id: str, event: MissionEvent) -> None:
        for queue in list(self._subscribers.get(mission_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the slow subscriber. Make room for the sentinel so its stream ends instead of
                # hanging: the client reconnects with Last-Event-ID and resumes without a gap.
                self.unsubscribe(mission_id, queue)
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with suppress(asyncio.QueueFull):
                    queue.put_nowait(None)

    def subscriber_count(self, mission_id: str) -> int:
        return len(self._subscribers.get(mission_id, ()))

    async def stream(
        self, mission_id: str, *, after_seq: int = 0, idle_timeout_s: float | None = None
    ) -> AsyncIterator[MissionEvent | None]:
        """Yield events for ``mission_id`` with ``seq > after_seq``. ``None`` marks the end of the stream."""
        queue = self.subscribe(mission_id)
        try:
            while True:
                try:
                    item = (
                        await asyncio.wait_for(queue.get(), timeout=idle_timeout_s)
                        if idle_timeout_s is not None
                        else await queue.get()
                    )
                except TimeoutError:
                    yield None
                    return
                if item is None:
                    yield None
                    return
                if item.seq > after_seq:
                    yield item
        finally:
            self.unsubscribe(mission_id, queue)


def apply_event(
    mission: Mission,
    event_type: MissionEventType,
    *,
    at: datetime,
    payload: Mapping[str, Any] | None = None,
) -> Mission:
    """Append an event to a mission (pure: returns a new instance)."""
    event = MissionEvent(
        seq=mission.last_seq + 1, type=event_type, at=at, payload=dict(payload or {})
    )
    return mission.model_copy(update={"events": [*mission.events, event], "updated_at": at})


def transition(mission: Mission, target: MissionStatus, *, at: datetime) -> Mission:
    """Move a mission to ``target``, validating the edge. Pure."""
    check_status(mission.status, target)
    return mission.model_copy(update={"status": target, "updated_at": at})


__all__ = [
    "ALLOWED_STATUS",
    "InvalidMissionTransition",
    "InMemoryMissionStore",
    "Mission",
    "MissionEvent",
    "MissionEventBus",
    "MissionEventType",
    "MissionNotFound",
    "MissionStatus",
    "MissionStore",
    "TERMINAL_STATUSES",
    "apply_event",
    "check_status",
    "transition",
]
