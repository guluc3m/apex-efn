"""App shell wiring: problem handlers, idempotency middleware, /health, store selection."""

from fastapi.testclient import TestClient

from apex.common.idempotency import InMemoryIdempotencyStore, RedisIdempotencyStore
from apex.config import Settings
from apex.main import build_idempotency_store, create_app


def test_health_is_unversioned_and_ok() -> None:
    response = TestClient(create_app(Settings())).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_unknown_route_is_problem_json_404() -> None:
    response = TestClient(create_app(Settings())).get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_store_selected_from_settings() -> None:
    assert isinstance(
        build_idempotency_store(Settings(idempotency_backend="memory")), InMemoryIdempotencyStore
    )
    redis_store = build_idempotency_store(Settings(idempotency_backend="redis"))
    assert isinstance(redis_store, RedisIdempotencyStore)


def test_writes_without_key_pass_through_by_default() -> None:
    app = create_app(Settings(), store=InMemoryIdempotencyStore())
    response = TestClient(app).post("/v1/missions", json={})
    assert response.status_code == 501
