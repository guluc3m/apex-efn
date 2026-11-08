"""Idempotency-Key middleware: replay, body mismatch (422), in-flight (409), 5xx not stored."""

import asyncio
from typing import Any

import fakeredis
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from apex.common.errors import install_problem_handlers
from apex.common.idempotency import (
    IdempotencyMiddleware,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    RedisIdempotencyStore,
)

KEY = {"Idempotency-Key": "k-1"}


def _build(store: IdempotencyStore, *, required: bool = False) -> tuple[FastAPI, dict[str, int]]:
    app = FastAPI()
    install_problem_handlers(app)
    counter = {"calls": 0}

    @app.post("/items")
    async def create(request: Request) -> dict[str, Any]:
        counter["calls"] += 1
        body = await request.json()
        return {"n": counter["calls"], "echo": body}

    @app.post("/boom")
    async def boom() -> None:
        counter["calls"] += 1
        raise RuntimeError("secret internal detail")

    app.add_middleware(IdempotencyMiddleware, store=store, ttl_seconds=60, required=required)
    return app, counter


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


def test_first_request_runs_and_second_is_replayed(store: InMemoryIdempotencyStore) -> None:
    app, counter = _build(store)
    client = TestClient(app)

    first = client.post("/items", json={"a": 1}, headers=KEY)
    second = client.post("/items", json={"a": 1}, headers=KEY)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.headers["idempotent-replayed"] == "true"
    assert counter["calls"] == 1


def test_same_key_different_body_is_422(store: InMemoryIdempotencyStore) -> None:
    app, counter = _build(store)
    client = TestClient(app)
    client.post("/items", json={"a": 1}, headers=KEY)

    response = client.post("/items", json={"a": 2}, headers=KEY)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Idempotency-Key reused"
    assert counter["calls"] == 1


def test_in_flight_request_gets_409(store: InMemoryIdempotencyStore) -> None:
    async def scenario() -> None:
        # Simulate a first request that has claimed the key but not completed yet.
        from apex.common.idempotency import _hash_request

        body = b'{"a":1}'
        request_hash = _hash_request("POST", "/items", b"", body)
        scope_key = "anonymous|POST|/items|k-1"
        assert await store.claim(scope_key, request_hash, 60) is None

        app, counter = _build(store)
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            response = await c.post(
                "/items", content=body, headers={**KEY, "content-type": "application/json"}
            )

        assert response.status_code == 409
        assert response.json()["title"] == "Request in progress"
        assert counter["calls"] == 0

    asyncio.run(scenario())


def test_server_error_is_not_stored_so_retry_runs_again(store: InMemoryIdempotencyStore) -> None:
    app, counter = _build(store)
    client = TestClient(app, raise_server_exceptions=False)

    failed = client.post("/boom", json={}, headers={"Idempotency-Key": "b-1"})
    retried = client.post("/boom", json={}, headers={"Idempotency-Key": "b-1"})

    assert failed.status_code == 500
    assert retried.status_code == 500
    assert counter["calls"] == 2


def test_500_body_does_not_leak_internals(store: InMemoryIdempotencyStore) -> None:
    app, _ = _build(store)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/boom", json={}, headers={"Idempotency-Key": "b-2"})
    assert "secret internal detail" not in response.text
    assert response.json()["title"] == "Internal server error"


def test_keys_are_scoped_per_path(store: InMemoryIdempotencyStore) -> None:
    app, counter = _build(store)
    client = TestClient(app)
    client.post("/items", json={"a": 1}, headers=KEY)
    client.post("/items", json={"a": 1}, headers={"Idempotency-Key": "k-1"})
    assert counter["calls"] == 1


def test_missing_key_is_allowed_when_not_required(store: InMemoryIdempotencyStore) -> None:
    app, counter = _build(store, required=False)
    client = TestClient(app)
    client.post("/items", json={"a": 1})
    client.post("/items", json={"a": 1})
    assert counter["calls"] == 2


def test_missing_key_is_rejected_when_required(store: InMemoryIdempotencyStore) -> None:
    app, counter = _build(store, required=True)
    client = TestClient(app)
    response = client.post("/items", json={"a": 1})
    assert response.status_code == 400
    assert response.json()["title"] == "Missing Idempotency-Key"
    assert counter["calls"] == 0


def test_get_requests_bypass_the_store(store: InMemoryIdempotencyStore) -> None:
    app = FastAPI()

    @app.get("/x")
    async def read() -> dict[str, str]:
        return {"ok": "yes"}

    app.add_middleware(IdempotencyMiddleware, store=store, ttl_seconds=60)
    response = TestClient(app).get("/x", headers=KEY)
    assert response.status_code == 200
    assert response.json() == {"ok": "yes"}


def test_redis_store_replays_and_mismatches() -> None:
    redis = fakeredis.FakeAsyncRedis()
    app, counter = _build(RedisIdempotencyStore(redis))
    client = TestClient(app)

    first = client.post("/items", json={"a": 1}, headers={"Idempotency-Key": "r-1"})
    replay = client.post("/items", json={"a": 1}, headers={"Idempotency-Key": "r-1"})
    mismatch = client.post("/items", json={"a": 9}, headers={"Idempotency-Key": "r-1"})

    assert first.json() == replay.json()
    assert replay.headers["idempotent-replayed"] == "true"
    assert mismatch.status_code == 422
    assert counter["calls"] == 1


def test_redis_store_claim_is_atomic_and_ttl_applied() -> None:
    async def scenario() -> None:
        redis = fakeredis.FakeAsyncRedis()
        store = RedisIdempotencyStore(redis)
        assert await store.claim("s", "h", 30) is None
        existing = await store.claim("s", "h", 30)
        assert existing is not None and existing.in_flight
        ttl = await redis.ttl("idempotency:s")
        assert 0 < ttl <= 30

    asyncio.run(scenario())


def test_ttl_must_be_positive() -> None:
    with pytest.raises(ValueError):
        IdempotencyMiddleware(FastAPI(), store=InMemoryIdempotencyStore(), ttl_seconds=0)
