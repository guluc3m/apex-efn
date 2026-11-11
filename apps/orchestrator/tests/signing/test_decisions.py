"""D2-09: decisions, signatures, the per-tenant chain and dual control. Criteria 17, 18, 21 and 23."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any

import httpx
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from apex.api import keys as keys_api
from apex.db.models import DecisionStatus, Signature
from apex.db.session import tenant_session
from apex.platform.vault import TransitPublicKey, TransitSignature
from apex.signing import decisions, jcs
from apex.signing.api import PendingSignature, SignatureInvalid, SigningService
from apex.tenant_config.errors import ConfigKeyUnset
from tests.signing.test_keys import T0, TENANT, Harness, app_db, h, migrated_db, pytestmark, seeded

__all__ = ["app_db", "h", "migrated_db", "pytestmark", "seeded"]  # fixtures and marks for pytest

DEVICE = "device-1"


def eur(minor: int) -> dict[str, Any]:
    return {"amount_minor": minor, "currency": "EUR"}


class Limits:
    config_version = 7

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def require(self, path: str) -> Any:
        if self.values.get(path) is None:
            raise ConfigKeyUnset(path)
        return self.values[path]


class Cfg:
    """ADR-900 demo values: dual control above EUR 20,000, immediate reauth above EUR 10,000."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {
            "approval.dual_control_above": eur(2_000_000),
            "signing.high_value_reauth_above": eur(1_000_000),
        }

    async def effective(self, tenant_id: str) -> Limits:
        return Limits(self.values)


def gate(amount_minor: int, score: int = 82) -> dict[str, Any]:
    return {
        "action": "approve",
        "offer_id": "offer-1",
        "mission_id": "mission-1",
        "amount": eur(amount_minor),
        "price_sanity": {"band": "normal", "config_version": 7},
        "seller_confidence": {"score": score, "band": "high", "model_version": "trust-v1"},
        "financial_verdict": "within_budget",
        "config_version": 7,
    }


class Desk:
    """Users with enrolled keys who open windows and sign over HTTP."""

    def __init__(self, h: Harness) -> None:
        self.h, self.cfg, self.keys = h, Cfg(), dict[str, tuple[Ed25519PrivateKey, str]]()
        self.service = SigningService(h.factory, self.cfg, h.clock)
        h.app.dependency_overrides[keys_api.get_signing_service] = lambda: self.service
        h.app.dependency_overrides.pop(keys_api.get_decision_verifier)  # the real require_signed

    async def window(self, user: str, at: datetime) -> str:
        """A step-up at ``at`` (the clock moves there) and a window opened on it."""
        self.h.clock.set(at)
        self.h.as_user(user, auth_at=at)
        if user not in self.keys:
            private = Ed25519PrivateKey.generate()
            self.keys[user] = (private, (await self.h.enroll(private)).json()["id"])
        opened = await self.h.client.post(
            "/v1/signing-sessions",
            json={"key_id": self.keys[user][1], "device_fingerprint_ref": DEVICE},
        )
        assert opened.status_code == 201, opened.text
        return str(opened.json()["id"])

    async def create(
        self,
        user: str,
        type_: str,
        params: dict[str, Any],
        subject: str = "offer:mission-1:offer-1",
    ) -> httpx.Response:
        self.h.as_user(user)
        return await self.h.client.post(
            "/v1/decisions", json={"type": type_, "subject_ref": subject, "params": params}
        )

    async def sign(
        self,
        user: str,
        decision: dict[str, Any],
        session_id: str,
        *,
        signature: str | None = None,
        payload_hash: str | None = None,
    ) -> httpx.Response:
        private, key_id = self.keys[user]
        self.h.as_user(user)
        body = {
            "key_id": key_id,
            "payload_hash": payload_hash or decision["payload_hash"],
            "signature": signature
            or base64.b64encode(private.sign(decision["payload_canonical"].encode())).decode(),
            "signing_session_id": session_id,
            "device_fingerprint_ref": DEVICE,
        }
        return await self.h.client.post(f"/v1/decisions/{decision['id']}/sign", json=body)

    async def session(self, session_id: str) -> dict[str, Any]:
        response = await self.h.client.get(f"/v1/signing-sessions/{session_id}")
        return dict(response.json())


@pytest.fixture
def desk(h: Harness) -> Desk:
    return Desk(h)


async def test_dual_control_needs_two_different_signers_and_chains(desk: Desk) -> None:  # 17, 23
    desk.h.clock.set(T0 + timedelta(minutes=1))
    created = await desk.create("alice", "deal_action", gate(2_500_000))
    assert created.status_code == 201, created.text
    decision = created.json()
    assert decision["status"] == "pending_signature" and decision["required_signers"] == 2
    fetched = await desk.h.client.get(
        f"/v1/decisions/{decision['id']}"
    )  # the signer reads the payload
    assert (
        fetched.status_code == 200
        and fetched.json()["payload_canonical"] == decision["payload_canonical"]
    )
    assert (await desk.h.client.get("/v1/decisions/nope")).status_code == 404
    assert decision["requires_immediate_reauth"]  # above EUR 10,000 too
    assert decision["payload_canonical"] == jcs.canonicalize(gate(2_500_000))
    with pytest.raises(PendingSignature):
        await desk.service.require_signed(decision["id"], tenant_id=TENANT)

    alice_window = await desk.window("alice", T0 + timedelta(minutes=2))
    first = await desk.sign("alice", decision, alice_window)
    assert first.status_code == 201, first.text
    assert first.json()["signing_session_id"] == alice_window
    assert first.json()["auth_at"] is not None
    with pytest.raises(PendingSignature):  # one of two: an unsigned decision cannot reach purchased
        await desk.service.require_signed(decision["id"], tenant_id=TENANT)

    again = await desk.sign(
        "alice", decision, await desk.window("alice", T0 + timedelta(minutes=3))
    )
    assert again.status_code == 409 and again.json()["code"] == "already_signed_by_signer"

    second = await desk.sign("bob", decision, await desk.window("bob", T0 + timedelta(minutes=4)))
    assert second.status_code == 201, second.text
    assert second.json()["prev_signature_hash"] == first.json()["chain_hash"]

    signed = await desk.service.require_signed(decision["id"], tenant_id=TENANT)
    assert signed.status is DecisionStatus.SIGNED and signed.signer_ids == (
        "user-alice",
        "user-bob",
    )
    assert signed.payload["seller_confidence"]["model_version"] == "trust-v1"
    verified = (await desk.h.client.post(f"/v1/decisions/{decision['id']}/verify")).json()
    assert verified["valid"] and all(c["ok"] for c in verified["checks"])
    async with tenant_session(TENANT, sessionmaker=desk.h.factory) as db:
        chain = await decisions.verify_chain(db, TENANT)
    assert chain.valid and chain.checked == 2 and chain.head_hash == second.json()["chain_hash"]


GUARDS = (("decisions", "decisions_guard"), ("signatures", "signatures_append_only"))


def _tamper(admin_url: str, sql: str, *args: object) -> None:
    """Change stored rows as a superuser would, past the append-only triggers."""
    with psycopg.connect(admin_url, autocommit=True) as admin:
        for table, trigger in GUARDS:
            admin.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
        admin.execute(sql, list(args))
        for table, trigger in GUARDS:
            admin.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")


async def test_tampering_breaks_verification(desk: Desk, migrated_db: str) -> None:  # 17, 18, 23
    desk.h.clock.set(T0 + timedelta(minutes=1))
    decision = (await desk.create("carol", "deal_action", gate(500_000, score=82))).json()
    assert not decision["requires_immediate_reauth"] and decision["required_signers"] == 1
    signature = await desk.sign(
        "carol", decision, await desk.window("carol", T0 + timedelta(minutes=2))
    )
    assert signature.status_code == 201, signature.text
    assert (await desk.service.require_signed(decision["id"], tenant_id=TENANT)).signer_count == 1

    original = decision["payload_canonical"]
    lifted = original.replace('"score":82', '"score":99')
    assert lifted != original

    async def refused() -> None:
        with pytest.raises(SignatureInvalid):
            await desk.service.require_signed(decision["id"], tenant_id=TENANT)
        verified = (await desk.h.client.post(f"/v1/decisions/{decision['id']}/verify")).json()
        assert not verified["valid"]

    # One byte of the stored payload changes: its hash no longer matches.
    flipped = original.replace('"approve"', '"approvf"')
    _tamper(
        migrated_db,
        "UPDATE decisions SET payload_canonical = %s WHERE id = %s",
        flipped,
        decision["id"],
    )
    await refused()
    # The score changes and the attacker fixes the hash too: the Ed25519 signature breaks (criterion 18).
    _tamper(
        migrated_db,
        "UPDATE decisions SET payload_canonical = %s, payload_hash = %s WHERE id = %s",
        lifted,
        jcs.payload_hash(jcs.loads(lifted)),
        decision["id"],
    )
    await refused()
    _tamper(
        migrated_db,
        "UPDATE decisions SET payload_canonical = %s, payload_hash = %s WHERE id = %s",
        original,
        decision["payload_hash"],
        decision["id"],
    )
    assert (await desk.service.require_signed(decision["id"], tenant_id=TENANT)).signer_count == 1

    # A stored signature row changes: its chain hash breaks, and so does the tenant chain.
    sig_id = signature.json()["id"]
    _tamper(
        migrated_db,
        "UPDATE signatures SET signed_at = signed_at + interval '1 second' WHERE id = %s",
        sig_id,
    )
    await refused()
    async with tenant_session(TENANT, sessionmaker=desk.h.factory) as db:
        broken = await decisions.verify_chain(db, TENANT)
    assert not broken.valid and broken.first_broken_id == sig_id
    _tamper(
        migrated_db,
        "UPDATE signatures SET signed_at = signed_at - interval '1 second' WHERE id = %s",
        sig_id,
    )
    async with tenant_session(TENANT, sessionmaker=desk.h.factory) as db:
        assert (await decisions.verify_chain(db, TENANT)).valid


async def test_immediate_reauth_ignores_a_live_window(desk: Desk) -> None:  # 21
    window = await desk.window("erin", T0 + timedelta(minutes=1))
    desk.h.clock.set(T0 + timedelta(minutes=2))
    high = (await desk.create("erin", "deal_action", gate(1_500_000))).json()
    assert high["requires_immediate_reauth"] and high["required_signers"] == 1

    refused = await desk.sign("erin", high, window)
    assert refused.status_code == 428 and refused.json()["reason"] == "high_value_decision"
    assert (await desk.session(window))["status"] == "active"  # still good for ordinary decisions
    low = (await desk.create("erin", "deal_action", gate(300_000))).json()
    assert (await desk.sign("erin", low, window)).status_code == 201

    fresh = await desk.window("erin", T0 + timedelta(minutes=3))
    assert (await desk.sign("erin", high, fresh)).status_code == 201

    config = (
        await desk.create(
            "erin", "config_change", {"patch": {"sanity": {"z_gate": 3.5}}}, "tenant:x:config"
        )
    ).json()
    assert config["requires_immediate_reauth"]
    used = await desk.sign("erin", config, fresh)  # the fresh window already signed one decision
    assert used.status_code == 428 and used.json()["reason"] == "immediate_reauth_required"

    # Key operations too. The revocation goes through the real require_signed.
    key_id = desk.keys["erin"][1]
    revoke = (
        await desk.create("erin", "revoke_key", {"key_id": key_id}, f"signing_key:{key_id}")
    ).json()
    url, body = f"/v1/keys/{key_id}/revoke", {"decision_id": revoke["id"]}
    assert (await desk.h.client.post(url, json=body)).json()["code"] == "pending_signature"
    stale = await desk.window("erin", T0 + timedelta(minutes=3, seconds=30))
    desk.h.clock.set(T0 + timedelta(minutes=4))
    other = (
        await desk.create("erin", "revoke_key", {"key_id": key_id}, f"signing_key:{key_id}")
    ).json()
    assert (await desk.sign("erin", other, stale)).json()["reason"] == "immediate_reauth_required"
    assert (
        await desk.sign("erin", revoke, await desk.window("erin", T0 + timedelta(minutes=5)))
    ).status_code == 201
    desk.h.as_user("erin")
    revoked = await desk.h.client.post(url, json=body)
    assert revoked.status_code == 200 and revoked.json()["revoked_at"] is not None


async def test_refusals_are_explicit_and_do_not_spend_the_window(desk: Desk) -> None:
    desk.h.clock.set(T0 + timedelta(minutes=1))
    missing = await desk.create("frank", "deal_action", {"offer_id": "offer-1", "amount": eur(100)})
    assert missing.status_code == 422 and missing.json()["code"] == "invalid_payload"
    usd = await desk.create(
        "frank", "deal_action", {**gate(100), "amount": {"amount_minor": 100, "currency": "USD"}}
    )
    assert usd.status_code == 422 and "USD" in usd.json()["detail"]
    desk.cfg.values["approval.dual_control_above"] = None
    unset = await desk.create("frank", "deal_action", gate(100))
    assert unset.status_code == 422  # unset threshold: refused, never defaulted (ADR-900 Q7)
    desk.cfg.values["approval.dual_control_above"] = eur(2_000_000)

    decision = (await desk.create("frank", "deal_action", gate(100))).json()
    window = await desk.window("frank", T0 + timedelta(minutes=2))
    forged = base64.b64encode(Ed25519PrivateKey.generate().sign(b"other")).decode()
    bad = await desk.sign("frank", decision, window, signature=forged)
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_signature"
    wrong = await desk.sign("frank", decision, window, payload_hash="0" * 64)
    assert wrong.status_code == 409 and wrong.json()["code"] == "payload_hash_mismatch"
    assert (await desk.session(window))["decisions_signed"] == []
    assert (await desk.sign("frank", decision, window)).status_code == 201
    done = await desk.sign("frank", decision, window)
    assert done.status_code == 409 and done.json()["code"] == "decision_not_pending"
    assert (await desk.h.client.post("/v1/decisions/nope/verify")).status_code == 404


class FakeTransit:
    """Vault Transit with a local key: ``sign`` returns what Transit would."""

    def __init__(self) -> None:
        self.private = Ed25519PrivateKey.generate()

    async def ensure_signing_key(self, name: str) -> None:
        return None

    async def get_public_key(self, name: str) -> TransitPublicKey:
        raw = self.private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return TransitPublicKey(name=name, version=1, raw=raw)

    async def sign(self, name: str, data: bytes) -> TransitSignature:
        b64 = base64.b64encode(self.private.sign(data)).decode()
        return TransitSignature(
            key_name=name, key_version=1, vault_signature=f"vault:v1:{b64}", signature_b64=b64
        )


async def test_service_events_are_signed_in_transit_and_chained(desk: Desk) -> None:
    service = SigningService(desk.h.factory, desk.cfg, desk.h.clock, vault=FakeTransit())  # type: ignore[arg-type]
    event = {
        "mission_id": "mission-1",
        "offer_id": "offer-1",
        "from": "discovered",
        "to": "enriched",
    }
    ids = [
        await service.sign_service_event("offer-graph", event, tenant_id=TENANT) for _ in range(2)
    ]
    async with tenant_session(TENANT, sessionmaker=desk.h.factory) as db:
        rows = [await db.get(Signature, sig_id) for sig_id in ids]
        assert all(
            r is not None and r.signing_session_id is None and r.key_id == "svc:offer-graph:v1"
            for r in rows
        )
        assert (
            rows[1] is not None
            and rows[0] is not None
            and rows[1].prev_signature_hash == rows[0].chain_hash
        )
        assert (await decisions.verify(db, rows[0].decision_id)).intact
        assert (await decisions.verify_chain(db, TENANT)).valid
        decision_id = rows[0].decision_id
    signed = await service.require_signed(decision_id, tenant_id=TENANT)
    assert signed.type == "service_event" and signed.payload == event
