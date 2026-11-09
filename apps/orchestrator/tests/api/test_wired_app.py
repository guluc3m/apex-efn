"""End-to-end: the real app, gateway, prompts and services against the in-process LLM stub (D4-08 wiring).

No network, no real model: the stub answers with fixture documents, the gateway runs its structured-output
ladder, and the sourcing service plans a mission exactly as it will in production.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from llm_stub.testing import mount_stub

from apex.common.clock import FixedClock
from apex.common.idempotency import InMemoryIdempotencyStore
from apex.config import Settings
from apex.llm.config import RoleEndpointConfig
from apex.main import create_app
from apex.wiring import build_app_services

SCENARIOS = Path(__file__).resolve().parent / "stub_scenarios"
NOW = __import__("datetime").datetime(2026, 11, 9, 12, 0, tzinfo=__import__("datetime").UTC)
TENANT = "tenant-a"


def _scenario_for(cfg: RoleEndpointConfig) -> str:
    """The endpoint id carries the role, so the stub picks the matching fixture."""
    return cfg.endpoint_id.replace("default-", "role-")


@pytest.fixture(autouse=True)
def _tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")


@pytest.fixture
def app() -> Iterator[FastAPI]:
    import asyncio

    stub = asyncio.run(_open_stub())
    services = build_app_services(
        Settings(idempotency_backend="memory"),
        clock=FixedClock(NOW),
        http_client_factory=lambda cfg: _scoped(stub, _scenario_for(cfg)),
    )
    application = create_app(
        Settings(idempotency_backend="memory"),
        store=InMemoryIdempotencyStore(),
        services=services,
    )
    application.state.stub = stub
    yield application
    asyncio.run(stub.aclose())


async def _open_stub() -> Any:
    return mount_stub(SCENARIOS)


def _scoped(stub: Any, scenario: str) -> httpx.AsyncClient:
    """An AsyncClient that reaches the stub in-process and pins the scenario per request."""

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            request.headers["X-Stub-Scenario"] = scenario
            return await stub._transport.handle_async_request(request)  # type: ignore[attr-defined]

    return httpx.AsyncClient(transport=_Transport(), base_url=str(stub.base_url))


def _h(tenant: str = TENANT) -> dict[str, str]:
    return {"X-Tenant-Id": tenant}


def test_sourcing_request_is_parsed_by_the_real_gateway(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/sourcing-requests",
            json={
                "text": "necesito 500 cajas de guantes de nitrilo talla M",
                "base_currency": "EUR",
            },
            headers=_h(),
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["spec"] == "Nitrile gloves size M, box of 100"
    assert body["quantity_tiers"] == [{"min_quantity": 500}]
    assert body["deadline"] == "2027-06-01"
    assert body["destination_country"] == "ES"
    assert body["config_version"].startswith("v1:")


def test_a_mission_is_planned_by_the_real_planner(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = client.post(
            "/v1/missions",
            json={
                "sourcing_request_id": "sr-1",
                "spec": "Nitrile gloves size M",
                "quantity_tiers": [500],
                "destination_country": "ES",
            },
            headers=_h(),
        )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "planned"
    assert {s["platform_id"] for s in body["steps"]} == {"mock-a", "mock-b"}
    assert {s["transport"] for s in body["steps"]} == {"http", "browser"}
    assert body["rejected_steps"] == []


def test_the_mission_streams_its_events(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = client.post(
            "/v1/missions",
            json={"sourcing_request_id": "sr-1", "spec": "gloves", "quantity_tiers": [500]},
            headers=_h(),
        ).json()
        with client.stream("GET", f"/v1/missions/{mission['id']}/events", headers=_h()) as response:
            body = "".join(response.iter_text())
    assert response.status_code == 200
    events = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert events == ["mission_created", "planning_started", "plan_ready"]


def test_a_mission_is_readable_after_creation(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = client.post(
            "/v1/missions",
            json={"sourcing_request_id": "sr-1", "spec": "gloves", "quantity_tiers": [500]},
            headers=_h(),
        ).json()
        fetched = client.get(f"/v1/missions/{mission['id']}", headers=_h())
    assert fetched.status_code == 200
    assert fetched.json()["id"] == mission["id"]


def test_missions_are_isolated_per_tenant(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = client.post(
            "/v1/missions",
            json={"sourcing_request_id": "sr-1", "spec": "gloves", "quantity_tiers": [500]},
            headers=_h(),
        ).json()
        other = client.get(f"/v1/missions/{mission['id']}", headers=_h("tenant-b"))
    assert other.status_code == 404


def test_routes_whose_engines_are_missing_still_answer_501(app: FastAPI) -> None:
    """Honest failure: the DEV-3 engines are not merged, so analysis endpoints say so."""
    with TestClient(app) as client:
        assert client.get("/v1/sellers/s-1/confidence", headers=_h()).status_code == 501
        assert client.get("/v1/dashboard/deals", headers=_h()).status_code == 501
