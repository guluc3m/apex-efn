"""HTTP surface for D4-07: sessions, CSV upload (never activates) and the activation request."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.agents.onboarding import InMemoryOnboardingStore, OnboardingDeps, OnboardingService
from apex.agents.ports import DecisionRef, PendingSignature
from apex.api import onboarding as onboarding_api
from apex.common.clock import FixedClock
from apex.common.errors import install_problem_handlers

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
REPORT = {"rows_ok": 34, "rows_rejected": 2, "projection_enabled": False}


class _Importer:
    async def parse(
        self, content: bytes, *, base_currency: str, tenant_id: str, now: datetime
    ) -> Any:
        class _Result:
            report = REPORT

        return _Result()


class _Objects:
    async def put(self, key: str, content: bytes, *, content_type: str) -> str:
        return key


class _Decisions:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create_decision(
        self, type: str, subject_ref: str, payload: Any, *, tenant_id: str
    ) -> DecisionRef:
        self.created.append({"type": type, "subject_ref": subject_ref})
        return DecisionRef(id=f"d{len(self.created)}", status="pending_signature")

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> Any:
        raise PendingSignature(decision_id)

    async def sign_service_event(self, service: str, payload: Any, *, tenant_id: str) -> str:
        return "sig"


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> str:
        self.n += 1
        return f"i{self.n}"


@pytest.fixture(autouse=True)
def _tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")


@pytest.fixture
def app() -> Iterator[FastAPI]:
    service = OnboardingService(
        OnboardingDeps(
            store=InMemoryOnboardingStore(),
            importer=_Importer(),
            objects=_Objects(),
            decisions=_Decisions(),
            clock=FixedClock(NOW),
            ids=_Ids(),
            stale_after_days=45,
            config_version=lambda tenant_id: "cfg-7",
        )
    )
    application = FastAPI()
    install_problem_handlers(application)
    application.include_router(onboarding_api.router, prefix="/onboarding")
    application.dependency_overrides[onboarding_api.get_onboarding] = lambda: service
    yield application


def _h(tenant: str = TENANT) -> dict[str, str]:
    return {"X-Tenant-Id": tenant}


def test_start_a_session(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post("/onboarding/sessions", headers=_h())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "started"
    assert body["profile"]["legal_name"] is None


def test_update_the_profile(app: FastAPI) -> None:
    with TestClient(app) as client:
        session = client.post("/onboarding/sessions", headers=_h()).json()
        response = client.patch(
            f"/onboarding/sessions/{session['id']}",
            json={"legal_name": "ACME", "base_currency": "EUR"},
            headers=_h(),
        )
    assert response.status_code == 200
    assert response.json()["status"] == "profiled"
    assert response.json()["profile"]["legal_name"] == "ACME"


def test_upload_returns_the_report_and_never_activates(app: FastAPI) -> None:
    with TestClient(app) as client:
        session = client.post("/onboarding/sessions", headers=_h()).json()
        response = client.post(
            f"/onboarding/{session['id']}/financial-csv",
            files={"file": ("fin.csv", b"period,metric,value_minor\n", "text/csv")},
            data={"base_currency": "EUR"},
            headers=_h(),
        )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["report"] == REPORT
    assert body["activation_decision_id"] is None


def test_upload_rejects_an_oversized_file(app: FastAPI) -> None:
    with TestClient(app) as client:
        session = client.post("/onboarding/sessions", headers=_h()).json()
        big = b"x" * (onboarding_api.MAX_CSV_BYTES + 1)
        response = client.post(
            f"/onboarding/{session['id']}/financial-csv",
            files={"file": ("fin.csv", big, "text/csv")},
            headers=_h(),
        )
    assert response.status_code == 413


def test_activation_returns_a_pending_decision(app: FastAPI) -> None:
    with TestClient(app) as client:
        session = client.post("/onboarding/sessions", headers=_h()).json()
        snapshot = client.post(
            f"/onboarding/{session['id']}/financial-csv",
            files={"file": ("fin.csv", b"period,metric,value_minor\n", "text/csv")},
            headers=_h(),
        ).json()
        response = client.post(
            f"/onboarding/{session['id']}/financial-csv/activate",
            data={"snapshot_id": snapshot["id"]},
            headers=_h(),
        )
    assert response.status_code == 202
    assert response.json() == {"decision_id": "d1", "status": "pending_signature"}


def test_activation_of_an_unknown_snapshot_is_404(app: FastAPI) -> None:
    with TestClient(app) as client:
        session = client.post("/onboarding/sessions", headers=_h()).json()
        response = client.post(
            f"/onboarding/{session['id']}/financial-csv/activate",
            data={"snapshot_id": "nope"},
            headers=_h(),
        )
    assert response.status_code == 404


def test_onboarding_needs_a_tenant(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_ALLOW_TENANT_HEADER", raising=False)
    with TestClient(app) as client:
        assert client.post("/onboarding/sessions", headers=_h()).status_code == 401
