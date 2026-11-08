"""HTTP surface: GET /config/effective and POST /config/proposals (mounted under /v1 by the app)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeDecisionPort, FixedClock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.api import config as config_api
from apex.common.errors import install_problem_handlers
from apex.tenant_config.load_defaults import seed
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.service import TenantConfigService


@pytest.fixture
def client_and_port() -> Iterator[tuple[TestClient, FakeDecisionPort]]:
    import asyncio

    repo = InMemoryConfigRepository()
    asyncio.run(seed(["tenant-a"], repo))
    port = FakeDecisionPort()
    clock = FixedClock(datetime(2026, 11, 8, 12, 0, tzinfo=UTC))

    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(config_api.router, prefix="/config")
    app.dependency_overrides[config_api.get_config_service] = lambda: TenantConfigService(
        repo, port, clock
    )
    with TestClient(app) as client:
        yield client, port


def _h(tenant: str = "tenant-a") -> dict[str, str]:
    return {"X-Tenant-Id": tenant}


def test_get_effective_returns_version_hash_and_explicit_unset(client_and_port: Any) -> None:
    client, _ = client_and_port
    r = client.get("/config/effective", params={"category": "steel"}, headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert body["config_version"] == 1
    assert body["content_hash"].startswith("sha256:")
    assert body["values"]["sanity.z_gate"] == {"value": 6.0, "status": "set", "layer": "global"}
    assert body["values"]["neg.max_discount"]["status"] == "unset"


def test_get_effective_requires_tenant(client_and_port: Any) -> None:
    client, _ = client_and_port
    assert client.get("/config/effective").status_code == 401


def test_propose_returns_202_with_pending_decision(client_and_port: Any) -> None:
    client, port = client_and_port
    r = client.post(
        "/config/proposals",
        json={"base_config_version": 1, "patch": {"sanity": {"z_gate": 7.0}}},
        headers=_h(),
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending_signature"
    assert port.decisions[body["decision_id"]].status == "pending_signature"


def test_propose_non_configurable_key_is_422(client_and_port: Any) -> None:
    client, _ = client_and_port
    r = client.post(
        "/config/proposals",
        json={"base_config_version": 1, "patch": {"money": {"supported_currencies": ["JPY"]}}},
        headers=_h(),
    )
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"] == "Non-configurable key"
    assert r.json()["reason"] == "non_configurable_key"


def test_propose_stale_version_is_409(client_and_port: Any) -> None:
    client, _ = client_and_port
    r = client.post(
        "/config/proposals",
        json={"base_config_version": 9, "patch": {"sanity": {"z_gate": 7.0}}},
        headers=_h(),
    )
    assert r.status_code == 409


def test_propose_without_signing_wired_is_501_not_a_silent_success() -> None:
    import asyncio

    repo = InMemoryConfigRepository()
    asyncio.run(seed(["tenant-a"], repo))
    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(config_api.router, prefix="/config")
    app.dependency_overrides[config_api.get_config_service] = lambda: TenantConfigService(
        repo, config_api.UnwiredDecisionPort(), FixedClock()
    )
    with TestClient(app) as client:
        r = client.post(
            "/config/proposals",
            json={"base_config_version": 1, "patch": {"sanity": {"z_gate": 7.0}}},
            headers=_h(),
        )
    assert r.status_code == 501
