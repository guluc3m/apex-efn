"""Mission records, status machine, event log, SSE bus and the SourcingService use cases (D4-08)."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from apex.agents.missions import (
    ALLOWED_STATUS,
    InMemoryMissionStore,
    InvalidMissionTransition,
    Mission,
    MissionEventBus,
    MissionEventType,
    MissionStatus,
    apply_event,
    check_status,
    transition,
)
from apex.agents.sourcing import NoViablePlatform, PlanStep, SourcingPlan, SourcingRequest
from apex.agents.sourcing_service import (
    MissionMissing,
    SourcingService,
    SourcingServiceDeps,
)
from apex.common.clock import FixedClock
from apex.common.ids import IdGenerator
from apex.llm.structured import StructuredOutputError

NOW = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
TENANT = "tenant-a"


def _mission(**overrides: Any) -> Mission:
    base: dict[str, Any] = {
        "id": "m-1",
        "tenant_id": TENANT,
        "sourcing_request_id": "sr-1",
        "quantity": 100,
        "status": MissionStatus.QUEUED,
        "config_version": "v7",
        "created_at": NOW,
        "updated_at": NOW,
    }
    return Mission(**{**base, **overrides})


def _request() -> SourcingRequest:
    return SourcingRequest(
        id="sr-1",
        tenant_id=TENANT,
        spec="Botellas PET 500ml",
        quantity_tiers=[],
        deadline=None,
        deadline_text=None,
        destination_country="ES",
        certifications=[],
        budget_text=None,
        missing_fields=[],
        created_at=NOW,
        config_version="v7",
    )


def _plan() -> SourcingPlan:
    return SourcingPlan(
        steps=[PlanStep(platform_id="mock-a", transport="http", query="PET")],
        rationale="only mock-a",
        config_version="v7",
    )


# ----- status machine ----------------------------------------------------------------------------


def test_status_table_is_total_and_terminal_states_are_final() -> None:
    assert set(ALLOWED_STATUS) == set(MissionStatus)
    for terminal in (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED):
        assert ALLOWED_STATUS[terminal] == frozenset()


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (MissionStatus.QUEUED, MissionStatus.PLANNED),
        (MissionStatus.QUEUED, MissionStatus.RUNNING),
        (MissionStatus.PLANNING, MissionStatus.RUNNING),
        (MissionStatus.PLANNED, MissionStatus.PLANNING),
        (MissionStatus.COMPLETED, MissionStatus.RUNNING),
        (MissionStatus.FAILED, MissionStatus.PLANNED),
    ],
)
def test_skipping_or_reopening_a_mission_is_refused(
    source: MissionStatus, target: MissionStatus
) -> None:
    with pytest.raises(InvalidMissionTransition):
        check_status(source, target)


def test_transition_and_apply_event_are_pure_and_monotonic() -> None:
    mission = _mission()
    moved = transition(mission, MissionStatus.PLANNING, at=NOW)
    assert mission.status is MissionStatus.QUEUED  # original untouched
    assert moved.status is MissionStatus.PLANNING
    first = apply_event(moved, MissionEventType.PLANNING_STARTED, at=NOW)
    second = apply_event(first, MissionEventType.MISSION_FAILED, at=NOW + timedelta(seconds=1))
    assert [e.seq for e in second.events] == [1, 2]
    assert first.events == [second.events[0]]  # no shared mutable list


# ----- store ---------------------------------------------------------------------------------------


async def test_store_is_tenant_scoped_and_rejects_duplicates() -> None:
    store = InMemoryMissionStore()
    await store.create(_mission())
    assert await store.get(TENANT, "m-1") is not None
    assert await store.get("tenant-b", "m-1") is None, "another tenant must not see the mission"
    with pytest.raises(ValueError, match="already exists"):
        await store.create(_mission())


# ----- event bus -----------------------------------------------------------------------------------


async def test_bus_delivers_events_after_a_sequence_number() -> None:
    bus = MissionEventBus()
    mission = apply_event(_mission(), MissionEventType.MISSION_CREATED, at=NOW)
    mission = apply_event(mission, MissionEventType.PLANNING_STARTED, at=NOW)

    async def consume() -> list[int]:
        seen: list[int] = []
        async for item in bus.stream("m-1", after_seq=1, idle_timeout_s=1.0):
            if item is None:
                break
            seen.append(item.seq)
            if len(seen) == 1:
                break
        return seen

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    bus.publish("m-1", mission.events[1])
    assert await asyncio.wait_for(task, 2.0) == [2]


async def test_a_slow_subscriber_is_dropped_and_told_to_resume_from_last_event_id() -> None:
    """A dropped subscriber must not hang: the bus makes room for the end-of-stream sentinel."""
    bus = MissionEventBus(queue_size=1)
    queue = bus.subscribe("m-1")
    bus.publish("m-1", _event(1))
    bus.publish("m-1", _event(2))  # queue full: the subscriber is dropped
    assert bus.subscriber_count("m-1") == 0
    assert queue.get_nowait() is None  # stream ends; the client reconnects with Last-Event-ID


async def test_publishing_without_subscribers_is_a_no_op() -> None:
    MissionEventBus().publish("nobody", _event(1))


def _event(seq: int) -> Any:
    from apex.agents.missions import MissionEvent

    return MissionEvent(seq=seq, type=MissionEventType.PLANNING_STARTED, at=NOW)


# ----- SourcingService -----------------------------------------------------------------------------


class _Intake:
    def __init__(self, request: SourcingRequest) -> None:
        self.request = request
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> SourcingRequest:
        self.calls.append(kwargs)
        return self.request


class _Planner:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome

    async def plan(self, **_: Any) -> SourcingPlan:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _service(*, planner_outcome: Any = None, request: SourcingRequest | None = None) -> Any:
    store = InMemoryMissionStore()
    bus = MissionEventBus()
    clock = FixedClock(NOW)
    deps = SourcingServiceDeps(
        intake=_Intake(request or _request()),
        planner=_Planner(planner_outcome if planner_outcome is not None else _plan()),
        store=store,
        bus=bus,
        clock=clock,
        ids=IdGenerator(clock, random_bits=lambda n: 7),
        config_version=lambda tenant_id: "v7",
    )
    return SourcingService(deps), store, bus


async def test_create_mission_plans_inline_and_records_the_events() -> None:
    service, store, _ = _service()
    mission = await service.create_mission(tenant_id=TENANT, request=_request())
    assert mission.status is MissionStatus.PLANNED
    assert mission.plan is not None and mission.plan.steps[0].platform_id == "mock-a"
    assert [e.type for e in mission.events] == [
        MissionEventType.MISSION_CREATED,
        MissionEventType.PLANNING_STARTED,
        MissionEventType.PLAN_READY,
    ]
    assert [e.seq for e in mission.events] == [1, 2, 3]
    assert mission.config_version == "v7"
    assert await store.get(TENANT, mission.id) is not None


async def test_plan_ready_event_reports_counts_and_rejections_not_the_model_text() -> None:
    service, _, _ = _service()
    mission = await service.create_mission(tenant_id=TENANT, request=_request())
    payload = mission.events[-1].payload
    assert payload["steps"] == 1 and payload["platforms"] == ["mock-a"]
    assert "rationale" not in payload


async def test_a_planner_failure_marks_the_mission_failed_with_a_reason() -> None:
    service, store, _ = _service(planner_outcome=NoViablePlatform("no platform is enabled"))
    mission = await service.create_mission(tenant_id=TENANT, request=_request())
    assert mission.status is MissionStatus.FAILED
    assert mission.failure_reason is not None and "no_viable_platform" in mission.failure_reason
    assert mission.events[-1].type is MissionEventType.MISSION_FAILED
    assert (await store.get(TENANT, mission.id)).status is MissionStatus.FAILED  # type: ignore[union-attr]


async def test_invalid_model_output_fails_the_mission_without_leaking_the_error() -> None:
    service, _, _ = _service(planner_outcome=StructuredOutputError("boom", []))
    mission = await service.create_mission(tenant_id=TENANT, request=_request())
    assert mission.failure_reason == "planner_output_invalid"


async def test_get_mission_is_tenant_scoped() -> None:
    service, _, _ = _service()
    mission = await service.create_mission(tenant_id=TENANT, request=_request())
    with pytest.raises(MissionMissing):
        await service.get_mission(tenant_id="tenant-b", mission_id=mission.id)


async def test_create_request_uses_the_injected_clock_and_config_version() -> None:
    service, _, _ = _service()
    request = await service.create_request(
        tenant_id=TENANT, text="botellas", base_currency="EUR", today=date(2026, 11, 9)
    )
    assert request.config_version == "v7"
    assert request.created_at == NOW


async def test_build_request_takes_clock_and_config_version_from_the_service() -> None:
    service, _, _ = _service()
    request = service.build_request(
        tenant_id=TENANT,
        request_id="sr-9",
        spec="sillas",
        quantity_tiers=[],
        deadline=None,
        destination_country=None,
        certifications=[],
        budget_text=None,
    )
    assert request.created_at == NOW and request.config_version == "v7"
