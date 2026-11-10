"""HTTP surface for D5-08: ``POST /v1/negotiations/{id}/takeover|resume|abort``.

The router is mounted on a bare app with the control service injected, exactly like the gate tests: the
default dependency owns an in-process engine, and the shared engine arrives when DEV-4 wires the graph.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.api import negotiations as negotiations_api
from apex.common.errors import install_problem_handlers
from apex.negotiation.api import NegotiationControlService, build_default_control
from apex.negotiation.engine import NegotiationError
from tests.negotiation.fakes import NOW, Harness, T, cooperative_seller, harness, params
from tests.negotiation.fakes import request as open_request

PROBLEM_JSON = "application/problem+json"


@dataclass
class Rig:
    app: FastAPI
    h: Harness


@pytest.fixture(autouse=True)
def _tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")


@pytest.fixture
def rig() -> Iterator[Rig]:
    h = harness(cooperative_seller())
    control = NegotiationControlService(h.engine)
    application = FastAPI()
    install_problem_handlers(application)
    application.include_router(negotiations_api.router, prefix="/v1/negotiations")
    application.dependency_overrides[negotiations_api.get_negotiation_control] = lambda: control
    yield Rig(application, h)


def _h(tenant: str = T) -> dict[str, str]:
    return {"X-Tenant-Id": tenant}


def _request(*, semi_automatic: bool = True, **overrides: object):  # type: ignore[no-untyped-def]
    return open_request(params(semi_automatic=semi_automatic, **overrides))


def _start(h: Harness, key: str = "neg-1", *, semi_automatic: bool = True) -> str:
    session = asyncio.run(
        h.engine.start(_request(semi_automatic=semi_automatic), idempotency_key=key)
    )
    return session.id


def _problem(response, reason: str) -> None:  # type: ignore[no-untyped-def]
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["reason"] == reason
    assert body["status"] == response.status_code


# ----- takeover ----------------------------------------------------------------------------------


def test_takeover_returns_the_contract_view(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        response = client.post(f"/v1/negotiations/{negotiation_id}/takeover", headers=_h())

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == negotiation_id
    assert body["state"] == "human_control"
    assert body["strategy"] == "playbook-v1"
    assert body["rounds"] == 0
    assert body["max_rounds"] == 6
    assert body["guardrail_hits"] == []
    assert body["pending_draft"] is None  # takeover drops the draft
    assert body["mission_id"] is None  # engine-level sessions have no mission
    assert body["trace_id"] is None
    assert set(body) == {
        "id",
        "offer_id",
        "strategy",
        "state",
        "rounds",
        "max_rounds",
        "guardrail_hits",
        "pending_draft",
        "mission_id",
        "trace_id",
    }


def test_takeover_drops_the_pending_draft(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        assert (
            client.post(f"/v1/negotiations/{negotiation_id}/takeover", headers=_h()).status_code
            == 200
        )

    stored = asyncio.run(rig.h.store.get(negotiation_id))
    assert stored is not None
    assert stored.pending is None
    assert stored.human_in_control is True


def test_takeover_of_an_unknown_negotiation_is_404(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        response = client.post("/v1/negotiations/nope/takeover", headers=_h())
    assert response.status_code == 404
    _problem(response, "not_found")


def test_another_tenant_gets_404_and_learns_nothing(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        response = client.post(
            f"/v1/negotiations/{negotiation_id}/takeover", headers=_h("tenant-b")
        )
    assert response.status_code == 404
    _problem(response, "not_found")
    assert "tenant" not in response.json()["detail"].lower()


def test_takeover_of_a_terminal_negotiation_is_409(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        assert (
            client.post(f"/v1/negotiations/{negotiation_id}/abort", headers=_h()).status_code == 200
        )
        response = client.post(f"/v1/negotiations/{negotiation_id}/takeover", headers=_h())
    assert response.status_code == 409
    _problem(response, "terminal")


def test_a_request_without_a_tenant_is_refused(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        response = client.post(f"/v1/negotiations/{negotiation_id}/takeover")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith(PROBLEM_JSON)


# ----- resume ------------------------------------------------------------------------------------


def test_resume_returns_control_to_the_agent(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        client.post(f"/v1/negotiations/{negotiation_id}/takeover", headers=_h())
        response = client.post(f"/v1/negotiations/{negotiation_id}/resume", headers=_h())
    assert response.status_code == 200
    assert response.json()["state"] == "running"


def test_resume_without_takeover_is_409(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        response = client.post(f"/v1/negotiations/{negotiation_id}/resume", headers=_h())
    assert response.status_code == 409
    _problem(response, "not_in_human_control")


def test_resume_after_abort_is_409(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        client.post(f"/v1/negotiations/{negotiation_id}/abort", headers=_h())
        response = client.post(f"/v1/negotiations/{negotiation_id}/resume", headers=_h())
    assert response.status_code == 409
    _problem(response, "terminal")


# ----- abort -------------------------------------------------------------------------------------


def test_abort_stops_the_negotiation_and_records_the_reason(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        response = client.post(
            f"/v1/negotiations/{negotiation_id}/abort",
            headers=_h(),
            json={"reason": "buyer_cancelled"},
        )
        again = client.post(
            f"/v1/negotiations/{negotiation_id}/abort",
            headers=_h(),
            json={"reason": "later_reason"},
        )
    assert response.status_code == 200
    assert response.json()["state"] == "aborted"
    assert again.status_code == 200
    stored = asyncio.run(rig.h.store.get(negotiation_id))
    assert stored is not None
    assert stored.stop_reason == "buyer_cancelled"  # the first reason wins


def test_abort_without_a_body_uses_the_closed_default_reason(rig: Rig) -> None:
    negotiation_id = _start(rig.h)
    with TestClient(rig.app) as client:
        response = client.post(f"/v1/negotiations/{negotiation_id}/abort", headers=_h())
    assert response.status_code == 200
    stored = asyncio.run(rig.h.store.get(negotiation_id))
    assert stored is not None
    assert stored.stop_reason == "human_abort"


def test_abort_of_an_unknown_negotiation_is_404(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        response = client.post("/v1/negotiations/nope/abort", headers=_h())
    assert response.status_code == 404
    _problem(response, "not_found")


# ----- guardrail mapping and default wiring ------------------------------------------------------


def test_guardrail_hits_use_the_contract_enum_and_carry_a_timestamp(rig: Rig) -> None:
    session = asyncio.run(
        rig.h.engine.start(
            _request(semi_automatic=False, max_messages_per_hour=1), idempotency_key="neg-1"
        )
    )
    rig.h.clock.advance(timedelta(minutes=1))
    asyncio.run(rig.h.engine.advance(session.id, tenant_id=T))

    with TestClient(rig.app) as client:
        response = client.post(f"/v1/negotiations/{session.id}/takeover", headers=_h())

    assert response.status_code == 200
    hits = response.json()["guardrail_hits"]
    assert [hit["code"] for hit in hits] == ["message_rate"]  # deduplicated to the closed enum
    assert datetime.fromisoformat(hits[0]["at"].replace("Z", "+00:00")) == NOW + timedelta(
        minutes=1
    )


def test_the_default_control_is_wired_and_answers_not_found() -> None:
    control = build_default_control()
    with pytest.raises(NegotiationError) as exc:
        asyncio.run(control.takeover("unknown", tenant_id=T))
    assert exc.value.code == "not_found"
