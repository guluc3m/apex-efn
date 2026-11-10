"""End-to-end: the application authenticates through the real dependency graph."""

from __future__ import annotations

import logging

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from apex.auth.deps import get_auth_clock, get_auth_settings, get_jwks_provider
from apex.auth.settings import AuthSettings
from apex.common.tenant import get_roles, get_tenant_id
from apex.config import Settings
from apex.main import create_app
from tests.auth.helpers import AUDIENCE, ISSUER, NOW

PROBLEM_JSON = "application/problem+json"


@pytest.fixture
def app(settings: AuthSettings, provider) -> FastAPI:
    application = create_app(Settings(idempotency_backend="memory"))
    application.dependency_overrides[get_auth_settings] = lambda: settings
    application.dependency_overrides[get_jwks_provider] = lambda: provider
    application.dependency_overrides[get_auth_clock] = lambda: lambda: NOW

    probe = APIRouter()

    @probe.get("/v1/_auth_probe")
    async def auth_probe(
        tenant_id: str = Depends(get_tenant_id),
        roles: tuple[str, ...] = Depends(get_roles),
    ) -> dict[str, object]:
        return {"tenant": tenant_id, "roles": list(roles)}

    application.include_router(probe)
    return application


def test_valid_token_reaches_the_route(app: FastAPI, make_token) -> None:
    response = TestClient(app).get(
        "/v1/_auth_probe", headers={"authorization": f"Bearer {make_token()}"}
    )

    assert response.status_code == 200
    assert response.json() == {"tenant": "tenant-a", "roles": ["owner"]}


def test_tenant_header_cannot_override_a_valid_token(app: FastAPI, make_token) -> None:
    response = TestClient(app).get(
        "/v1/_auth_probe",
        headers={"authorization": f"Bearer {make_token()}", "x-tenant-id": "tenant-b"},
    )

    assert response.status_code == 200
    assert response.json()["tenant"] == "tenant-a"


def test_bad_token_is_a_problem_json_401_and_never_echoes_the_token(
    app: FastAPI, make_token
) -> None:
    token = make_token(claims={"exp": int(NOW.timestamp()) - 10_000})

    response = TestClient(app).get("/v1/_auth_probe", headers={"authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert token not in response.text
    assert response.json()["status"] == 401


def test_no_credentials_is_a_401(app: FastAPI, monkeypatch) -> None:
    monkeypatch.delenv("APEX_ALLOW_TENANT_HEADER", raising=False)

    response = TestClient(app).get("/v1/_auth_probe")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith(PROBLEM_JSON)


def test_dev_header_mode_still_works_for_local_development(app: FastAPI, monkeypatch) -> None:
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")
    monkeypatch.setenv("APEX_DEV_ROLES", "owner")

    response = TestClient(app).get("/v1/_auth_probe", headers={"x-tenant-id": "tenant-dev"})

    assert response.status_code == 200
    assert response.json() == {"tenant": "tenant-dev", "roles": ["owner"]}


def test_disabled_auth_answers_503(app: FastAPI, monkeypatch) -> None:
    monkeypatch.setitem(
        app.dependency_overrides,
        get_auth_settings,
        lambda: AuthSettings(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_url=f"{ISSUER}/protocol/openid-connect/certs",
            auth_disabled=True,
        ),
    )

    response = TestClient(app).get("/v1/_auth_probe")

    assert response.status_code == 503


def test_a_route_without_its_own_auth_dependency_is_still_protected(
    app: FastAPI, make_token, monkeypatch
) -> None:
    # GET /v1/audit is a stub owned by DEV-2 and depends on no tenant helper of its own. Authentication
    # is applied to the whole /v1 surface, so an unauthenticated call must not fall through to the stub.
    monkeypatch.delenv("APEX_ALLOW_TENANT_HEADER", raising=False)

    anonymous = TestClient(app).get("/v1/audit")
    authenticated = TestClient(app).get(
        "/v1/audit", headers={"authorization": f"Bearer {make_token()}"}
    )

    assert anonymous.status_code == 401
    assert authenticated.status_code != 401


def test_a_real_route_is_no_longer_blocked_by_the_placeholder(app: FastAPI, make_token) -> None:
    response = TestClient(app).get("/v1/audit", headers={"authorization": f"Bearer {make_token()}"})

    # Whatever the owning lane answers (501 today, 200/403 later), it must not be the auth 401.
    assert response.status_code != 401


def test_the_token_never_reaches_the_logs(app: FastAPI, make_token, caplog) -> None:
    token = make_token(claims={"exp": int(NOW.timestamp()) - 10_000})

    with caplog.at_level(logging.DEBUG):
        TestClient(app).get("/v1/_auth_probe", headers={"authorization": f"Bearer {token}"})

    assert token not in caplog.text
