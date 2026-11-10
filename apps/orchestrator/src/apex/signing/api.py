"""``apex.signing.api``: the signing seam for other lanes (AGENTS.md section 4, issue #92, ADR-209).

Async, ``tenant_id`` as a keyword. ``require_signed`` never trusts ``status``: it re-hashes the stored payload and
re-verifies every signature before it returns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apex.common.clock import Clock
from apex.common.ids import IdGenerator
from apex.db.models import ActorType, DecisionStatus, DecisionType, SigningKey
from apex.db.session import system_session, tenant_session
from apex.platform.vault import VaultClient
from apex.signing import decisions, jcs
from apex.signing import sessions as signing_sessions
from apex.signing.keys import service_key_id, sync_service_key


class PendingSignature(Exception):
    """The decision is not (fully) signed yet."""


class DecisionRejected(Exception):
    """The decision was rejected or expired. It will never be signed."""


class SignatureInvalid(Exception):
    """The stored payload or a stored signature does not verify. Tampering: never read it as a rejection."""


class ConfigSource(Protocol):
    async def effective(self, tenant_id: str) -> decisions.Config: ...


@dataclass(frozen=True)
class DecisionRef:
    id: str
    type: DecisionType
    subject_ref: str
    status: DecisionStatus
    payload_hash: str
    requires_immediate_reauth: bool
    required_signers: int
    created_at: datetime


@dataclass(frozen=True)
class SignedDecision(DecisionRef):
    payload: Mapping[str, Any]
    """The signed canonical payload, parsed."""
    signer_ids: tuple[str, ...]
    signed_at: datetime | None

    @property
    def signer_count(self) -> int:
        return len(self.signer_ids)


def _ref(row: Any) -> DecisionRef:
    return DecisionRef(
        id=row.id,
        type=row.type,
        subject_ref=row.subject_ref,
        status=row.status,
        payload_hash=row.payload_hash,
        requires_immediate_reauth=row.requires_immediate_reauth,
        required_signers=row.required_signers,
        created_at=row.created_at,
    )


def decision_type(value: str) -> DecisionType:
    try:
        return DecisionType(value)
    except ValueError as error:
        raise decisions.InvalidPayload(f"unknown decision type {value!r}") from error


class SigningService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        config: ConfigSource,
        clock: Clock,
        vault: VaultClient | None = None,
    ) -> None:
        self._sessions, self._config, self._clock, self._vault = sessionmaker, config, clock, vault
        self._ids = IdGenerator(clock)

    async def create_decision(
        self,
        type: str,
        subject_ref: str,
        payload: Mapping[str, Any],
        *,
        tenant_id: str,
        created_by: tuple[ActorType, str] = (ActorType.SERVICE, "orchestrator"),
    ) -> DecisionRef:
        """A ``pending_signature`` decision. Dual control and immediate reauth are decided here, not by callers."""
        config = await self._config.effective(tenant_id)
        async with tenant_session(tenant_id, sessionmaker=self._sessions) as session:
            row = await decisions.create(
                session,
                decision_id=self._ids.new_id(),
                tenant_id=tenant_id,
                type_=decision_type(type),
                subject_ref=subject_ref,
                payload=payload,
                created_by=created_by,
                config=config,
                now=self._clock.now(),
            )
            return _ref(row)

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> SignedDecision:
        """The signed decision, re-verified. Raises ``PendingSignature``, ``DecisionRejected``,
        ``SignatureInvalid`` or ``decisions.DecisionNotFound``."""
        async with tenant_session(tenant_id, sessionmaker=self._sessions) as session:
            check = await decisions.verify(session, decision_id)
        row = check.decision
        if row.status in (DecisionStatus.REJECTED, DecisionStatus.EXPIRED):
            raise DecisionRejected(f"decision {decision_id} is {row.status.value}")
        if not check.intact:
            raise SignatureInvalid(f"decision {decision_id} does not verify")
        if row.status != DecisionStatus.SIGNED:
            raise PendingSignature(decision_id)
        if not check.enough_signers:
            raise SignatureInvalid(f"decision {decision_id} is signed without enough signers")
        return SignedDecision(
            **vars(_ref(row)),
            payload=jcs.loads(row.payload_canonical),
            signer_ids=tuple(sig.signer_id for sig in check.signatures),
            signed_at=row.signed_at,
        )

    async def sign_service_event(
        self, service: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> str:
        """Sign an automatic transition with the service's Vault Transit key. Returns the signature id."""
        if self._vault is None:
            raise RuntimeError("service signing needs a Vault client")
        now = self._clock.now()
        async with tenant_session(tenant_id, sessionmaker=self._sessions) as session:
            row = await decisions.create(
                session,
                decision_id=self._ids.new_id(),
                tenant_id=tenant_id,
                type_=DecisionType.SERVICE_EVENT,
                subject_ref=f"service:{service}",
                payload=payload,
                created_by=(ActorType.SERVICE, service),
                config=None,
                now=now,
            )
            signed = await self._vault.sign(service, row.payload_canonical.encode("utf-8"))
            key_id = service_key_id(signed.key_name, signed.key_version)
            key = await session.get(SigningKey, key_id)
            if key is None:  # first use of this Transit version: register it (global row)
                async with system_session(sessionmaker=self._sessions) as system:
                    await sync_service_key(self._vault, system, service, now=now)
                key = await session.get(SigningKey, key_id)
            if key is None:
                raise RuntimeError(f"Transit key {key_id} is not registered")
            sig = await decisions.sign_service(
                session,
                row.id,
                signature_id=self._ids.new_id(),
                key=key,
                signature=signed.signature_b64,
                now=now,
            )
            return sig.id

    async def mark_session_risky(self, session_id: str, *, tenant_id: str) -> bool:
        """GateAgent hook: end a signing window at once. True if it was active."""
        async with tenant_session(tenant_id, sessionmaker=self._sessions) as session:
            return await signing_sessions.mark_session_risky(
                session, session_id, now=self._clock.now()
            )


__all__ = [
    "ConfigSource",
    "DecisionRef",
    "DecisionRejected",
    "PendingSignature",
    "SignatureInvalid",
    "SignedDecision",
    "SigningService",
    "decision_type",
]
