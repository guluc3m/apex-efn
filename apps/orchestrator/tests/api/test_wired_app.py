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


# ----- config and onboarding are wired too -------------------------------------------------------


def test_effective_config_is_served_for_a_demo_tenant(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/config/effective", headers=_h())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tenant_id"] == TENANT
    assert body["config_version"] >= 1
    assert body["content_hash"].startswith("sha256:")
    assert body["values"]["sanity.z_gate"]["status"] == "set"


def test_the_demo_tenants_get_their_seeded_values(app: FastAPI) -> None:
    """ADR-900 Q7: the demo tenants get demo values from the seed, never from /config/defaults."""
    with TestClient(app) as client:
        response = client.get("/v1/config/effective", headers=_h())
    values = response.json()["values"]
    assert values["neg.max_discount"]["status"] == "set"
    assert values["neg.max_discount"]["value"] == "0.15"


def test_a_tenant_outside_the_demo_set_keeps_the_unset_keys(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/config/effective", headers=_h("tenant-c"))
    values = response.json()["values"]
    assert values["neg.max_discount"]["status"] == "unset"
    assert values["approval.threshold"]["status"] == "unset"


def test_a_config_proposal_says_signing_is_not_wired(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/config/proposals",
            json={"base_config_version": 1, "patch": {"sanity": {"z_gate": "7.0"}}},
            headers=_h(),
        )
    assert response.status_code == 501, response.text


def test_an_onboarding_session_can_be_started_and_profiled(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = client.post("/v1/onboarding/sessions", headers=_h())
        assert created.status_code == 201, created.text
        session = created.json()
        assert session["status"] == "started"
        updated = client.patch(
            f"/v1/onboarding/sessions/{session['id']}",
            json={"legal_name": "ACME", "base_currency": "EUR"},
            headers=_h(),
        )
    assert updated.status_code == 200
    assert updated.json()["status"] == "profiled"
    assert updated.json()["profile"]["legal_name"] == "ACME"


def test_a_csv_upload_says_the_importer_is_not_wired(app: FastAPI) -> None:
    with TestClient(app) as client:
        session = client.post("/v1/onboarding/sessions", headers=_h()).json()
        response = client.post(
            f"/v1/onboarding/{session['id']}/financial-csv",
            files={"file": ("fin.csv", b"period,metric,value_minor\n", "text/csv")},
            headers=_h(),
        )
    assert response.status_code == 501, response.text
    # The original is stored before it is parsed, so the first missing piece is object storage (D1-06);
    # once that lands the importer (D3-04) is next. Either way the answer names the owning lane.
    assert "not wired yet" in response.json()["detail"]
    assert "owner: DEV-" in response.json()["detail"]


# ----- the app boots even when the config defaults are not there ----------------------------------


def test_the_app_boots_when_the_config_defaults_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A container image built from apps/orchestrator alone has no config/defaults. It must not crash.

    The service graph reads that file while it is built, so the failure is simulated at the seam that reads
    it: ``build_app_services`` itself.
    """
    import apex.main as main_module

    def _missing(_cfg: Any) -> Any:
        raise FileNotFoundError("config/defaults/tenant-config.v1.json")

    monkeypatch.setattr(main_module, "build_app_services", _missing)
    app = create_app(Settings(idempotency_backend="memory"), store=InMemoryIdempotencyStore())
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        sourcing = client.post("/v1/sourcing-requests", json={"text": "x"}, headers=_h())
        missions = client.post("/v1/missions", json={}, headers=_h())
    # The routes that depend on the service graph answer 501 with a reason instead of crashing the process.
    assert sourcing.status_code == 501, sourcing.text
    assert "wire SourcingService" in sourcing.json()["detail"]
    assert missions.status_code == 501


def test_the_app_still_boots_when_the_service_graph_is_unavailable() -> None:
    app = create_app(
        Settings(idempotency_backend="memory"), store=InMemoryIdempotencyStore(), services=None
    )
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


# ----- mission autorun is a flag, off by default -------------------------------------------------


def test_missions_are_not_run_automatically_by_default(app: FastAPI) -> None:
    """The runner needs D5-01 and the DEV-3 engines; with them missing every mission would fail."""
    with TestClient(app) as client:
        mission = client.post(
            "/v1/missions",
            json={"sourcing_request_id": "sr-1", "spec": "gloves", "quantity_tiers": [500]},
            headers=_h(),
        ).json()
    assert mission["status"] == "planned"
    assert mission["failure_reason"] is None


def test_turning_autorun_on_advances_the_mission_and_reports_the_missing_owner() -> None:
    """With the flag on, the mission does not sit at `planned`: it fails naming the port it needs."""
    import asyncio

    from apex.wiring import build_app_services

    stub = asyncio.run(_open_stub())
    services = build_app_services(
        Settings(idempotency_backend="memory", mission_autorun=True),
        clock=FixedClock(NOW),
        http_client_factory=lambda cfg: _scoped(stub, _scenario_for(cfg)),
    )
    application = create_app(
        Settings(idempotency_backend="memory", mission_autorun=True),
        store=InMemoryIdempotencyStore(),
        services=services,
    )
    application.state.stub = stub
    try:
        with TestClient(application) as client:
            mission = client.post(
                "/v1/missions",
                json={"sourcing_request_id": "sr-1", "spec": "gloves", "quantity_tiers": [500]},
                headers=_h(),
            ).json()
        assert mission["status"] == "failed"
        assert mission["failure_reason"] is not None
        assert "D5-01" in mission["failure_reason"]
    finally:
        asyncio.run(stub.aclose())


def test_the_service_graph_exposes_a_runner_with_named_unwired_ports() -> None:
    from apex.agents.mission_runner import MissionRunner
    from apex.wiring import build_app_services

    services = build_app_services(Settings())
    assert isinstance(services.runner, MissionRunner)
    assert services.settings.mission_autorun is False


# ----- an unreachable model endpoint is a 502 with a reason, not a bare 500 -----------------------


def test_an_unreachable_llm_endpoint_is_a_502_with_a_reason() -> None:
    """The default endpoint is the LLM stub. If it is not running, the caller must learn why.

    The failure is injected through the HTTP client factory rather than a closed port, so the test does not
    depend on what happens to be listening on the developer's machine.
    """
    from apex.wiring import build_app_services

    class _Refuse(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

    services = build_app_services(
        Settings(idempotency_backend="memory"),
        http_client_factory=lambda cfg: httpx.AsyncClient(transport=_Refuse()),
    )
    application = create_app(
        Settings(idempotency_backend="memory"), store=InMemoryIdempotencyStore(), services=services
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        sourcing = client.post("/v1/sourcing-requests", json={"text": "gloves"}, headers=_h())
        mission = client.post(
            "/v1/missions",
            json={"sourcing_request_id": "sr-1", "spec": "gloves", "quantity_tiers": [500]},
            headers=_h(),
        )
    assert sourcing.status_code == 502, sourcing.text
    assert sourcing.json()["reason"] == "llm_unavailable"
    assert sourcing.headers["content-type"].startswith("application/problem+json")
    assert mission.status_code == 502, mission.text
    assert mission.json()["reason"] == "llm_unavailable"
    assert "planner" in mission.json()["detail"]
