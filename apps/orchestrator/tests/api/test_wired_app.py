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


def _new_mission(client: TestClient) -> dict[str, Any]:
    """Create a sourcing request and a mission for it, as the BFF does."""
    request = client.post(
        "/v1/sourcing-requests",
        json={"natural_language": "guantes de nitrilo", "delivery_country": "ES"},
        headers=_h(),
    ).json()
    mission: dict[str, Any] = client.post(
        "/v1/missions", json={"sourcing_request_id": request["id"]}, headers=_h()
    ).json()
    return mission


def test_sourcing_request_is_parsed_by_the_real_gateway(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/sourcing-requests",
            json={
                "natural_language": "necesito 500 cajas de guantes de nitrilo talla M",
                "delivery_country": "ES",
            },
            headers=_h(),
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["spec"]["description"] == "Nitrile gloves size M, box of 100"
    assert body["quantity_tiers"] == [{"quantity": 500, "priority": "primary"}]
    assert body["target_delivery_date"] == "2027-06-01"
    assert body["delivery_country"] == "ES"
    assert body["status"] == "normalized"


def test_a_mission_is_planned_by_the_real_planner(app: FastAPI) -> None:
    with TestClient(app) as client:
        request = client.post(
            "/v1/sourcing-requests",
            json={"natural_language": "guantes de nitrilo talla M", "delivery_country": "ES"},
            headers=_h(),
        ).json()
        created = client.post(
            "/v1/missions", json={"sourcing_request_id": request["id"]}, headers=_h()
        )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["state"] == "sourcing"
    assert body["sourcing_request_id"] == request["id"]
    assert body["error"] is None


def test_the_mission_streams_its_events(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = _new_mission(client)
        with client.stream("GET", f"/v1/missions/{mission['id']}/events", headers=_h()) as response:
            body = "".join(response.iter_text())
    assert response.status_code == 200
    events = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert events == ["state_changed", "state_changed", "state_changed"]


def test_a_mission_is_readable_after_creation(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = _new_mission(client)
        fetched = client.get(f"/v1/missions/{mission['id']}", headers=_h())
    assert fetched.status_code == 200
    assert fetched.json()["id"] == mission["id"]


def test_missions_are_isolated_per_tenant(app: FastAPI) -> None:
    with TestClient(app) as client:
        mission = _new_mission(client)
        other = client.get(f"/v1/missions/{mission['id']}", headers=_h("tenant-b"))
    assert other.status_code == 404


def test_read_routes_are_wired_and_empty_before_any_mission(app: FastAPI) -> None:
    with TestClient(app) as client:
        seller = client.get("/v1/sellers/s-1/confidence", headers=_h())
        assert seller.status_code == 200 and seller.json()["history"] == []
        assert client.get("/v1/dashboard/deals", headers=_h()).json() == {"deals": []}
        assert client.get("/v1/gate/queue", headers=_h()).status_code == 200


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


def test_an_onboarding_session_can_be_started_and_profiled(app: FastAPI) -> None:
    with TestClient(app) as client:
        created = client.post("/v1/onboarding/sessions", headers=_h())
        assert created.status_code == 201, created.text
        session = created.json()
        assert session["status"] == "profiling"
        updated = client.patch(
            f"/v1/onboarding/sessions/{session['id']}",
            json={"company_profile": {"legal_name": "ACME", "base_currency": "EUR"}},
            headers=_h(),
        )
    assert updated.status_code == 200
    assert updated.json()["status"] == "profiling"
    assert updated.json()["company_profile"]["legal_name"] == "ACME"


class _Objects:
    def __init__(self) -> None:
        self.stored: dict[str, bytes] = {}

    async def put(self, key: str, content: bytes, *, content_type: str) -> str:
        self.stored[key] = content
        return f"s3://apex-csv/{key}"


BUNDLED_SCENARIOS = Path(__file__).resolve().parents[3] / "llm-stub" / "scenarios"


def test_onboarding_chat_mapping_and_csv_upload_work_against_the_bundled_stub() -> None:
    """The demo path: no scenario pinning, the stub picks by role and requested schema."""
    import asyncio

    stub = mount_stub(BUNDLED_SCENARIOS)
    objects = _Objects()
    services = build_app_services(
        Settings(idempotency_backend="memory"),
        clock=FixedClock(NOW),
        http_client_factory=lambda cfg: httpx.AsyncClient(
            transport=stub._transport,  # type: ignore[attr-defined]
            base_url=str(stub.base_url),
        ),
        objects=objects,
    )
    application = create_app(
        Settings(idempotency_backend="memory"), store=InMemoryIdempotencyStore(), services=services
    )
    try:
        with TestClient(application) as client:
            sid = client.post("/v1/onboarding/sessions", headers=_h()).json()["id"]
            turn = client.post(
                f"/v1/onboarding/sessions/{sid}/messages", json={"text": "hola"}, headers=_h()
            )
            assert turn.status_code == 200, turn.text
            assert [m["role"] for m in turn.json()["messages"]] == ["user", "agent"]

            csv = b"periodo,metrica,importe,moneda\n2026-09,cash_balance,5000000,EUR\n"
            mapping = client.post(
                f"/v1/onboarding/{sid}/financial-csv/mapping",
                files={"file": ("fin.csv", csv, "text/csv")},
                headers=_h(),
            )
            assert mapping.status_code == 200, mapping.text
            confirmed = {m["source"]: m["target"] for m in mapping.json()["mappings"]}
            assert confirmed == {
                "periodo": "period",
                "metrica": "metric",
                "importe": "value_minor",
                "moneda": "currency",
            }

            import json as _json

            upload = client.post(
                f"/v1/onboarding/{sid}/financial-csv",
                files={"file": ("fin.csv", csv, "text/csv")},
                data={"column_mapping": _json.dumps(confirmed)},
                headers=_h(),
            )
            assert upload.status_code == 201, upload.text
            assert upload.json()["stored_object"].startswith("s3://apex-csv/financial-csv/")
            assert list(objects.stored.values()) == [csv]  # the original, not the remapped copy
    finally:
        asyncio.run(stub.aclose())


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
        mission = _new_mission(client)
    assert mission["state"] == "sourcing"
    assert mission["error"] is None


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
            request = client.post(
                "/v1/sourcing-requests",
                json={"natural_language": "guantes", "delivery_country": "ES"},
                headers=_h(),
            ).json()
            mission = client.post(
                "/v1/missions", json={"sourcing_request_id": request["id"]}, headers=_h()
            ).json()
        assert mission["state"] == "failed"
        assert mission["error"] is not None
        assert "D5-01" in mission["error"]["detail"]
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
        sourcing = client.post(
            "/v1/sourcing-requests",
            json={"natural_language": "gloves", "delivery_country": "ES"},
            headers=_h(),
        )
    assert sourcing.status_code == 502, sourcing.text
    assert sourcing.json()["reason"] == "llm_unavailable"
    assert sourcing.headers["content-type"].startswith("application/problem+json")


# ----- writes are idempotent when the caller sends the key (the BFF always does) -------------------


def test_replaying_a_mission_creation_returns_the_same_mission(app: FastAPI) -> None:
    """The BFF generates an Idempotency-Key per user action; a retry must not create a second mission."""
    with TestClient(app) as client:
        request = client.post(
            "/v1/sourcing-requests",
            json={"natural_language": "guantes", "delivery_country": "ES"},
            headers=_h(),
        ).json()
    body = {"sourcing_request_id": request["id"]}
    headers = {**_h(), "Idempotency-Key": "bff-abc-123"}
    with TestClient(app) as client:
        first = client.post("/v1/missions", json=body, headers=headers)
        second = client.post("/v1/missions", json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.headers.get("idempotent-replayed") == "true"


def test_the_same_key_with_a_different_body_is_refused(app: FastAPI) -> None:
    """Reusing a key for a different request is a client bug and must not silently return the old answer."""
    headers = {**_h(), "Idempotency-Key": "bff-abc-456"}
    with TestClient(app) as client:
        request = client.post(
            "/v1/sourcing-requests",
            json={"natural_language": "guantes", "delivery_country": "ES"},
            headers=_h(),
        ).json()
        first = client.post(
            "/v1/missions", json={"sourcing_request_id": request["id"]}, headers=headers
        )
        conflict = client.post(
            "/v1/missions",
            json={"sourcing_request_id": request["id"], "profile_id": "other"},
            headers=headers,
        )
    assert first.status_code == 201
    assert conflict.status_code == 422


def test_replaying_a_sourcing_request_returns_the_same_request(app: FastAPI) -> None:
    headers = {**_h(), "Idempotency-Key": "bff-sr-1"}
    body = {"natural_language": "gloves", "delivery_country": "ES"}
    with TestClient(app) as client:
        first = client.post("/v1/sourcing-requests", json=body, headers=headers)
        second = client.post("/v1/sourcing-requests", json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


# ----- the browser worker is wired when a URL is configured ---------------------------------------


def test_the_worker_port_names_its_owner_when_no_url_is_configured() -> None:
    """A mission that needs to scrape must fail with the owner, not call a service that is not there."""
    from apex.wiring import UnwiredBrowserWorker, build_app_services

    services = build_app_services(Settings())
    assert isinstance(services.runner._deps.scraping._deps.worker, UnwiredBrowserWorker)  # type: ignore[attr-defined]


def test_a_configured_worker_url_switches_to_the_http_client() -> None:
    from apex.agents.browser_worker import HttpBrowserWorker
    from apex.wiring import build_app_services

    services = build_app_services(
        Settings(browser_worker_url="http://worker.test", browser_worker_token="t")
    )
    worker = services.runner._deps.scraping._deps.worker  # type: ignore[attr-defined]
    assert isinstance(worker, HttpBrowserWorker)
    assert worker.base_url == "http://worker.test"
    assert worker.service_token == "t"


async def test_the_runner_reaches_the_worker_and_stops_at_the_next_unwired_port() -> None:
    """The worker and FX are wired; finance has no active snapshot (criterion 1), so the mission fails there.

    That is the honest state of the chain today, and it proves both the worker client and the FX port are
    actually called: the failure reason names the port *after* them.
    """
    from apex.agents.missions import Mission, MissionStatus
    from apex.agents.sourcing import PlanStep, SourcingPlan
    from apex.wiring import build_app_services

    offer = {
        "platform": "mock-a",
        "platform_offer_id": "a-1",
        "product_id": "p-1",
        "platform_seller_id": "s-1",
        "title": "Gloves",
        "unit_price": {"amount_minor": 445, "currency": "EUR"},
        "list_price": None,
        "price_tiers": [],
        "moq": 500,
        "quantity_available": 2000,
        "specifications": {},
        "certifications": [],
        "seller_country": "CN",
        "shipping": None,
        "incoterm": None,
        "lead_time_days": 10,
        "captured_at": "2026-11-09T12:00:00Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                202, json={"job_id": "j-1", "status": "queued", "deduplicated": False}
            )
        return httpx.Response(
            200,
            json={
                "job_id": "j-1",
                "status": "succeeded",
                "result": {"kind": "search", "offers": [offer], "skipped": [], "truncated": False},
            },
        )

    services = build_app_services(
        Settings(browser_worker_url="http://worker.test", browser_worker_token="t"),
        clock=FixedClock(NOW),
        http_client_factory=lambda cfg: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://worker.test"
        ),
    )
    plan = SourcingPlan(
        steps=[PlanStep(platform_id="mock-a", transport="http", query="gloves")],
        rationale="test",
        config_version="v1",
    )
    mission = Mission(
        id="m-1",
        tenant_id=TENANT,
        sourcing_request_id="sr-1",
        quantity=500,
        status=MissionStatus.PLANNED,
        config_version="v1",
        created_at=NOW,
        updated_at=NOW,
        plan=plan,
    )
    await services.mission_store.create(mission)
    result = await services.runner.run(tenant_id=TENANT, mission_id="m-1")
    assert result.mission.status is MissionStatus.FAILED
    assert result.failed_reason is not None
    assert (
        "no_active_snapshot" in result.failed_reason
    )  # finance: trust and sanity are wired, no onboarding yet
    assert "D5-01" not in result.failed_reason  # the worker is wired
    assert "D3-03" not in result.failed_reason  # FX is wired


# ----- the mission reports the tokens the gateway actually committed ------------------------------


def test_a_mission_reports_the_tokens_its_planning_used(app: FastAPI) -> None:
    """Criterion 28: the token budget is a hard limit, so the number the UI shows must be the real one."""
    with TestClient(app) as client:
        request = client.post(
            "/v1/sourcing-requests",
            json={"natural_language": "guantes", "delivery_country": "ES"},
            headers=_h(),
        ).json()
        mission = client.post(
            "/v1/missions", json={"sourcing_request_id": request["id"]}, headers=_h()
        ).json()
        fetched = client.get(f"/v1/missions/{mission['id']}", headers=_h()).json()
    # The stub reports usage, so the gateway committed something for the planning call.
    assert mission["tokens_used"] > 0
    assert fetched["tokens_used"] == mission["tokens_used"]
    assert mission["tokens_used"] < mission["token_budget"]


def test_a_mission_without_llm_calls_reports_zero_tokens() -> None:
    """A mission that never reached the model must not invent usage."""
    from apex.wiring import build_app_services

    services = build_app_services(Settings(idempotency_backend="memory"), clock=FixedClock(NOW))
    assert services.gateway.tokens_used("mission-that-never-ran") == 0


def test_dashboard_summary_and_missing_deal(app: FastAPI) -> None:
    with TestClient(app) as client:
        summary = client.get("/v1/dashboard/summary", headers=_h()).json()
        assert summary["pending_count"] == 0 and summary["nearest_sla_due_at"] is None
        assert client.get("/v1/dashboard/deals/nope", headers=_h()).status_code == 404
