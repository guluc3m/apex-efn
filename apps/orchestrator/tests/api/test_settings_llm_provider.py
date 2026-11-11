"""HTTP contract for the tenant LLM provider settings (dashboard settings page backend).

The tests mount the router exactly as ``api/__init__.py`` does (prefix ``/settings`` under ``/v1``) and
override the tenant/store/transport dependencies, so no authentication or network is involved. The
``/test`` endpoint is driven by an ``httpx.MockTransport``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from apex.api import settings as settings_api
from apex.common.clock import FixedClock
from apex.common.errors import install_problem_handlers
from apex.llm.provider_store import TenantProviderStore

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
SECRET = "sk-live-SECRET-0123456789"
EMPTY = {"base_url": None, "model": None, "api_key_set": False, "updated_at": None}


@pytest.fixture
def store() -> TenantProviderStore:
    return TenantProviderStore(clock=FixedClock(NOW))


def _app(
    store: TenantProviderStore, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(settings_api.router, prefix="/v1/settings")
    app.dependency_overrides[settings_api.get_tenant_id] = lambda: TENANT
    app.dependency_overrides[settings_api.get_provider_store] = lambda: store
    if transport is not None:
        app.dependency_overrides[settings_api.get_http_transport] = lambda: transport
    return app


def _client(
    store: TenantProviderStore, transport: httpx.AsyncBaseTransport | None = None
) -> TestClient:
    return TestClient(_app(store, transport))


def _seed(store: TenantProviderStore) -> None:
    store.set(
        TENANT,
        base_url="https://api.example.com",
        model="deepseek-chat",
        api_key=SecretStr(SECRET),
    )


# ---------------------------------------------------------------------------
# GET / PUT / DELETE
# ---------------------------------------------------------------------------


def test_get_returns_the_empty_shape_when_unset(store: TenantProviderStore) -> None:
    response = _client(store).get("/v1/settings/llm-provider")
    assert response.status_code == 200
    assert response.json() == EMPTY


def test_put_then_get_never_exposes_the_key(store: TenantProviderStore) -> None:
    client = _client(store)
    response = client.put(
        "/v1/settings/llm-provider",
        json={
            "base_url": "https://api.example.com/v1",
            "model": "deepseek-chat",
            "api_key": SECRET,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["base_url"] == "https://api.example.com/v1"
    assert body["model"] == "deepseek-chat"
    assert body["api_key_set"] is True
    assert body["updated_at"] is not None
    assert SECRET not in response.text

    fetched = client.get("/v1/settings/llm-provider")
    assert fetched.status_code == 200
    assert fetched.json() == body
    assert SECRET not in fetched.text
    assert store.get(TENANT) is not None
    assert store.get(TENANT).api_key is not None
    assert store.get(TENANT).api_key.get_secret_value() == SECRET


def test_put_without_api_key_keeps_the_existing_one(store: TenantProviderStore) -> None:
    client = _client(store)
    client.put(
        "/v1/settings/llm-provider",
        json={"base_url": "https://one.example", "model": "m1", "api_key": SECRET},
    )

    omitted = client.put(
        "/v1/settings/llm-provider",
        json={"base_url": "https://two.example", "model": "m2"},
    )
    assert omitted.status_code == 200
    assert omitted.json()["api_key_set"] is True
    stored = store.get(TENANT)
    assert stored is not None and stored.api_key is not None
    assert stored.api_key.get_secret_value() == SECRET

    empty = client.put(
        "/v1/settings/llm-provider",
        json={"base_url": "https://three.example", "model": "m3", "api_key": ""},
    )
    assert empty.status_code == 200
    assert empty.json()["api_key_set"] is True
    stored = store.get(TENANT)
    assert stored is not None and stored.api_key is not None
    assert stored.api_key.get_secret_value() == SECRET


def test_put_with_explicit_null_clears_the_key(store: TenantProviderStore) -> None:
    client = _client(store)
    client.put(
        "/v1/settings/llm-provider",
        json={"base_url": "https://api.example.com", "model": "m", "api_key": SECRET},
    )
    response = client.put(
        "/v1/settings/llm-provider",
        json={"base_url": "https://api.example.com", "model": "m", "api_key": None},
    )
    assert response.status_code == 200
    assert response.json()["api_key_set"] is False
    stored = store.get(TENANT)
    assert stored is not None
    assert stored.api_key is None


def test_delete_forgets_the_settings_and_is_idempotent(store: TenantProviderStore) -> None:
    _seed(store)
    client = _client(store)

    response = client.delete("/v1/settings/llm-provider")
    assert response.status_code == 204
    assert response.content == b""
    assert store.get(TENANT) is None
    assert client.get("/v1/settings/llm-provider").json() == EMPTY

    assert client.delete("/v1/settings/llm-provider").status_code == 204


@pytest.mark.parametrize(
    "payload",
    [
        {"base_url": "ftp://api.example.com", "model": "m"},
        {"base_url": "api.example.com", "model": "m"},
        {"base_url": "https://api.example.com", "model": ""},
        {"base_url": "https://api.example.com", "model": "   "},
    ],
)
def test_put_validates_base_url_and_model(
    store: TenantProviderStore, payload: dict[str, str]
) -> None:
    response = _client(store).put("/v1/settings/llm-provider", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert store.get(TENANT) is None


# ---------------------------------------------------------------------------
# POST /test
# ---------------------------------------------------------------------------


def test_test_endpoint_calls_v1_models_with_the_bearer_key(
    store: TenantProviderStore,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "model-a"}, {"id": "model-b"}]},
        )

    _seed(store)
    response = _client(store, httpx.MockTransport(handler)).post(
        "/v1/settings/llm-provider/test"
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "models": ["model-a", "model-b"], "error": None}
    assert SECRET not in response.text
    assert str(seen[0].url) == "https://api.example.com/v1/models"
    assert seen[0].headers["authorization"] == f"Bearer {SECRET}"


def test_test_endpoint_normalises_a_trailing_v1(store: TenantProviderStore) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    store.set(
        TENANT,
        base_url="https://api.example.com/v1/",
        model="m",
        api_key=SecretStr(SECRET),
    )
    response = _client(store, httpx.MockTransport(handler)).post(
        "/v1/settings/llm-provider/test"
    )
    assert response.status_code == 200
    assert str(seen[0].url) == "https://api.example.com/v1/models"


def test_test_endpoint_reports_provider_errors_without_the_key(
    store: TenantProviderStore,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    _seed(store)
    response = _client(store, httpx.MockTransport(handler)).post(
        "/v1/settings/llm-provider/test"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["models"] == []
    assert body["error"] is not None
    assert SECRET not in response.text


def test_test_endpoint_reports_timeouts(store: TenantProviderStore) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    _seed(store)
    response = _client(store, httpx.MockTransport(handler)).post(
        "/v1/settings/llm-provider/test"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["models"] == []
    assert "timed out" in body["error"]


def test_test_endpoint_without_settings_answers_with_a_reason(
    store: TenantProviderStore,
) -> None:
    response = _client(store).post("/v1/settings/llm-provider/test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["models"] == []
    assert body["error"] is not None


# ---------------------------------------------------------------------------
# Mounting
# ---------------------------------------------------------------------------


def test_router_is_mounted_at_the_settings_prefix() -> None:
    from apex.config import Settings
    from apex.main import create_app

    paths = create_app(Settings(idempotency_backend="memory")).openapi()["paths"]
    assert "/v1/settings/llm-provider" in paths
    assert "/v1/settings/llm-provider/test" in paths
