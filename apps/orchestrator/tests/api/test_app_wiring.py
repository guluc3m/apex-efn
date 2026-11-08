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
    """The middleware must not reject a write that omits the header; the route's own answer comes through.

    Uses a route that is still a 501 stub (D4-08 implemented ``/v1/missions``, which now answers 401
    because the dev tenant header is closed).
    """
    app = create_app(Settings(), store=InMemoryIdempotencyStore())
    response = TestClient(app).post("/v1/negotiations/n-1/takeover", json={})
    assert response.status_code == 501
