"""D2-12 (ADR-210): export, erasure keeps the chains verifiable, retention never invents a period."""

from __future__ import annotations

from datetime import timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apex import gdpr
from apex.audit import chain
from apex.audit.api import AuditEventInput
from apex.audit.api import append as append_event
from apex.db.models import ActorType, User
from apex.db.session import tenant_session
from tests.signing.test_keys import (
    T0,
    TENANT,
    Harness,
    app_db,
    h,
    migrated_db,
    pytestmark,
    seeded,
)

__all__ = ["app_db", "h", "migrated_db", "pytestmark", "seeded"]  # fixtures and marks for pytest

NOW = T0 + timedelta(days=400)


async def test_export_then_erase_keeps_the_audit_chain_verifiable(h: Harness) -> None:
    h.as_user("erin")
    key_id = (await h.enroll(Ed25519PrivateKey.generate())).json()["id"]
    opened = await h.client.post(
        "/v1/signing-sessions", json={"key_id": key_id, "device_fingerprint_ref": "device-erin"}
    )
    assert opened.status_code == 201
    async with tenant_session(TENANT, sessionmaker=h.factory) as db:
        await append_event(
            db,
            AuditEventInput(TENANT, ActorType.HUMAN, "user-erin", "offer.followed", "offer:1", {}),
            clock=h.clock,
        )

    async with tenant_session(TENANT, sessionmaker=h.factory) as db:
        dump = await gdpr.export_subject(db, "user-erin")
        assert dump["user"]["email"] == "erin@example.test"
        assert [k["id"] for k in dump["keys"]] == [key_id]
        assert dump["signing_sessions"][0]["device_fingerprint_ref"] == "device-erin"
        assert [e["event_type"] for e in dump["audit_events"]] == ["offer.followed"]
        assert (await chain.verify(db, TENANT)).valid

    async with tenant_session(TENANT, sessionmaker=h.factory) as db:
        await gdpr.erase_subject(db, "user-erin", now=NOW)

    async with tenant_session(TENANT, sessionmaker=h.factory) as db:
        user = await db.get(User, "user-erin")
        assert user is not None and user.email.startswith("erased+") and user.external_subject is None
        dump = await gdpr.export_subject(db, "user-erin")
        assert dump["keys"][0]["revoked_at"] is not None and dump["keys"][0]["label"] is None
        assert dump["signing_sessions"][0]["device_fingerprint_ref"] == "erased"
        assert dump["signing_sessions"][0]["status"] != "active"
        assert (await chain.verify(db, TENANT)).valid  # chains untouched


def test_retention_unset_means_keep() -> None:
    assert gdpr.retention_cutoff({}, "sessions", now=NOW) is None
    assert gdpr.retention_cutoff({"sessions": None}, "sessions", now=NOW) is None
    assert gdpr.retention_cutoff({"sessions": 30}, "sessions", now=NOW) == NOW - timedelta(days=30)


async def test_purge_clears_only_old_ended_fingerprints(h: Harness) -> None:
    h.as_user("alice")
    key_id = (await h.enroll(Ed25519PrivateKey.generate())).json()["id"]
    sid = (
        await h.client.post(
            "/v1/signing-sessions", json={"key_id": key_id, "device_fingerprint_ref": "device-a"}
        )
    ).json()["id"]
    await h.client.delete(f"/v1/signing-sessions/{sid}")
    async with tenant_session(TENANT, sessionmaker=h.factory) as db:
        assert await gdpr.purge_session_fingerprints(db, h.clock.now() - timedelta(days=1)) == 0
        assert await gdpr.purge_session_fingerprints(db, h.clock.now() + timedelta(days=1)) >= 1
