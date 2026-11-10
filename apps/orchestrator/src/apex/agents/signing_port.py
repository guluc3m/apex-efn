"""``DecisionPort`` over ``apex.signing.api`` (D2-09).

The graph never touches signatures directly: it asks for a decision to be created, and it asks whether one is
signed. This adapter is the only place that translates between the two vocabularies, so a change in
``apex.signing.api`` is one file to update.

Two rules from ADR-209 that this adapter must not soften:

* ``require_signed`` **re-verifies** the stored payload and every signature. The adapter maps its failures
  onto the graph's own exceptions, and it never turns a tampered decision into "not signed yet".
* Dual control and immediate reauth are decided by the signing service from config, never by the caller. The
  adapter passes ``tenant_id`` and nothing else that could influence them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from apex.agents.ports import DecisionPort, DecisionRef, SignedDecisionView
from apex.agents.ports import DecisionRejected as GraphDecisionRejected
from apex.agents.ports import PendingSignature as GraphPendingSignature


class SigningBackend(Protocol):
    """The slice of ``apex.signing.api.SigningService`` this adapter calls."""

    async def create_decision(
        self, type: str, subject_ref: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> Any: ...

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> Any: ...

    async def sign_service_event(
        self, service: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> Any: ...


class SigningIntegrityError(Exception):
    """A stored decision does not verify. Tampering: never reported as a rejection or a pending signature."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class SigningDecisionPort(DecisionPort):
    """``DecisionPort`` backed by the signing service.

    DEV-2's exception classes are injected rather than imported: ``apex.signing.api`` is not on ``main`` yet
    (D2-09 is in review), and importing it here would make the whole orchestrator depend on an unmerged
    module. The wiring passes the real classes once D2-09 lands; with none passed, every failure propagates
    unchanged, which is loud rather than wrong.
    """

    def __init__(
        self,
        service: SigningBackend,
        *,
        pending: tuple[type[BaseException], ...] = (),
        rejected: tuple[type[BaseException], ...] = (),
        invalid: tuple[type[BaseException], ...] = (),
    ) -> None:
        self._service = service
        self._pending, self._rejected, self._invalid = pending, rejected, invalid

    async def create_decision(
        self, type: str, subject_ref: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> DecisionRef:
        ref = await self._service.create_decision(type, subject_ref, payload, tenant_id=tenant_id)
        return DecisionRef(id=ref.id, status=ref.status.value)

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> SignedDecisionView:
        try:
            signed = await self._service.require_signed(decision_id, tenant_id=tenant_id)
        except self._pending as exc:
            raise GraphPendingSignature(decision_id) from exc
        except self._rejected as exc:
            raise GraphDecisionRejected(decision_id) from exc
        except self._invalid as exc:
            raise SigningIntegrityError(f"decision {decision_id} does not verify: {exc}") from exc
        return SignedDecisionView(
            id=signed.id,
            type=signed.type.value,
            subject_ref=signed.subject_ref,
            payload=dict(signed.payload),
            signer_count=signed.signer_count,
        )

    async def sign_service_event(
        self, service: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> str:
        signature = await self._service.sign_service_event(service, payload, tenant_id=tenant_id)
        # The service returns a Signature row; the graph only needs something stable to log.
        return str(getattr(signature, "id", signature))


__all__ = ["SigningBackend", "SigningDecisionPort", "SigningIntegrityError"]
