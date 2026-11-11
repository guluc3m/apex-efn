"""Decisions, signatures and the per-tenant hash chain (D2-09, ADR-209, spec 5.10.2-5.10.4).

A decision stores the RFC 8785 form of its payload and its SHA-256. Signers sign exactly those bytes. The server
verifies every signature before it stores it, chains it to the tenant's previous signature, and marks the decision
``signed`` once ``required_signers`` different people (or one service) have signed. All functions take a
``tenant_session``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from apex.db.models import (
    ActorType,
    Decision,
    DecisionStatus,
    DecisionType,
    ReauthReason,
    Signature,
    SigningKey,
    SigningKeyOwnerType,
)
from apex.signing import jcs, sessions
from apex.signing.ed25519 import MalformedKeyOrSignature, verify_bytes
from apex.signing.keys import ALG

T = DecisionType
GATE_TYPES = frozenset(
    {
        T.DEAL_ACTION,
        T.GATE_UNBLOCK,
        T.GATE_OVERRIDE_DISCARD,
        T.FOLLOW,
        T.RENEGOTIATE,
        T.TAKEOVER,
        T.HOLD,
        T.DISCARD,
        T.APPROVE_PURCHASE,
    }
)
"""Spec 5.10.2: their payload must carry the amount, the offer, the sanity check, the seller confidence, the
financial verdict and ``config_version``."""
GATE_FIELDS = (
    "offer_id",
    "amount",
    "price_sanity",
    "seller_confidence",
    "financial_verdict",
    "config_version",
)
IMMEDIATE_TYPES = frozenset(
    {
        T.FINANCIAL_SNAPSHOT_ACTIVATION,
        T.CONFIG_CHANGE,
        T.CHANGE_PRICING_THRESHOLD,
        T.CHANGE_CONFIDENCE_WEIGHTS,
        T.CHANGE_SCORING_WEIGHTS,
        T.GATE_OVERRIDE_DISCARD,
        T.ROTATE_KEY,
        T.REVOKE_KEY,
    }
)
"""Spec 5.10.4: these need a fresh step-up whatever the amount."""


class DecisionError(Exception):
    """Base class. ``code`` is stable and goes into the problem+json body."""

    code = "decision_error"
    status = 409


class InvalidPayload(DecisionError):
    code = "invalid_payload"
    status = 422


class DecisionNotFound(DecisionError):
    code = "decision_not_found"
    status = 404


class NotPending(DecisionError):
    code = "decision_not_pending"


class PayloadHashMismatch(DecisionError):
    code = "payload_hash_mismatch"


class AlreadySignedBySigner(DecisionError):
    """Dual control: the second signature must come from someone else."""

    code = "already_signed_by_signer"


class BadSignature(DecisionError):
    code = "invalid_signature"
    status = 422


class Config(Protocol):
    """The part of ``EffectiveConfig`` this module reads. ``require`` raises ``ConfigKeyUnset``."""

    @property
    def config_version(self) -> int: ...

    def require(self, path: str) -> Any: ...


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_payload(type_: DecisionType, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Validate the shape the server relies on and return the ``amount``, if any."""
    if type_ in GATE_TYPES:
        missing = [name for name in GATE_FIELDS if payload.get(name) is None]
        if missing:
            raise InvalidPayload(f"a {type_.value} payload needs {', '.join(missing)}")
        confidence = payload["seller_confidence"]
        if not isinstance(confidence, Mapping) or any(
            confidence.get(k) is None for k in ("score", "band", "model_version")
        ):
            raise InvalidPayload("seller_confidence needs score, band and model_version")
        if not isinstance(payload["price_sanity"], Mapping):
            raise InvalidPayload("price_sanity must be the PriceSanityCheck object")
    amount = payload.get("amount")
    if amount is None:
        return None
    if (
        not isinstance(amount, Mapping)
        or not _is_int(amount.get("amount_minor"))
        or not isinstance(amount.get("currency"), str)
    ):
        raise InvalidPayload("amount must be {amount_minor: int, currency}")
    return amount


def _above(amount: Mapping[str, Any], config: Config, path: str) -> bool:
    limit = config.require(path)  # unset: ConfigKeyUnset, never a default (ADR-900 Q7)
    if limit["currency"] != amount["currency"]:
        raise InvalidPayload(
            f"amount is in {amount['currency']} but {path} is in {limit['currency']}"
        )
    return bool(amount["amount_minor"] > limit["amount_minor"])


async def create(
    session: AsyncSession,
    *,
    decision_id: str,
    tenant_id: str,
    type_: DecisionType,
    subject_ref: str,
    payload: Mapping[str, Any],
    created_by: tuple[ActorType, str],
    config: Config | None,
    now: datetime,
) -> Decision:
    """Store a ``pending_signature`` decision. Thresholds are read now and fixed in the row."""
    if not isinstance(payload, Mapping):
        raise InvalidPayload("payload must be a JSON object")
    amount = _check_payload(type_, payload)
    if amount is not None and config is None:
        raise InvalidPayload("a decision with an amount needs the tenant configuration")
    try:
        canonical = jcs.canonicalize(payload)
    except jcs.CanonicalizationError as error:
        raise InvalidPayload(str(error)) from error
    dual = (
        amount is not None
        and config is not None
        and _above(amount, config, "approval.dual_control_above")
    )
    high = (
        amount is not None
        and config is not None
        and _above(amount, config, "signing.high_value_reauth_above")
    )
    row = Decision(
        id=decision_id,
        tenant_id=tenant_id,
        type=type_,
        subject_ref=subject_ref,
        payload_canonical=canonical,
        payload_hash=jcs.payload_hash(payload),
        status=DecisionStatus.PENDING_SIGNATURE,
        requires_immediate_reauth=high or type_ in IMMEDIATE_TYPES,
        required_signers=2 if dual else 1,
        config_version=None if config is None else config.config_version,
        created_by_type=created_by[0],
        created_by_id=created_by[1],
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row


def _ts(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


def chain_hash(sig: Signature) -> str:
    """SHA-256 over the JCS form of the record, ``prev_signature_hash`` included (ADR-209)."""
    return jcs.payload_hash(
        {
            "alg": sig.alg,
            "auth_at": _ts(sig.auth_at),
            "decision_id": sig.decision_id,
            "key_id": sig.key_id,
            "payload_hash": sig.payload_hash,
            "prev_signature_hash": sig.prev_signature_hash,
            "signature": sig.signature,
            "signed_at": _ts(sig.signed_at),
            "signer_id": sig.signer_id,
            "signer_type": sig.signer_type.value,
            "signing_session_id": sig.signing_session_id,
        }
    )


async def _append(
    session: AsyncSession, decision: Decision, sig: Signature, now: datetime
) -> Signature:
    """Chain ``sig`` to the tenant's head, store it, and settle the decision."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"signature_chain:{sig.tenant_id}")))
    )
    later = aliased(Signature)
    # ponytail: the head query scans the tenant's signatures; a head pointer row if D1-10 shows it matters.
    sig.prev_signature_hash = await session.scalar(
        select(Signature.chain_hash).where(
            Signature.tenant_id == sig.tenant_id,
            ~exists().where(
                later.tenant_id == Signature.tenant_id,
                later.prev_signature_hash == Signature.chain_hash,
            ),
        )
    )
    sig.chain_hash = chain_hash(sig)
    session.add(sig)
    await session.flush()
    signers = await session.scalar(
        select(func.count()).select_from(Signature).where(Signature.decision_id == decision.id)
    )
    if (signers or 0) >= decision.required_signers:
        decision.status = DecisionStatus.SIGNED
        decision.signed_at = now
        await session.flush()
    return sig


def _valid(public_key: str, signature: str, decision: Decision) -> bool:
    try:
        return verify_bytes(public_key, signature, decision.payload_canonical.encode("utf-8"))
    except MalformedKeyOrSignature:
        return False


async def _pending(session: AsyncSession, decision_id: str) -> Decision:
    decision = await session.get(Decision, decision_id, with_for_update=True)
    if decision is None:
        raise DecisionNotFound(decision_id)
    if decision.status != DecisionStatus.PENDING_SIGNATURE:
        raise NotPending(f"decision {decision_id} is {decision.status.value}")
    return decision


async def sign_human(
    session: AsyncSession,
    decision_id: str,
    *,
    signature_id: str,
    user_id: str,
    key_id: str,
    payload_hash: str,
    signature: str,
    signing_session_id: str,
    device_fingerprint_ref: str,
    client_attestation: str | None,
    now: datetime,
    network_ref: str | None = None,
) -> Signature:
    """Verify and store a browser signature. Raises ``DecisionError`` or ``sessions.ReauthRequired``.

    The order matters: nothing that can fail runs after ``sessions.consume``, which commits its refusals.
    """
    decision = await _pending(session, decision_id)
    if payload_hash != decision.payload_hash:
        raise PayloadHashMismatch("payload_hash is not the hash of the stored payload")
    if await session.scalar(
        select(Signature.id).where(
            Signature.decision_id == decision_id, Signature.signer_id == user_id
        )
    ):
        raise AlreadySignedBySigner("dual control needs a second, different signer")
    key = await session.get(SigningKey, key_id)
    if key is None or key.owner_type != SigningKeyOwnerType.HUMAN or key.owner_id != user_id:
        raise BadSignature("key_id is not one of your keys")
    if not _valid(key.public_key, signature, decision):
        raise BadSignature("the signature does not verify against the stored payload")
    window = await sessions.consume(
        session,
        signing_session_id,
        user_id=user_id,
        key_id=key_id,
        device_fingerprint_ref=device_fingerprint_ref,
        network_ref=network_ref,
        decision_id=decision_id,
        now=now,
        fresh_after=decision.created_at if decision.requires_immediate_reauth else None,
        fresh_reason=ReauthReason.IMMEDIATE_REAUTH_REQUIRED
        if decision.type in IMMEDIATE_TYPES
        else ReauthReason.HIGH_VALUE_DECISION,
    )
    sig = Signature(
        id=signature_id,
        tenant_id=decision.tenant_id,
        decision_id=decision_id,
        signer_type=ActorType.HUMAN,
        signer_id=user_id,
        key_id=key_id,
        alg=ALG,
        payload_hash=payload_hash,
        signature=signature,
        signed_at=now,
        signing_session_id=window.id,
        auth_at=window.auth_at,
        client_attestation=client_attestation,
    )
    return await _append(session, decision, sig, now)


async def sign_service(
    session: AsyncSession,
    decision_id: str,
    *,
    signature_id: str,
    key: SigningKey,
    signature: str,
    now: datetime,
) -> Signature:
    """Store a Vault Transit signature by a service key. Services sign without a signing session."""
    decision = await _pending(session, decision_id)
    if key.owner_type != SigningKeyOwnerType.SERVICE or not _valid(
        key.public_key, signature, decision
    ):
        raise BadSignature("the service signature does not verify")
    sig = Signature(
        id=signature_id,
        tenant_id=decision.tenant_id,
        decision_id=decision_id,
        signer_type=ActorType.SERVICE,
        signer_id=key.owner_id,
        key_id=key.id,
        alg=ALG,
        payload_hash=decision.payload_hash,
        signature=signature,
        signed_at=now,
    )
    return await _append(session, decision, sig, now)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class Verification:
    decision: Decision
    signatures: Sequence[Signature]
    checks: Sequence[Check]

    @property
    def intact(self) -> bool:
        """Payload and every stored signature are untampered (whether or not enough people signed)."""
        return all(c.ok for c in self.checks if c.name != "signers")

    @property
    def enough_signers(self) -> bool:
        return all(c.ok for c in self.checks if c.name == "signers")


async def verify(session: AsyncSession, decision_id: str) -> Verification:
    """Re-check a decision from the stored bytes: payload hash, every signature and chain hash, signer count."""
    decision = await session.get(Decision, decision_id)
    if decision is None:
        raise DecisionNotFound(decision_id)
    sigs = (
        await session.scalars(
            select(Signature)
            .where(Signature.decision_id == decision_id)
            .order_by(Signature.signed_at)
        )
    ).all()
    stored = decision.payload_canonical.encode("utf-8")
    checks = [Check("payload_hash", hashlib.sha256(stored).hexdigest() == decision.payload_hash)]
    for sig in sigs:
        key = await session.get(SigningKey, sig.key_id)
        checks.append(
            Check(
                f"signature:{sig.id}",
                key is not None
                and sig.payload_hash == decision.payload_hash
                and _valid(key.public_key, sig.signature, decision),
                f"signer {sig.signer_id}, key {sig.key_id}",
            )
        )
        checks.append(Check(f"chain_hash:{sig.id}", chain_hash(sig) == sig.chain_hash))
    distinct = len({sig.signer_id for sig in sigs})
    checks.append(
        Check(
            "signers",
            distinct >= decision.required_signers,
            f"{distinct}/{decision.required_signers}",
        )
    )
    return Verification(decision, sigs, checks)


@dataclass(frozen=True)
class ChainCheck:
    valid: bool
    checked: int
    head_hash: str | None
    first_broken_id: str | None = None


async def verify_chain(session: AsyncSession, tenant_id: str) -> ChainCheck:
    """Walk the tenant's chain from its first signature and recompute every link (criterion 23)."""
    sigs = (await session.scalars(select(Signature).where(Signature.tenant_id == tenant_id))).all()
    by_prev = {sig.prev_signature_hash: sig for sig in sigs}
    prev: str | None = None
    for checked in range(len(sigs)):
        sig = by_prev.get(prev)
        if sig is None or chain_hash(sig) != sig.chain_hash:
            broken = sig.id if sig is not None else None
            return ChainCheck(False, checked, prev, broken)
        prev = sig.chain_hash
    return ChainCheck(len(by_prev) == len(sigs), len(sigs), prev)


__all__ = [
    "GATE_FIELDS",
    "GATE_TYPES",
    "IMMEDIATE_TYPES",
    "AlreadySignedBySigner",
    "BadSignature",
    "ChainCheck",
    "Check",
    "Config",
    "DecisionError",
    "DecisionNotFound",
    "InvalidPayload",
    "NotPending",
    "PayloadHashMismatch",
    "Verification",
    "chain_hash",
    "create",
    "sign_human",
    "sign_service",
    "verify",
    "verify_chain",
]
