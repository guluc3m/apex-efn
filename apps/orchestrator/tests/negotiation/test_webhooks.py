"""Platform webhooks (D5-11): HMAC authentication, deduplication and the contract's body."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.api import webhooks as webhooks_api
from apex.common.errors import install_problem_handlers
from apex.negotiation.webhooks import (
    InMemoryReplayGuard,
    WebhookRejected,
    secret_for,
    sign,
    verify_signature,
)

SECRET = "a" * 40
PLATFORM = "mock-a"
BODY: dict[str, Any] = {
    "event_type": "seller_message",
    "platform_ref": "evt-1",
    "occurred_at": "2026-11-11T09:00:00Z",
    "data": {"negotiation_id": "n-1", "text": "hello"},
}


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.setenv("APEX_WEBHOOK_SECRET_MOCK_A", SECRET)
    application = FastAPI()
    install_problem_handlers(application)
    application.include_router(webhooks_api.router, prefix="/webhooks")
    # A fresh guard per test: the module-level one would leak "already seen" refs between tests.
    guard = InMemoryReplayGuard()
    application.dependency_overrides[webhooks_api.get_replay_guard] = lambda: guard
    yield application


def _post(client: TestClient, body: dict[str, Any] | None = None, *, signature: str | None = None):
    raw = json.dumps(body or BODY).encode()
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Platform-Signature"] = signature
    return client.post(f"/webhooks/platforms/{PLATFORM}", content=raw, headers=headers)


# ----- the signature ------------------------------------------------------------------------------


def test_the_secret_is_read_from_the_platform_specific_env_var() -> None:
    assert secret_for("mock-a", {"APEX_WEBHOOK_SECRET_MOCK_A": "x"}) == "x"
    assert secret_for("mock.a", {"APEX_WEBHOOK_SECRET_MOCK_A": "x"}) == "x"
    assert secret_for("mock-a", {}) is None


def test_a_valid_signature_is_accepted() -> None:
    verify_signature(SECRET, b"body", sign(SECRET, b"body"))


def test_the_sha256_prefix_is_tolerated() -> None:
    verify_signature(SECRET, b"body", "sha256=" + sign(SECRET, b"body"))


def test_a_missing_signature_is_rejected() -> None:
    with pytest.raises(WebhookRejected) as caught:
        verify_signature(SECRET, b"body", None)
    assert caught.value.reason == "missing_signature"


def test_a_wrong_signature_is_rejected() -> None:
    with pytest.raises(WebhookRejected) as caught:
        verify_signature(SECRET, b"body", sign("other-secret", b"body"))
    assert caught.value.reason == "invalid_signature"


# ----- the endpoint -------------------------------------------------------------------------------


def test_a_signed_event_is_accepted(app: FastAPI) -> None:
    raw = json.dumps(BODY).encode()
    with TestClient(app) as client:
        response = client.post(
            f"/webhooks/platforms/{PLATFORM}",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Platform-Signature": sign(SECRET, raw),
            },
        )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "platform_ref": "evt-1"}


def test_an_unsigned_event_is_401(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = _post(client)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["reason"] == "missing_signature"


def test_a_body_that_does_not_match_the_signature_is_401(app: FastAPI) -> None:
    raw = json.dumps(BODY).encode()
    tampered = json.dumps({**BODY, "data": {"text": "changed"}}).encode()
    with TestClient(app) as client:
        response = client.post(
            f"/webhooks/platforms/{PLATFORM}",
            content=tampered,
            headers={
                "Content-Type": "application/json",
                "X-Platform-Signature": sign(SECRET, raw),
            },
        )
    assert response.status_code == 401
    assert response.json()["reason"] == "invalid_signature"


def test_a_platform_without_a_secret_is_404(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/webhooks/platforms/unknown",
            content=json.dumps(BODY).encode(),
            headers={"Content-Type": "application/json", "X-Platform-Signature": "x"},
        )
    assert response.status_code == 404
    assert response.json()["reason"] == "unknown_platform"


def test_a_duplicate_event_is_accepted_and_ignored(app: FastAPI) -> None:
    """Platforms retry; the same platform_ref must not become a second state change."""
    raw = json.dumps(BODY).encode()
    headers = {"Content-Type": "application/json", "X-Platform-Signature": sign(SECRET, raw)}
    with TestClient(app) as client:
        first = client.post(f"/webhooks/platforms/{PLATFORM}", content=raw, headers=headers)
        second = client.post(f"/webhooks/platforms/{PLATFORM}", content=raw, headers=headers)
    assert first.json()["status"] == "accepted"
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"


@pytest.mark.parametrize(
    "body",
    [
        {"platform_ref": "e", "occurred_at": "2026-11-11T09:00:00Z"},
        {"event_type": "x", "occurred_at": "2026-11-11T09:00:00Z"},
        {"event_type": "x", "platform_ref": "e"},
        {"event_type": "x", "platform_ref": "e", "occurred_at": "not-a-date"},
    ],
)
def test_a_malformed_body_is_422(app: FastAPI, body: dict[str, Any]) -> None:
    raw = json.dumps(body).encode()
    with TestClient(app) as client:
        response = client.post(
            f"/webhooks/platforms/{PLATFORM}",
            content=raw,
            headers={"Content-Type": "application/json", "X-Platform-Signature": sign(SECRET, raw)},
        )
    assert response.status_code == 422


def test_a_body_that_is_not_json_is_422(app: FastAPI) -> None:
    raw = b"not json"
    with TestClient(app) as client:
        response = client.post(
            f"/webhooks/platforms/{PLATFORM}",
            content=raw,
            headers={"Content-Type": "application/json", "X-Platform-Signature": sign(SECRET, raw)},
        )
    assert response.status_code == 422
