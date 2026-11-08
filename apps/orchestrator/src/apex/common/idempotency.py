"""Idempotency-Key middleware for unsafe methods (spec §8: idempotency keys en todas las escrituras).

Behaviour for POST/PUT/PATCH/DELETE carrying an ``Idempotency-Key`` header:

* First request: the key is claimed (marked in-flight), the request runs, and the response is stored.
* Same key, same request body hash, response already stored: the stored response is replayed.
* Same key, different body hash: 422 problem+json (the key was reused for a different request).
* Same key while the first request is still in flight: 409 problem+json.
* 5xx responses are not stored; the claim is released so the client may retry.

The scope of a key is ``(principal, method, path, key)``. The principal comes from
``principal_resolver``, a placeholder that returns ``"anonymous"`` until DEV-1's auth lands.

Missing key: writes are *not* rejected unless ``settings.idempotency_required`` is true (default
false, because DEV-6 is not ready yet). The middleware logs the missing key in that case.

Store and TTL are configuration: ``settings.idempotency_backend`` (``memory`` or ``redis``) and
``settings.idempotency_ttl_seconds``. No business default is hardcoded here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apex.common.errors import Problem

logger = logging.getLogger(__name__)

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
HEADER_NAME = "Idempotency-Key"
MAX_KEY_LENGTH = 255
ANONYMOUS_PRINCIPAL = "anonymous"

PrincipalResolver = Callable[[Scope], str]


def anonymous_principal(_scope: Scope) -> str:
    """Placeholder until DEV-1 supplies ``current_principal``."""
    return ANONYMOUS_PRINCIPAL


@dataclass(frozen=True)
class StoredResponse:
    status: int
    headers: list[tuple[str, str]]
    body_b64: str


@dataclass
class IdempotencyRecord:
    request_hash: str
    in_flight: bool = True
    response: StoredResponse | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class IdempotencyStore(Protocol):
    """Pluggable storage. ``claim`` is atomic: it returns None when the caller now owns the key."""

    async def claim(
        self, scope_key: str, request_hash: str, ttl_seconds: int
    ) -> IdempotencyRecord | None: ...

    async def complete(
        self, scope_key: str, response: StoredResponse, ttl_seconds: int
    ) -> None: ...

    async def release(self, scope_key: str) -> None: ...

    async def get(self, scope_key: str) -> IdempotencyRecord | None: ...


def _serialize_record(record: IdempotencyRecord) -> str:
    payload: dict[str, Any] = {
        "request_hash": record.request_hash,
        "in_flight": record.in_flight,
        "response": None,
    }
    if record.response is not None:
        payload["response"] = {
            "status": record.response.status,
            "headers": [list(h) for h in record.response.headers],
            "body_b64": record.response.body_b64,
        }
    return json.dumps(payload, sort_keys=True)


def _deserialize_record(raw: str | bytes) -> IdempotencyRecord:
    data = json.loads(raw)
    response = None
    if data.get("response") is not None:
        r = data["response"]
        response = StoredResponse(
            status=int(r["status"]),
            headers=[(str(k), str(v)) for k, v in r["headers"]],
            body_b64=str(r["body_b64"]),
        )
    return IdempotencyRecord(
        request_hash=str(data["request_hash"]),
        in_flight=bool(data["in_flight"]),
        response=response,
    )


class InMemoryIdempotencyStore:
    """Process-local store for tests and single-process dev runs. Ignores TTL expiry accounting
    beyond storing the value; tests construct it fresh."""

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}

    async def claim(
        self, scope_key: str, request_hash: str, ttl_seconds: int
    ) -> IdempotencyRecord | None:
        del ttl_seconds
        existing = self._records.get(scope_key)
        if existing is not None:
            return existing
        self._records[scope_key] = IdempotencyRecord(request_hash=request_hash)
        return None

    async def complete(self, scope_key: str, response: StoredResponse, ttl_seconds: int) -> None:
        del ttl_seconds
        record = self._records[scope_key]
        record.in_flight = False
        record.response = response

    async def release(self, scope_key: str) -> None:
        self._records.pop(scope_key, None)

    async def get(self, scope_key: str) -> IdempotencyRecord | None:
        return self._records.get(scope_key)


class RedisIdempotencyStore:
    """Redis-backed store (redis.asyncio). Claims use SET NX EX so they are atomic across workers."""

    _PREFIX = "idempotency:"

    def __init__(self, client: Any) -> None:
        # ``client`` is a redis.asyncio.Redis (or fakeredis.aioredis.FakeRedis in tests).
        self._redis = client

    def _key(self, scope_key: str) -> str:
        return f"{self._PREFIX}{scope_key}"

    async def claim(
        self, scope_key: str, request_hash: str, ttl_seconds: int
    ) -> IdempotencyRecord | None:
        marker = _serialize_record(IdempotencyRecord(request_hash=request_hash))
        claimed = await self._redis.set(self._key(scope_key), marker, nx=True, ex=ttl_seconds)
        if claimed:
            return None
        raw = await self._redis.get(self._key(scope_key))
        if raw is None:  # expired between the two calls: treat as a fresh claim next time
            return IdempotencyRecord(request_hash=request_hash, in_flight=True)
        return _deserialize_record(raw)

    async def complete(self, scope_key: str, response: StoredResponse, ttl_seconds: int) -> None:
        record = IdempotencyRecord(
            request_hash=(await self._get_record(scope_key)).request_hash,
            in_flight=False,
            response=response,
        )
        await self._redis.set(self._key(scope_key), _serialize_record(record), ex=ttl_seconds)

    async def release(self, scope_key: str) -> None:
        await self._redis.delete(self._key(scope_key))

    async def get(self, scope_key: str) -> IdempotencyRecord | None:
        raw = await self._redis.get(self._key(scope_key))
        return None if raw is None else _deserialize_record(raw)

    async def _get_record(self, scope_key: str) -> IdempotencyRecord:
        record = await self.get(scope_key)
        if record is None:
            raise KeyError(scope_key)
        return record


def _hash_request(method: str, path: str, query: bytes, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.encode())
    digest.update(b"\x00")
    digest.update(path.encode())
    digest.update(b"\x00")
    digest.update(query)
    digest.update(b"\x00")
    digest.update(body)
    return digest.hexdigest()


class IdempotencyMiddleware:
    """Pure ASGI middleware. Buffers the request body (to hash it) and replays it downstream."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        store: IdempotencyStore,
        ttl_seconds: int,
        required: bool = False,
        principal_resolver: PrincipalResolver = anonymous_principal,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("idempotency ttl must be >= 1 second")
        self.app = app
        self.store = store
        self.ttl_seconds = ttl_seconds
        self.required = required
        self.principal_resolver = principal_resolver

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        raw_key = _header(scope, HEADER_NAME)
        if raw_key is None:
            if self.required:
                await _write_problem(
                    send,
                    Problem(
                        400,
                        "Missing Idempotency-Key",
                        detail="This write requires an Idempotency-Key header.",
                    ),
                    scope,
                )
                return
            logger.info(
                "write without Idempotency-Key",
                extra={"method": scope["method"], "path": scope["path"]},
            )
            await self.app(scope, receive, send)
            return

        if not raw_key or len(raw_key) > MAX_KEY_LENGTH:
            await _write_problem(
                send,
                Problem(400, "Invalid Idempotency-Key", detail="Key must be 1-255 characters."),
                scope,
            )
            return

        body = await _read_body(receive)
        request_hash = _hash_request(
            scope["method"], scope["path"], scope.get("query_string", b""), body
        )
        scope_key = _scope_key(
            self.principal_resolver(scope), scope["method"], scope["path"], raw_key
        )

        existing = await self.store.claim(scope_key, request_hash, self.ttl_seconds)
        if existing is not None:
            if existing.request_hash != request_hash:
                await _write_problem(
                    send,
                    Problem(
                        422,
                        "Idempotency-Key reused",
                        detail="This Idempotency-Key was already used for a different request.",
                    ),
                    scope,
                )
                return
            if existing.in_flight or existing.response is None:
                await _write_problem(
                    send,
                    Problem(
                        409,
                        "Request in progress",
                        detail="A request with this Idempotency-Key is still being processed.",
                    ),
                    scope,
                )
                return
            await _replay(send, existing.response)
            return

        await self._run_and_store(scope, receive, send, body, scope_key)

    async def _run_and_store(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        body: bytes,
        scope_key: str,
    ) -> None:
        captured: dict[str, Any] = {"status": 500, "headers": [], "body": b""}
        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        async def capturing_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]
                captured["headers"] = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                captured["body"] += message.get("body", b"")
            await send(message)

        try:
            await self.app(scope, replay_receive, capturing_send)
        except BaseException:
            await self.store.release(scope_key)
            raise

        status = int(captured["status"])
        if status >= 500:
            await self.store.release(scope_key)
            return
        stored = StoredResponse(
            status=status,
            headers=[(k.decode("latin-1"), v.decode("latin-1")) for k, v in captured["headers"]],
            body_b64=base64.b64encode(captured["body"]).decode("ascii"),
        )
        await self.store.complete(scope_key, stored, self.ttl_seconds)


def _scope_key(principal: str, method: str, path: str, key: str) -> str:
    return "|".join((principal, method, path, key))


def _header(scope: Scope, name: str) -> str | None:
    wanted = name.lower().encode("latin-1")
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for k, v in headers:
        if k.lower() == wanted:
            return v.decode("latin-1").strip()
    return None


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


async def _replay(send: Send, stored: StoredResponse) -> None:
    body = base64.b64decode(stored.body_b64)
    headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in stored.headers]
    headers.append((b"idempotent-replayed", b"true"))
    await send({"type": "http.response.start", "status": stored.status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _write_problem(send: Send, problem: Problem, scope: Scope) -> None:
    details = problem.to_details(instance=scope.get("path"))
    body = json.dumps(details.model_dump(exclude_none=True)).encode("utf-8")
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/problem+json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    await send({"type": "http.response.start", "status": problem.status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


__all__ = [
    "HEADER_NAME",
    "InMemoryIdempotencyStore",
    "IdempotencyMiddleware",
    "IdempotencyRecord",
    "IdempotencyStore",
    "RedisIdempotencyStore",
    "StoredResponse",
    "anonymous_principal",
]
