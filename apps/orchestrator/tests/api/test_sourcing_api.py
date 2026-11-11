"""HTTP surface for D4-08, against the shapes in ``contracts/openapi.yaml``."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.agents.missions import InMemoryMissionStore, MissionEventBus, MissionStatus
from apex.agents.request_store import InMemorySourcingRequestStore
from apex.agents.sourcing import NoViablePlatform, PlanStep, SourcingPlan, SourcingRequest
from apex.agents.sourcing_service import SourcingService, SourcingServiceDeps
from apex.api import missions as missions_api
from apex.api import sourcing as sourcing_api
from apex.common.clock import FixedClock
from apex.common.errors import install_problem_handlers
from apex.common.ids import IdGenerator

NOW = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
TENANT = "tenant-a"
TOKEN_BUDGET = 200_000


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


class _Settings:
    llm_mission_token_budget = TOKEN_BUDGET
    mission_autorun = False


@pytest.fixture
def app() -> Iterator[FastAPI]:
    clock = FixedClock(NOW)
    store = InMemoryMissionStore()
    bus = MissionEventBus()
    requests = InMemorySourcingRequestStore()
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
    application.state.settings = _Settings()
    application.include_router(sourcing_api.router, prefix="/sourcing-requests")
    application.include_router(missions_api.router, prefix="/missions")
    application.dependency_overrides[sourcing_api.get_sourcing_service] = lambda: service
    application.dependency_overrides[sourcing_api.get_request_store] = lambda: requests
    yield application


def _h(tenant: str = TENANT) -> dict[str, str]:
    return {"X-Tenant-Id": tenant}


def _create_request(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/sourcing-requests",
        json={"natural_language": "Necesito botellas PET", "delivery_country": "ES"},
        headers=_h(),
    )
    assert response.status_code == 201, response.text
    return response.json()


# ----- POST /sourcing-requests -------------------------------------------------------------------


def test_create_sourcing_request_returns_the_contract_shape(app: FastAPI) -> None:
    with TestClient(app) as client:
        body = _create_request(client)
    assert body["id"] == "sr-1"
    assert body["status"] == "needs_clarification"  # the intake reported missing fields
    assert body["spec"] == {
        "description": "Botellas PET 500ml",
        "specifications": None,
        "certifications": ["food grade"],
    }
    assert body["delivery_country"] == "ES"
    assert body["target_delivery_date"] == "2027-06-01"
    assert body["needs_clarification"] == ["quantity_tiers"]
    assert body["max_budget"] is None


def test_the_caller_stated_country_wins_over_the_inferred_one(app: FastAPI) -> None:
    with TestClient(app) as client:
        body = client.post(
            "/sourcing-requests",
            json={"natural_language": "botellas", "delivery_country": "FR"},
            headers=_h(),
        ).json()
    assert body["delivery_country"] == "FR"


def test_a_stated_budget_is_echoed_as_money(app: FastAPI) -> None:
    with TestClient(app) as client:
        body = client.post(
            "/sourcing-requests",
            json={
                "natural_language": "botellas",
                "delivery_country": "ES",
                "max_budget": {"amount_minor": 450_000, "currency": "EUR"},
            },
            headers=_h(),
        ).json()
    assert body["max_budget"] == {"amount_minor": 450_000, "currency": "EUR"}


@pytest.mark.parametrize(
    "body",
    [
        {"natural_language": "", "delivery_country": "ES"},
        {"natural_language": "x"},
        {"natural_language": "x", "delivery_country": "Spain"},
        {"natural_language": "x", "delivery_country": "ES", "max_budget": {"amount_minor": 1}},
    ],
)
def test_invalid_bodies_are_422(app: FastAPI, body: dict[str, Any]) -> None:
    with TestClient(app) as client:
        assert client.post("/sourcing-requests", json=body, headers=_h()).status_code == 422


def test_sourcing_needs_a_tenant(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_ALLOW_TENANT_HEADER", raising=False)
    with TestClient(app) as client:
        assert (
            client.post(
                "/sourcing-requests",
                json={"natural_language": "x", "delivery_country": "ES"},
                headers=_h(),
            ).status_code
            == 401
        )


# ----- POST /missions ----------------------------------------------------------------------------


def test_create_mission_returns_the_contract_shape(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = _create_request(client)
        response = client.post(
            "/missions", json={"sourcing_request_id": created["id"]}, headers=_h()
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sourcing_request_id"] == "sr-1"
    assert body["state"] == "sourcing"  # a planned mission is about to source
    assert body["offers_discovered"] == 0
    assert body["offers_in_gate"] == 0
    assert body["token_budget"] == TOKEN_BUDGET
    assert body["error"] is None


def test_a_mission_for_an_unknown_request_is_404(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post("/missions", json={"sourcing_request_id": "nope"}, headers=_h())
    assert response.status_code == 404


def test_a_planner_failure_is_reported_on_the_mission(app: FastAPI) -> None:
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
    app.dependency_overrides[sourcing_api.get_sourcing_service] = lambda: failing
    with TestClient(app) as client:
        created = _create_request(client)
        body = client.post(
            "/missions", json={"sourcing_request_id": created["id"]}, headers=_h()
        ).json()
    assert body["state"] == "failed"
    assert body["error"] is not None
    assert "no_viable_platform" in body["error"]["detail"]


# ----- GET /missions/{id} ------------------------------------------------------------------------


def test_get_mission_is_tenant_scoped(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = _create_request(client)
        mission = client.post(
            "/missions", json={"sourcing_request_id": created["id"]}, headers=_h()
        ).json()
        assert client.get(f"/missions/{mission['id']}", headers=_h()).status_code == 200
        other = client.get(f"/missions/{mission['id']}", headers=_h("tenant-b"))
    assert other.status_code == 404
    assert other.headers["content-type"].startswith("application/problem+json")


# ----- list / pause / resume / cancel (issue #303) -----------------------------------------------


def _mission(client: TestClient) -> dict[str, Any]:
    created = _create_request(client)
    return client.post(
        "/missions", json={"sourcing_request_id": created["id"]}, headers=_h()
    ).json()


def test_list_missions_is_tenant_scoped_and_paginated(app: FastAPI) -> None:
    with TestClient(app) as client:
        _mission(client)
        page = client.get("/missions", headers=_h()).json()
        assert len(page["items"]) == 1 and page["next_cursor"] is None
        assert client.get("/missions", headers=_h("tenant-b")).json()["items"] == []
        assert client.get("/missions?state=failed", headers=_h()).json()["items"] == []
        assert client.get("/missions?cursor=%25%25", headers=_h()).status_code == 400


def test_pause_resume_cancel(app: FastAPI) -> None:
    with TestClient(app) as client:
        mid = _mission(client)["id"]
        assert client.post(f"/missions/{mid}/pause", headers=_h()).json()["paused"] is True
        assert client.post(f"/missions/{mid}/pause", headers=_h()).status_code == 409
        assert client.post(f"/missions/{mid}/resume", headers=_h()).json()["paused"] is False
        cancelled = client.post(f"/missions/{mid}/cancel", headers=_h()).json()
        assert cancelled["state"] == "cancelled"
        assert client.post(f"/missions/{mid}/cancel", headers=_h()).status_code == 409
        assert client.post(f"/missions/{mid}/pause", headers=_h()).status_code == 409
        assert client.post("/missions/nope/pause", headers=_h()).status_code == 404


# ----- GET /missions/{id}/events (SSE) ------------------------------------------------------------


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


def _mission(client: TestClient) -> dict[str, Any]:
    created = _create_request(client)
    return client.post(
        "/missions", json={"sourcing_request_id": created["id"]}, headers=_h()
    ).json()


def test_sse_replays_the_mission_log_with_contract_events(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = _mission(client)
        with client.stream("GET", f"/missions/{mission['id']}/events", headers=_h()) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())
    events = _parse_sse(body)
    assert [e["id"] for e in events] == ["1", "2", "3"]
    assert [e["event"] for e in events] == ["state_changed", "state_changed", "state_changed"]
    payload = json.loads(events[-1]["data"])
    assert payload["mission_id"] == mission["id"]
    assert payload["data"]["state"] == "sourcing"


def test_sse_last_event_id_skips_what_the_client_already_has(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = _mission(client)
        with client.stream(
            "GET", f"/missions/{mission['id']}/events", headers={**_h(), "Last-Event-ID": "2"}
        ) as response:
            body = "".join(response.iter_text())
    assert [e["id"] for e in _parse_sse(body)] == ["3"]


def test_sse_rejects_a_malformed_last_event_id(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = _mission(client)
        response = client.get(
            f"/missions/{mission['id']}/events", headers={**_h(), "Last-Event-ID": "abc"}
        )
    assert response.status_code == 400


def test_sse_404s_before_streaming_for_an_unknown_mission(app: FastAPI) -> None:
    with TestClient(app) as client:
        assert client.get("/missions/nope/events", headers=_h()).status_code == 404


def test_a_planned_mission_stream_ends_immediately(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = _mission(client)
        assert mission["state"] == MissionStatus.PLANNED.value or mission["state"] == "sourcing"
        with client.stream("GET", f"/missions/{mission['id']}/events", headers=_h()) as response:
            body = "".join(response.iter_text())
    assert len(_parse_sse(body)) == 3  # replay only, no hang
