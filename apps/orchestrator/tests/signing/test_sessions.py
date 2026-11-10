"""D2-08: the fixed signing window. Criteria 19, 20 and 22, with an injected clock and no sleeps."""

from __future__ import annotations

from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apex.db.models import ReauthReason
from apex.db.session import tenant_session
from apex.signing import sessions
from apex.signing.sessions import ReauthRequired
from tests.signing.test_keys import (
    T0,
    TENANT,
    Harness,
    _decision,
    app_db,
    h,
    migrated_db,
    pytestmark,
    seeded,
)

__all__ = ["app_db", "h", "migrated_db", "pytestmark", "seeded"]  # fixtures and marks for pytest

DEVICE = "device-1"


async def _open(h: Harness, user: str) -> tuple[str, str]:
    """Enroll a key for ``user`` and open a window authenticated at T0. Returns (key_id, session_id)."""
    h.as_user(user)
    h.clock.set(T0 + timedelta(minutes=1))
    key_id = (await h.enroll(Ed25519PrivateKey.generate())).json()["id"]
    opened = await h.client.post(
        "/v1/signing-sessions", json={"key_id": key_id, "device_fingerprint_ref": DEVICE}
    )
    assert opened.status_code == 201, opened.text
    body = opened.json()
    assert body["status"] == "active" and body["remaining_decisions"] == 10
    return key_id, body["id"]


async def _sign(
    h: Harness, user: str, key_id: str, session_id: str, decision: str, device: str = DEVICE
) -> list[str]:
    async with tenant_session(TENANT, sessionmaker=h.factory) as db:
        row = await sessions.consume(
            db,
            session_id,
            user_id=f"user-{user}",
            key_id=key_id,
            device_fingerprint_ref=device,
            decision_id=decision,
            now=h.clock.now(),
        )
        return list(row.decisions_signed or [])


async def _refused(
    h: Harness, user: str, key_id: str, session_id: str, device: str = DEVICE
) -> ReauthReason:
    with pytest.raises(ReauthRequired) as raised:
        await _sign(h, user, key_id, session_id, "dec-late", device)
    return raised.value.reason


async def test_window_signs_many_then_expires_at_fifteen_minutes(
    h: Harness,
) -> None:  # criterion 19, 20
    key_id, session_id = await _open(h, "alice")
    expires_at = (await h.client.get(f"/v1/signing-sessions/{session_id}")).json()["expires_at"]
    for minute, decision in [(2, "dec-1"), (8, "dec-2"), (14, "dec-3")]:
        h.clock.set(T0 + timedelta(minutes=minute, seconds=59))
        await _sign(h, "alice", key_id, session_id, decision)
    view = (await h.client.get(f"/v1/signing-sessions/{session_id}")).json()
    assert view["expires_at"] == expires_at  # signing never slides the window
    assert (
        view["decisions_signed"] == ["dec-1", "dec-2", "dec-3"] and view["remaining_decisions"] == 7
    )

    h.clock.set(T0 + timedelta(minutes=15))
    assert await _refused(h, "alice", key_id, session_id) is ReauthReason.SESSION_EXPIRED
    view = (await h.client.get(f"/v1/signing-sessions/{session_id}")).json()
    assert view["status"] == "expired" and view["revoked_reason"] == "session_expired"


async def test_reaching_max_decisions_ends_the_session(h: Harness) -> None:  # criterion 20
    key_id, session_id = await _open(h, "bob")
    for n in range(10):
        await _sign(h, "bob", key_id, session_id, f"dec-{n}")
    assert await _refused(h, "bob", key_id, session_id) is ReauthReason.SESSION_EXHAUSTED
    assert (await h.client.get(f"/v1/signing-sessions/{session_id}")).json()[
        "status"
    ] == "exhausted"


async def test_revoking_the_key_kills_the_session(h: Harness) -> None:  # criterion 22
    key_id, session_id = await _open(h, "carol")
    await _sign(h, "carol", key_id, session_id, "dec-1")
    h.decisions.decision = _decision(f"signing_key:{key_id}")
    assert (
        await h.client.post(f"/v1/keys/{key_id}/revoke", json={"decision_id": "dec-1"})
    ).status_code == 200
    assert await _refused(h, "carol", key_id, session_id) is ReauthReason.KEY_REVOKED
    view = (await h.client.get(f"/v1/signing-sessions/{session_id}")).json()
    assert view["status"] == "revoked" and view["revoked_reason"] == "key_revoked"


async def test_another_device_kills_the_session(h: Harness) -> None:  # criterion 22
    key_id, session_id = await _open(h, "erin")
    assert (
        await _refused(h, "erin", key_id, session_id, device="device-2")
        is ReauthReason.DEVICE_MISMATCH
    )
    assert (
        await _refused(h, "erin", key_id, session_id) is ReauthReason.DEVICE_MISMATCH
    )  # stays dead


async def test_open_close_and_risk_flag(h: Harness) -> None:
    h.as_user("alice", auth_at=T0 - timedelta(minutes=20))
    h.clock.set(T0)
    stale = await h.client.post(
        "/v1/signing-sessions", json={"key_id": "x", "device_fingerprint_ref": DEVICE}
    )
    assert stale.status_code == 428 and stale.json()["reason"] == "step_up_required"

    key_id, session_id = await _open(h, "frank")
    h.as_user("alice")
    assert (await h.client.get(f"/v1/signing-sessions/{session_id}")).status_code == 404
    foreign = await h.client.post(
        "/v1/signing-sessions", json={"key_id": key_id, "device_fingerprint_ref": DEVICE}
    )
    assert foreign.status_code == 422

    h.as_user("frank")
    closed = await h.client.delete(f"/v1/signing-sessions/{session_id}")
    assert closed.json()["status"] == "closed" and closed.json()["remaining_decisions"] == 0
    assert await _refused(h, "frank", key_id, session_id) is ReauthReason.SESSION_REVOKED

    opened = await h.client.post(
        "/v1/signing-sessions", json={"key_id": key_id, "device_fingerprint_ref": DEVICE}
    )
    risky_id = opened.json()["id"]
    async with tenant_session(TENANT, sessionmaker=h.factory) as db:
        assert await sessions.mark_session_risky(db, risky_id, now=h.clock.now())
    assert await _refused(h, "frank", key_id, risky_id) is ReauthReason.RISK_FLAGGED
