"""Post-decision flows (D4-14): approvals with dual control, document triggers and price memory.

Three pieces, all deterministic and all behind ports:

* **Approvals inbox.** A decision above ``approval.dual_control_above`` needs two signatures from two
  *different* signers before it is approved (spec §5.10). The inbox lists what is waiting and records the
  second signature; it never signs on anyone's behalf.
* **Document triggers.** An approved deal asks for an RFQ and, once purchased, a purchase order. The PDFs
  belong to DEV-2 (D2-11); this module only decides *when* to ask and what the request must contain.
* **Price memory.** The agreed unit price is written to the price history so the next negotiation can say
  "last time you gave it to me at X" and so the sanity reference can use it (spec §3.3.1, §3.6).

Nothing here computes a price, a band or a score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from apex.agents.ports import DecisionPort, DecisionRef, SignedDecisionView


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    AWAITING_SECOND_SIGNATURE = "awaiting_second_signature"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequest(_Model):
    """One decision waiting for a human. ``signers`` are the distinct user ids that already signed."""

    decision_id: str
    tenant_id: str
    subject_ref: str
    amount_eur_minor: int = Field(ge=0)
    requires_dual_control: bool
    status: ApprovalStatus
    signers: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @property
    def signatures_needed(self) -> int:
        return 2 if self.requires_dual_control else 1


class PriceMemoryRecord(_Model):
    """An agreed unit price, kept for the next negotiation and for the sanity reference."""

    tenant_id: str
    seller_id: str
    product_id: str
    unit_price_eur_minor: int = Field(ge=0)
    quantity: int = Field(gt=0)
    currency: str = Field(pattern="^(EUR|USD|CNY)$")
    agreed_at: datetime
    decision_id: str


class DocumentKind(StrEnum):
    RFQ = "rfq"
    PURCHASE_ORDER = "purchase_order"
    VERIFICATION_CERTIFICATE = "verification_certificate"


class DocumentRequest(_Model):
    kind: DocumentKind
    tenant_id: str
    mission_id: str
    offer_id: str
    decision_id: str
    requested_at: datetime


class DocumentRef(_Model):
    document_id: str
    kind: DocumentKind
    url: str


class DocumentService(Protocol):
    """DEV-2's document generator (D2-11)."""

    async def generate(self, request: DocumentRequest) -> DocumentRef: ...


class ApprovalStore(Protocol):
    async def save(self, request: ApprovalRequest) -> ApprovalRequest: ...

    async def get(self, tenant_id: str, decision_id: str) -> ApprovalRequest | None: ...

    async def list_pending(self, tenant_id: str) -> list[ApprovalRequest]: ...


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ApprovalRequest] = {}

    async def save(self, request: ApprovalRequest) -> ApprovalRequest:
        self._items[(request.tenant_id, request.decision_id)] = request
        return request

    async def get(self, tenant_id: str, decision_id: str) -> ApprovalRequest | None:
        return self._items.get((tenant_id, decision_id))

    async def list_pending(self, tenant_id: str) -> list[ApprovalRequest]:
        pending = [
            r
            for (t, _), r in self._items.items()
            if t == tenant_id
            and r.status in {ApprovalStatus.PENDING, ApprovalStatus.AWAITING_SECOND_SIGNATURE}
        ]
        return sorted(pending, key=lambda r: (r.created_at, r.decision_id))


class PriceMemoryStore(Protocol):
    async def append(self, record: PriceMemoryRecord) -> PriceMemoryRecord: ...

    async def history(
        self, tenant_id: str, *, seller_id: str | None = None, product_id: str | None = None
    ) -> list[PriceMemoryRecord]: ...


class InMemoryPriceMemoryStore:
    def __init__(self) -> None:
        self._records: list[PriceMemoryRecord] = []

    async def append(self, record: PriceMemoryRecord) -> PriceMemoryRecord:
        self._records.append(record)
        return record

    async def history(
        self, tenant_id: str, *, seller_id: str | None = None, product_id: str | None = None
    ) -> list[PriceMemoryRecord]:
        return [
            r
            for r in self._records
            if r.tenant_id == tenant_id
            and (seller_id is None or r.seller_id == seller_id)
            and (product_id is None or r.product_id == product_id)
        ]


@dataclass(frozen=True)
class PostDecisionDeps:
    approvals: ApprovalStore
    prices: PriceMemoryStore
    decisions: DecisionPort
    documents: DocumentService
    clock: object
    dual_control_above_eur_minor: int
    """``approval.dual_control_above`` from tenant config. Required: no default."""


class DualControlViolation(Exception):
    """Two signatures from the same person, or a second signature before the first."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class PostDecisionService:
    def __init__(self, deps: PostDecisionDeps) -> None:
        self._deps = deps

    # ------------------------------------------------------------------ approvals inbox

    async def open_approval(
        self,
        *,
        tenant_id: str,
        decision: DecisionRef,
        subject_ref: str,
        amount_eur_minor: int,
    ) -> ApprovalRequest:
        """Register a decision in the inbox. Dual control is decided by the amount, not by the caller."""
        now = self._now()
        request = ApprovalRequest(
            decision_id=decision.id,
            tenant_id=tenant_id,
            subject_ref=subject_ref,
            amount_eur_minor=amount_eur_minor,
            requires_dual_control=amount_eur_minor > self._deps.dual_control_above_eur_minor,
            status=ApprovalStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        return await self._deps.approvals.save(request)

    async def list_pending(self, *, tenant_id: str) -> list[ApprovalRequest]:
        return await self._deps.approvals.list_pending(tenant_id)

    async def record_signature(
        self, *, tenant_id: str, decision_id: str, signer_id: str
    ) -> ApprovalRequest:
        """Record one signature. The same person cannot supply both signatures of a dual-control decision."""
        request = await self._deps.approvals.get(tenant_id, decision_id)
        if request is None:
            raise LookupError(f"approval {decision_id} not found")
        if request.status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise DualControlViolation(f"approval {decision_id} is already {request.status.value}")
        if signer_id in request.signers:
            raise DualControlViolation(
                f"{signer_id} already signed {decision_id}; dual control needs two different signers"
            )
        signers = [*request.signers, signer_id]
        approved = len(signers) >= request.signatures_needed
        updated = request.model_copy(
            update={
                "signers": signers,
                "status": ApprovalStatus.APPROVED
                if approved
                else ApprovalStatus.AWAITING_SECOND_SIGNATURE,
                "updated_at": self._now(),
            }
        )
        return await self._deps.approvals.save(updated)

    async def reject(self, *, tenant_id: str, decision_id: str, comment: str) -> ApprovalRequest:
        request = await self._deps.approvals.get(tenant_id, decision_id)
        if request is None:
            raise LookupError(f"approval {decision_id} not found")
        if not comment.strip():
            raise DualControlViolation("a rejection needs a written reason")
        return await self._deps.approvals.save(
            request.model_copy(
                update={"status": ApprovalStatus.REJECTED, "updated_at": self._now()}
            )
        )

    async def require_approved(self, *, tenant_id: str, decision_id: str) -> SignedDecisionView:
        """The gate for everything downstream: the decision must be signed *and* approved by a human."""
        request = await self._deps.approvals.get(tenant_id, decision_id)
        if request is None:
            raise LookupError(f"approval {decision_id} not found")
        if request.status is not ApprovalStatus.APPROVED:
            raise DualControlViolation(f"approval {decision_id} is {request.status.value}")
        return await self._deps.decisions.require_signed(decision_id, tenant_id=tenant_id)

    # ------------------------------------------------------------------ documents

    async def request_rfq(
        self, *, tenant_id: str, mission_id: str, offer_id: str, decision_id: str
    ) -> DocumentRef:
        """An approved deal asks for its RFQ. Refused until the approval is complete."""
        await self.require_approved(tenant_id=tenant_id, decision_id=decision_id)
        return await self._deps.documents.generate(
            DocumentRequest(
                kind=DocumentKind.RFQ,
                tenant_id=tenant_id,
                mission_id=mission_id,
                offer_id=offer_id,
                decision_id=decision_id,
                requested_at=self._now(),
            )
        )

    async def request_purchase_order(
        self, *, tenant_id: str, mission_id: str, offer_id: str, decision_id: str
    ) -> DocumentRef:
        await self.require_approved(tenant_id=tenant_id, decision_id=decision_id)
        return await self._deps.documents.generate(
            DocumentRequest(
                kind=DocumentKind.PURCHASE_ORDER,
                tenant_id=tenant_id,
                mission_id=mission_id,
                offer_id=offer_id,
                decision_id=decision_id,
                requested_at=self._now(),
            )
        )

    # ------------------------------------------------------------------ price memory

    async def remember_price(
        self,
        *,
        tenant_id: str,
        seller_id: str,
        product_id: str,
        unit_price_eur_minor: int,
        quantity: int,
        currency: str,
        decision_id: str,
    ) -> PriceMemoryRecord:
        """Write the agreed price to the history. Called only after a signed approval."""
        await self.require_approved(tenant_id=tenant_id, decision_id=decision_id)
        return await self._deps.prices.append(
            PriceMemoryRecord(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=product_id,
                unit_price_eur_minor=unit_price_eur_minor,
                quantity=quantity,
                currency=currency,
                agreed_at=self._now(),
                decision_id=decision_id,
            )
        )

    async def last_price(
        self, *, tenant_id: str, seller_id: str, product_id: str
    ) -> PriceMemoryRecord | None:
        """What this seller last agreed for this product, or ``None``. Used by the negotiator's opener."""
        history = await self._deps.prices.history(
            tenant_id, seller_id=seller_id, product_id=product_id
        )
        return history[-1] if history else None

    async def reference_prices(self, *, tenant_id: str, product_id: str) -> list[PriceMemoryRecord]:
        """Every agreed price for a product: one of the sanity reference sources (spec §3.3.1)."""
        return await self._deps.prices.history(tenant_id, product_id=product_id)

    def _now(self) -> datetime:
        now: datetime = self._deps.clock.now()  # type: ignore[attr-defined]
        return now


__all__ = [
    "ApprovalRequest",
    "ApprovalStatus",
    "DocumentKind",
    "DocumentRef",
    "DocumentRequest",
    "DocumentService",
    "DualControlViolation",
    "InMemoryApprovalStore",
    "InMemoryPriceMemoryStore",
    "PostDecisionDeps",
    "PostDecisionService",
    "PriceMemoryRecord",
    "PriceMemoryStore",
]
