"""HTTP surface for D4-08: sourcing requests, missions and the SSE stream."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.agents.missions import InMemoryMissionStore, MissionEventBus, MissionStatus
from apex.agents.sourcing import NoViablePlatform, PlanStep, SourcingPlan, SourcingRequest
from apex.agents.sourcing_service import SourcingService, SourcingServiceDeps
from apex.api import missions as missions_api
from apex.api import sourcing as sourcing_api
from apex.common.clock import FixedClock
from apex.common.errors import install_problem_handlers
from apex.common.ids import IdGenerator

NOW = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
TENANT = "tenant-a"


class _Intake:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> SourcingRequest:
        self.calls.append(kwargs)
        return SourcingRequest(
            id="sr-1",
            tenant_id=kwargs["tenant_id"],
            spec="Botellas PET 500ml",
            quantity_tiers=[],
            deadline=date(2027, 6, 1),
            deadline_text=None,
            destination_country="ES",
            certifications=["food grade"],
            budget_text="4500 EUR",
            missing_fields=["quantity_tiers"],
            created_at=NOW,
            config_version="v7",
        )


class _Planner:
    def __init__(self, outcome: Any = None) -> None:
        self.outcome = outcome

    async def plan(self, **_: Any) -> SourcingPlan:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return SourcingPlan(
            steps=[PlanStep(platform_id="mock-a", transport="http", query="PET")],
            rationale="only mock-a",
            config_version="v7",
        )


@pytest.fixture(autouse=True)
def _tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")


@pytest.fixture
def app() -> Iterator[FastAPI]:
    clock = FixedClock(NOW)
    store = InMemoryMissionStore()
    bus = MissionEventBus()
    service = SourcingService(
        SourcingServiceDeps(
            intake=_Intake(),
            planner=_Planner(),
            store=store,
            bus=bus,
            clock=clock,
            ids=IdGenerator(clock, random_bits=lambda n: 11),
            config_version=lambda tenant_id: "v7",
        )
    )
    application = FastAPI()
    install_problem_handlers(application)
    application.state.mission_event_bus = bus
    application.include_router(sourcing_api.router, prefix="/sourcing-requests")
    application.include_router(missions_api.router, prefix="/missions")
    application.dependency_overrides[sourcing_api.get_sourcing_service] = lambda: service
    application.dependency_overrides[missions_api.get_sourcing_service] = lambda: service
    yield application


def _h(tenant: str = TENANT) -> dict[str, str]:
    return {"X-Tenant-Id": tenant}


# ----- POST /sourcing-requests -------------------------------------------------------------------


def test_create_sourcing_request_returns_the_normalised_request(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/sourcing-requests",
            json={"text": "Necesito botellas", "base_currency": "EUR"},
            headers=_h(),
        )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "sr-1" and body["tenant_id"] == TENANT
    assert body["spec"] == "Botellas PET 500ml"
    assert body["deadline"] == "2027-06-01"
    assert body["missing_fields"] == ["quantity_tiers"]
    assert body["config_version"] == "v7"


def test_create_sourcing_request_rejects_an_empty_text(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post("/sourcing-requests", json={"text": ""}, headers=_h())
    assert response.status_code == 422


def test_sourcing_needs_a_tenant(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_ALLOW_TENANT_HEADER", raising=False)
    with TestClient(app) as client:
        assert client.post("/sourcing-requests", json={"text": "x"}).status_code == 401
        assert (
            client.post("/sourcing-requests", json={"text": "x"}, headers=_h()).status_code == 401
        )


# ----- POST /missions ----------------------------------------------------------------------------


def _mission_body() -> dict[str, Any]:
    return {
        "sourcing_request_id": "sr-1",
        "spec": "Botellas PET 500ml",
        "quantity_tiers": [5000],
        "deadline": "2027-06-01",
        "destination_country": "ES",
        "certifications": ["food grade"],
        "budget_text": "4500 EUR",
    }


def test_create_mission_plans_it_and_returns_the_steps(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post("/missions", json=_mission_body(), headers=_h())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "planned"
    assert body["steps"] == [
        {"platform_id": "mock-a", "transport": "http", "query": "PET", "tier_index": None}
    ]
    assert body["rejected_steps"] == []
    assert body["config_version"] == "v7"


def test_create_mission_rejects_an_invalid_deadline(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/missions", json={**_mission_body(), "deadline": "next june"}, headers=_h()
        )
    assert response.status_code == 422
    assert response.json()["status"] == 422


def test_a_planner_failure_returns_a_failed_mission_not_a_500(app: FastAPI) -> None:
    failing = SourcingService(
        SourcingServiceDeps(
            intake=_Intake(),
            planner=_Planner(NoViablePlatform("no platform is enabled")),
            store=InMemoryMissionStore(),
            bus=MissionEventBus(),
            clock=FixedClock(NOW),
            ids=IdGenerator(FixedClock(NOW), random_bits=lambda n: 13),
            config_version=lambda tenant_id: "v7",
        )
    )
    app.dependency_overrides[missions_api.get_sourcing_service] = lambda: failing
    with TestClient(app) as client:
        response = client.post("/missions", json=_mission_body(), headers=_h())
    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert "no_viable_platform" in response.json()["failure_reason"]


# ----- GET /missions/{id} ------------------------------------------------------------------------


def test_get_mission_returns_404_for_another_tenant(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = client.post("/missions", json=_mission_body(), headers=_h()).json()
        assert client.get(f"/missions/{created['id']}", headers=_h()).status_code == 200
        other = client.get(f"/missions/{created['id']}", headers=_h("tenant-b"))
    assert other.status_code == 404
    assert other.headers["content-type"].startswith("application/problem+json")


# ----- GET /missions/{id}/events (SSE) ------------------------------------------------------------


def test_sse_replays_the_mission_log(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = client.post("/missions", json=_mission_body(), headers=_h()).json()
        with client.stream("GET", f"/missions/{created['id']}/events", headers=_h()) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())
    events = _parse_sse(body)
    assert [e["id"] for e in events] == ["1", "2", "3"]
    assert [e["event"] for e in events] == ["mission_created", "planning_started", "plan_ready"]
    payload = json.loads(events[-1]["data"])
    assert payload["payload"]["platforms"] == ["mock-a"]


def test_sse_last_event_id_skips_what_the_client_already_has(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = client.post("/missions", json=_mission_body(), headers=_h()).json()
        with client.stream(
            "GET",
            f"/missions/{created['id']}/events",
            headers={**_h(), "Last-Event-ID": "2"},
        ) as response:
            body = "".join(response.iter_text())
    assert [e["id"] for e in _parse_sse(body)] == ["3"]


def test_sse_rejects_a_malformed_last_event_id(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = client.post("/missions", json=_mission_body(), headers=_h()).json()
        response = client.get(
            f"/missions/{created['id']}/events", headers={**_h(), "Last-Event-ID": "abc"}
        )
    assert response.status_code == 400


def test_sse_404s_before_streaming_for_an_unknown_mission(app: FastAPI) -> None:
    with TestClient(app) as client:
        assert client.get("/missions/nope/events", headers=_h()).status_code == 404


async def test_the_stream_follows_the_bus_while_a_mission_is_running() -> None:
    """The live path: after the replay, new events reach the subscriber until the mission ends."""
    import asyncio

    from apex.agents.missions import MissionEventType, MissionStatus, apply_event
    from apex.api.missions import _stream

    bus = MissionEventBus()
    mission = _mission(status=MissionStatus.RUNNING)
    mission = apply_event(mission, MissionEventType.MISSION_CREATED, at=NOW)

    async def consume() -> list[int]:
        seen: list[int] = []
        async for chunk in _stream(mission, bus, after_seq=0):
            if chunk.startswith(b"id: "):
                seen.append(int(chunk.split(b"\n")[0].removeprefix(b"id: ")))
            if len(seen) == 2:
                break
        return seen

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    bus.publish(
        mission.id, apply_event(mission, MissionEventType.PLANNING_STARTED, at=NOW).events[-1]
    )
    assert await asyncio.wait_for(task, 2.0) == [1, 2]


def test_a_finished_mission_stream_ends_immediately(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = client.post("/missions", json=_mission_body(), headers=_h()).json()
        assert created["status"] == MissionStatus.PLANNED.value
        with client.stream("GET", f"/missions/{created['id']}/events", headers=_h()) as response:
            body = "".join(response.iter_text())
    assert len(_parse_sse(body)) == 3  # replay only, no hang


def _mission(**overrides: Any) -> Any:
    from apex.agents.missions import Mission

    base: dict[str, Any] = {
        "id": "m-1",
        "tenant_id": TENANT,
        "sourcing_request_id": "sr-1",
        "status": MissionStatus.QUEUED,
        "config_version": "v7",
        "created_at": NOW,
        "updated_at": NOW,
    }
    return Mission(**{**base, **overrides})


def _parse_sse(body: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for block in body.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        entry: dict[str, str] = {}
        for line in block.splitlines():
            if ": " in line:
                key, value = line.split(": ", 1)
                entry[key] = value
        if entry:
            events.append(entry)
    return events
