"""D2-10: audit chain, endpoints, tamper detection and the WORM anchor."""

from __future__ import annotations

from datetime import datetime, timedelta

import psycopg
from sqlalchemy import select

from apex.api import audit as audit_api
from apex.audit import anchor, chain
from apex.audit.api import AuditEventInput
from apex.audit.api import append as append_event
from apex.db.models import ActorType, AuditEvent
from apex.db.session import tenant_session
from tests.signing.test_keys import (
    OTHER,
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


class FakeStore:
    """In-memory Object Lock: refuses to overwrite a key, like COMPLIANCE retention does."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, datetime]] = {}

    def put(self, key: str, body: bytes, retain_until: datetime) -> None:
        assert key not in self.objects, "locked object"
        self.objects[key] = (body, retain_until)

    def latest(self, prefix: str) -> tuple[str, bytes] | None:
        keys = sorted(k for k in self.objects if k.startswith(prefix))
        return (keys[-1], self.objects[keys[-1]][0]) if keys else None


async def _fill(h: Harness, tenant: str, n: int) -> None:
    async with tenant_session(tenant, sessionmaker=h.factory) as session:
        for i in range(n):
            await append_event(
                session,
                AuditEventInput(
                    tenant, ActorType.AGENT, "gate-agent", "offer.gated", f"offer:{i}", {"i": i}
                ),
                clock=h.clock,
            )


def _tamper(url: str, sql: str, *args: object) -> None:
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute("ALTER TABLE audit_events DISABLE TRIGGER USER")
        admin.execute(sql, args)
        admin.execute("ALTER TABLE audit_events ENABLE TRIGGER USER")


async def test_append_list_verify_and_roles(h: Harness) -> None:
    await _fill(h, TENANT, 5)
    h.as_user("alice", roles=("buyer",))
    assert (await h.client.get("/v1/audit")).status_code == 403
    h.as_user("alice", roles=("admin",))

    first = (await h.client.get("/v1/audit", params={"limit": 3})).json()
    assert [e["seq"] for e in first["items"]] == [5, 4, 3] and first["next_cursor"]
    rest = (
        await h.client.get("/v1/audit", params={"limit": 3, "cursor": first["next_cursor"]})
    ).json()
    assert [e["seq"] for e in rest["items"]] == [2, 1] and rest["next_cursor"] is None
    one = (await h.client.get("/v1/audit", params={"subject_ref": "offer:2"})).json()["items"]
    assert [e["seq"] for e in one] == [3]

    verdict = (await h.client.get("/v1/audit/verify")).json()
    assert (
        verdict["valid"]
        and verdict["checked_events"] == 5
        and verdict["anchored_head_hash"] is None
    )

    h.as_user(
        "dave", tenant=OTHER, roles=("admin",)
    )  # isolation: the other tenant sees an empty chain
    assert (await h.client.get("/v1/audit")).json()["items"] == []


async def test_tampering_with_any_row_is_detected(h: Harness, migrated_db: str) -> None:
    h.as_user("alice", roles=("admin",))
    for column, value in (("event_type", "x"), ("payload", '{"i": 99}'), ("hash", "f" * 64)):
        async with tenant_session(TENANT, sessionmaker=h.factory) as session:
            check = await chain.verify(session, TENANT)
        assert check.valid
        original = _read(migrated_db, column)
        _tamper(
            migrated_db,
            f"UPDATE audit_events SET {column} = %s WHERE tenant_id = %s AND seq = 3",
            value,
            TENANT,
        )
        verdict = (await h.client.get("/v1/audit/verify")).json()
        assert not verdict["valid"] and verdict["first_broken_seq"] in (3, 4), column
        _tamper(
            migrated_db,
            f"UPDATE audit_events SET {column} = %s WHERE tenant_id = %s AND seq = 3",
            original,
            TENANT,
        )
    _tamper(migrated_db, "DELETE FROM audit_events WHERE tenant_id = %s AND seq = 2", TENANT)
    verdict = (await h.client.get("/v1/audit/verify")).json()
    assert not verdict["valid"] and verdict["first_broken_seq"] == 3  # a gap in seq


def _read(url: str, column: str) -> str:
    with psycopg.connect(url) as conn:
        row = conn.execute(
            f"SELECT {column}::text FROM audit_events WHERE tenant_id = %s AND seq = 3", [TENANT]
        ).fetchone()
    assert row is not None
    return str(row[0])


async def test_anchor_detects_a_rewritten_chain(h: Harness, migrated_db: str) -> None:
    store = FakeStore()
    h.app.dependency_overrides[audit_api.get_anchor_store] = lambda: store
    h.as_user("dave", tenant=OTHER, roles=("owner",))
    await _fill(h, OTHER, 3)
    async with tenant_session(OTHER, sessionmaker=h.factory) as session:
        await anchor.anchor_head(session, store, OTHER, now=T0, retention=timedelta(days=365))
    ((_, (_, retain_until)),) = store.objects.items()
    assert retain_until == T0 + timedelta(days=365)

    verdict = (await h.client.get("/v1/audit/verify")).json()
    assert verdict["valid"] and verdict["anchored_head_hash"] and verdict["anchored_at"]

    # Rewrite the head and recompute its own hash: the chain is self-consistent again, the anchor is not.
    async with tenant_session(OTHER, sessionmaker=h.factory) as session:
        head = (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.tenant_id == OTHER, AuditEvent.seq == 3)
            )
        ).one()
        head.event_type = "rewritten"
        forged = chain.event_hash(head)
        session.expunge(head)
    _tamper(
        migrated_db,
        "UPDATE audit_events SET event_type = 'rewritten', hash = %s WHERE tenant_id = %s AND seq = 3",
        forged,
        OTHER,
    )
    verdict = (await h.client.get("/v1/audit/verify")).json()
    assert not verdict["valid"] and verdict["first_broken_seq"] == 3
    # A broken chain is never anchored.
    _tamper(
        migrated_db,
        "UPDATE audit_events SET event_type = 'x' WHERE tenant_id = %s AND seq = 1",
        OTHER,
    )
    broken = FakeStore()
    async with tenant_session(OTHER, sessionmaker=h.factory) as session:
        await anchor.anchor_head(session, broken, OTHER, now=T0, retention=timedelta(days=1))
    assert not broken.objects
