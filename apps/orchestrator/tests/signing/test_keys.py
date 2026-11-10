"""D2-07: enroll, list and revoke signing keys; old signatures still verify; service keys from Transit."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

import httpx
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import FastAPI

from apex.api import keys as keys_api
from apex.auth.deps import current_principal
from apex.auth.models import Principal
from apex.common.clock import FixedClock
from apex.common.errors import Problem
from apex.contracts.generated.models import Decision, DecisionStatus, DecisionType
from apex.db.models import SigningKey
from apex.db.session import create_engine, create_sessionmaker, system_session
from apex.main import create_app
from apex.platform.vault import TransitPublicKey
from apex.signing import keys
from apex.signing.ed25519 import verify_payload
from apex.signing.jcs import canonical_bytes
from tests.db.conftest import app_db, migrated_db, postgres_available

__all__ = ["app_db", "migrated_db"]  # fixtures imported for pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not postgres_available(), reason="no Postgres: set APEX_TEST_PG_ADMIN_URL or start Docker"
    ),
]

T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
TENANT, OTHER = "tenant-keys-a", "tenant-keys-b"


def _asyncpg(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, "", ""))


@pytest.fixture(scope="module")
def seeded(migrated_db: str, app_db: str) -> str:
    with psycopg.connect(migrated_db, autocommit=True) as admin:
        for tenant in (TENANT, OTHER):
            admin.execute(
                "INSERT INTO tenants (id, name, country, base_currency, created_at, updated_at) "
                "VALUES (%s, %s, 'ES', 'EUR', %s, %s)",
                [tenant, tenant, T0, T0],
            )
        for user in ("alice", "bob", "carol", "dave", "erin"):
            admin.execute(
                "INSERT INTO users (id, email, display_name, external_subject, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [f"user-{user}", f"{user}@example.test", user, user, T0, T0],
            )
        members = [(TENANT, u) for u in ("alice", "bob", "carol", "erin")] + [(OTHER, "dave")]
        for tenant, user in members:
            admin.execute(
                "INSERT INTO memberships (id, tenant_id, user_id, role, created_at) "
                "VALUES (%s, %s, %s, 'buyer', %s)",
                [f"m-{user}", tenant, f"user-{user}", T0],
            )
    return app_db


class Signed:
    """A fake D2-09: every decision is the signed decision given to it."""

    def __init__(self) -> None:
        self.decision: Decision | None = None

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> Decision:
        assert self.decision is not None and self.decision.id == decision_id
        return self.decision


def _decision(subject_ref: str, type_: DecisionType = DecisionType.revoke_key) -> Decision:
    return Decision(
        id="dec-1",
        type=type_,
        subject_ref=subject_ref,
        status=DecisionStatus.signed,
        payload_canonical="{}",
        payload_hash="0" * 64,
        requires_immediate_reauth=True,
        required_signers=1,
        signatures=[],
        created_at=T0,
    )


class Harness:
    def __init__(self, app: FastAPI, client: httpx.AsyncClient, decisions: Signed) -> None:
        self.app, self.client, self.decisions = app, client, decisions
        self.as_user("alice")

    def as_user(
        self,
        user: str,
        *,
        tenant: str = TENANT,
        roles: tuple[str, ...] = ("buyer",),
        auth_at: datetime | None = T0,
    ) -> None:
        principal = Principal(
            user_id=user,
            tenant_id=tenant,
            roles=roles,
            auth_time=None if auth_at is None else int(auth_at.timestamp()),
        )
        self.app.dependency_overrides[current_principal] = lambda: principal

    async def enroll(self, private: Ed25519PrivateKey) -> httpx.Response:
        raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        body = {"public_key": base64.b64encode(raw).decode(), "alg": "Ed25519", "label": "laptop"}
        return await self.client.post("/v1/keys/me", json=body)


@pytest.fixture
async def h(seeded: str) -> AsyncIterator[Harness]:
    engine = create_engine(_asyncpg(seeded), pool_size=2)
    app = create_app()
    decisions = Signed()
    app.dependency_overrides[keys_api.get_sessionmaker] = lambda: create_sessionmaker(engine)
    app.dependency_overrides[keys_api.get_clock] = lambda: FixedClock(T0 + timedelta(minutes=5))
    app.dependency_overrides[keys_api.get_decision_verifier] = lambda: decisions
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        yield Harness(app, client, decisions)
    await engine.dispose()


async def test_enroll_revoke_and_old_signature_still_verifies(h: Harness) -> None:
    private = Ed25519PrivateKey.generate()
    enrolled = await h.enroll(private)
    assert enrolled.status_code == 201, enrolled.text
    key = enrolled.json()
    assert (
        key["owner_type"] == "human"
        and key["owner_id"] == "user-alice"
        and key["revoked_at"] is None
    )

    payload = {"decision": "approve_purchase", "amount_minor": 125000}
    signature = base64.b64encode(private.sign(canonical_bytes(payload))).decode()

    assert (await h.enroll(Ed25519PrivateKey.generate())).json()["code"] == "active_key_exists"

    h.decisions.decision = _decision(f"signing_key:{key['id']}")
    revoked = await h.client.post(f"/v1/keys/{key['id']}/revoke", json={"decision_id": "dec-1"})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked_at"] is not None
    again = await h.client.post(f"/v1/keys/{key['id']}/revoke", json={"decision_id": "dec-1"})
    assert again.json()["code"] == "key_already_revoked"

    listed = (await h.client.get("/v1/keys/me")).json()["items"]
    assert [k["id"] for k in listed] == [key["id"]]
    assert verify_payload(
        listed[0]["public_key"], signature, payload
    )  # revocation never breaks the past

    assert (
        await h.enroll(Ed25519PrivateKey.generate())
    ).status_code == 201  # new device after revoking


async def test_enroll_needs_fresh_step_up(h: Harness) -> None:
    h.as_user("bob", auth_at=None)
    assert (await h.enroll(Ed25519PrivateKey.generate())).json()["reason"] == "step_up_required"
    h.as_user(
        "bob", auth_at=T0 - timedelta(minutes=11)
    )  # 16 minutes before the clock, window is 15
    response = await h.enroll(Ed25519PrivateKey.generate())
    assert response.status_code == 428 and response.json()["error"] == "reauth_required"
    h.as_user("bob", roles=("viewer",))
    assert (await h.enroll(Ed25519PrivateKey.generate())).status_code == 403


async def test_enroll_rejects_malformed_or_reused_public_key(h: Harness) -> None:
    h.as_user("carol")
    bad = await h.client.post("/v1/keys/me", json={"public_key": "AAAA", "alg": "Ed25519"})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_public_key"
    private = Ed25519PrivateKey.generate()
    assert (await h.enroll(private)).status_code == 201
    h.as_user("dave", tenant=OTHER)
    assert (await h.enroll(private)).json()["code"] == "public_key_in_use"


async def test_revoke_checks_decision_owner_and_tenant(h: Harness) -> None:
    h.as_user("erin")
    key_id = (await h.enroll(Ed25519PrivateKey.generate())).json()["id"]
    url = f"/v1/keys/{key_id}/revoke"

    h.decisions.decision = _decision("signing_key:someone-else")
    assert (await h.client.post(url, json={"decision_id": "dec-1"})).json()[
        "code"
    ] == "decision_mismatch"
    h.decisions.decision = _decision(f"signing_key:{key_id}", DecisionType.rotate_key)
    assert (await h.client.post(url, json={"decision_id": "dec-1"})).json()[
        "code"
    ] == "decision_mismatch"

    h.decisions.decision = _decision(f"signing_key:{key_id}")
    h.as_user("alice")  # same tenant, not the owner, not an admin
    assert (await h.client.post(url, json={"decision_id": "dec-1"})).status_code == 403
    h.as_user("dave", tenant=OTHER, roles=("admin",))
    assert (await h.client.post(url, json={"decision_id": "dec-1"})).status_code == 404
    h.as_user("alice", roles=("admin",))  # lost-device path: an admin revokes
    assert (await h.client.post(url, json={"decision_id": "dec-1"})).status_code == 200


async def test_revoke_is_501_until_decisions_exist() -> None:
    with pytest.raises(Problem) as raised:
        await keys_api.get_decision_verifier().require_signed("d", tenant_id=TENANT)
    assert raised.value.status == 501


async def test_service_keys_are_versioned_and_idempotent(seeded: str) -> None:
    engine = create_engine(_asyncpg(seeded), pool_size=1)
    factory = create_sessionmaker(engine)

    def transit(version: int) -> TransitPublicKey:
        raw = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return TransitPublicKey(name="gate-agent", version=version, raw=raw)

    v1 = transit(1)
    async with system_session(sessionmaker=factory) as session:
        first = await keys.register_service_key(session, v1, now=T0)
        assert (
            (await keys.register_service_key(session, v1, now=T0)).id
            == first.id
            == "svc:gate-agent:v1"
        )
        await keys.register_service_key(session, transit(2), now=T0 + timedelta(days=1))
    async with system_session(sessionmaker=factory) as session:
        rows = await keys.list_owner_keys(session, "gate-agent")
        assert [(r.id, r.tenant_id, r.vault_key_ref) for r in rows] == [
            ("svc:gate-agent:v1", None, "gate-agent:1"),
            ("svc:gate-agent:v2", None, "gate-agent:2"),
        ]
        assert rows[0].rotated_at is not None and rows[1].rotated_at is None
        assert isinstance(rows[0], SigningKey)
    await engine.dispose()
