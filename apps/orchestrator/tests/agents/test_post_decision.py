"""Post-decision flows (D4-14): dual-control approvals, document triggers and price memory."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from apex.agents.ports import DecisionRef, PendingSignature, SignedDecisionView
from apex.agents.post_decision import (
    ApprovalStatus,
    DocumentKind,
    DocumentRef,
    DocumentRequest,
    DualControlViolation,
    InMemoryApprovalStore,
    InMemoryPriceMemoryStore,
    PostDecisionDeps,
    PostDecisionService,
)
from apex.common.clock import FixedClock

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
DUAL_ABOVE = 2_000_000  # EUR 20,000 in minor units


class _Decisions:
    def __init__(self) -> None:
        self.signed: dict[str, SignedDecisionView] = {}

    async def create_decision(
        self, type: str, subject_ref: str, payload: Any, *, tenant_id: str
    ) -> DecisionRef:
        return DecisionRef(id="d1", status="pending_signature")

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> SignedDecisionView:
        if decision_id not in self.signed:
            raise PendingSignature(decision_id)
        return self.signed[decision_id]

    async def sign_service_event(self, service: str, payload: Any, *, tenant_id: str) -> str:
        return "sig"

    def sign(self, decision_id: str) -> None:
        self.signed[decision_id] = SignedDecisionView(
            id=decision_id,
            type="deal_action",
            subject_ref="offer:m-1:o-1",
            payload={},
            signer_count=1,
        )


class _Documents:
    def __init__(self) -> None:
        self.requests: list[DocumentRequest] = []

    async def generate(self, request: DocumentRequest) -> DocumentRef:
        self.requests.append(request)
        return DocumentRef(
            document_id=f"doc-{len(self.requests)}", kind=request.kind, url="s3://docs/x.pdf"
        )


def _service(
    *, dual_above: int = DUAL_ABOVE, approvals: Any = None, prices: Any = None
) -> tuple[PostDecisionService, _Decisions, _Documents]:
    decisions = _Decisions()
    documents = _Documents()
    service = PostDecisionService(
        PostDecisionDeps(
            approvals=approvals or InMemoryApprovalStore(),
            prices=prices or InMemoryPriceMemoryStore(),
            decisions=decisions,
            documents=documents,
            clock=FixedClock(NOW),
            dual_control_above_eur_minor=dual_above,
        )
    )
    return service, decisions, documents


async def _open(service: PostDecisionService, amount: int = 500_000) -> Any:
    return await service.open_approval(
        tenant_id=TENANT,
        decision=DecisionRef(id="d1", status="pending_signature"),
        subject_ref="offer:m-1:o-1",
        amount_eur_minor=amount,
    )


# ----- dual control ------------------------------------------------------------------------------


async def test_dual_control_is_decided_by_the_amount_not_the_caller() -> None:
    service, _, _ = _service()
    small = await _open(service, amount=DUAL_ABOVE)
    big = await _open(service, amount=DUAL_ABOVE + 1)
    assert small.requires_dual_control is False and small.signatures_needed == 1
    assert big.requires_dual_control is True and big.signatures_needed == 2


async def test_one_signature_approves_a_normal_decision() -> None:
    service, decisions, _ = _service()
    await _open(service)
    approved = await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    assert approved.status is ApprovalStatus.APPROVED
    assert approved.signers == ["u-1"]


async def test_a_dual_control_decision_needs_two_different_signers() -> None:
    service, _, _ = _service()
    await _open(service, amount=DUAL_ABOVE + 1)
    first = await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    assert first.status is ApprovalStatus.AWAITING_SECOND_SIGNATURE
    second = await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-2")
    assert second.status is ApprovalStatus.APPROVED
    assert second.signers == ["u-1", "u-2"]


async def test_the_same_signer_cannot_supply_both_signatures() -> None:
    service, _, _ = _service()
    await _open(service, amount=DUAL_ABOVE + 1)
    await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    with pytest.raises(DualControlViolation, match="two different signers"):
        await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")


async def test_a_decided_approval_cannot_be_signed_again() -> None:
    service, _, _ = _service()
    await _open(service)
    await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    with pytest.raises(DualControlViolation, match="already approved"):
        await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-2")


async def test_the_inbox_lists_only_what_is_waiting() -> None:
    service, _, _ = _service()
    await _open(service, amount=DUAL_ABOVE + 1)
    assert len(await service.list_pending(tenant_id=TENANT)) == 1
    await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    assert len(await service.list_pending(tenant_id=TENANT)) == 1  # awaiting the second signature
    await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-2")
    assert await service.list_pending(tenant_id=TENANT) == []


async def test_the_inbox_is_tenant_scoped() -> None:
    service, _, _ = _service()
    await _open(service)
    assert await service.list_pending(tenant_id="tenant-b") == []


async def test_a_rejection_needs_a_reason() -> None:
    service, _, _ = _service()
    await _open(service)
    with pytest.raises(DualControlViolation, match="written reason"):
        await service.reject(tenant_id=TENANT, decision_id="d1", comment="  ")
    rejected = await service.reject(tenant_id=TENANT, decision_id="d1", comment="too expensive")
    assert rejected.status is ApprovalStatus.REJECTED


# ----- downstream requires a completed approval ---------------------------------------------------


async def test_documents_and_price_memory_are_refused_until_approved() -> None:
    service, decisions, documents = _service()
    await _open(service, amount=DUAL_ABOVE + 1)
    await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    decisions.sign("d1")  # signed, but only one of the two required signatures
    with pytest.raises(DualControlViolation, match="awaiting_second_signature"):
        await service.request_rfq(
            tenant_id=TENANT, mission_id="m-1", offer_id="o-1", decision_id="d1"
        )
    assert documents.requests == []


async def test_an_unapproved_approval_is_not_found_for_another_tenant() -> None:
    service, _, _ = _service()
    await _open(service)
    with pytest.raises(LookupError):
        await service.require_approved(tenant_id="tenant-b", decision_id="d1")


async def test_rfq_and_purchase_order_are_requested_after_approval() -> None:
    service, decisions, documents = _service()
    await _open(service)
    await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    decisions.sign("d1")
    rfq = await service.request_rfq(
        tenant_id=TENANT, mission_id="m-1", offer_id="o-1", decision_id="d1"
    )
    po = await service.request_purchase_order(
        tenant_id=TENANT, mission_id="m-1", offer_id="o-1", decision_id="d1"
    )
    assert rfq.kind is DocumentKind.RFQ and po.kind is DocumentKind.PURCHASE_ORDER
    assert [r.kind for r in documents.requests] == [DocumentKind.RFQ, DocumentKind.PURCHASE_ORDER]
    assert all(r.decision_id == "d1" for r in documents.requests)


# ----- price memory ------------------------------------------------------------------------------


async def test_price_memory_records_the_agreed_price_after_approval() -> None:
    service, decisions, _ = _service()
    await _open(service)
    await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    decisions.sign("d1")
    record = await service.remember_price(
        tenant_id=TENANT,
        seller_id="s-1",
        product_id="p-1",
        unit_price_eur_minor=412,
        quantity=100,
        currency="EUR",
        decision_id="d1",
    )
    assert record.unit_price_eur_minor == 412
    assert record.agreed_at == NOW


async def test_last_price_is_the_most_recent_agreement_for_that_seller_and_product() -> None:
    service, decisions, _ = _service()
    await _open(service)
    await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    decisions.sign("d1")
    for price in (500, 412):
        await service.remember_price(
            tenant_id=TENANT,
            seller_id="s-1",
            product_id="p-1",
            unit_price_eur_minor=price,
            quantity=100,
            currency="EUR",
            decision_id="d1",
        )
    last = await service.last_price(tenant_id=TENANT, seller_id="s-1", product_id="p-1")
    assert last is not None and last.unit_price_eur_minor == 412
    assert await service.last_price(tenant_id=TENANT, seller_id="s-9", product_id="p-1") is None


async def test_reference_prices_cover_every_seller_for_a_product() -> None:
    service, decisions, _ = _service()
    await _open(service)
    await service.record_signature(tenant_id=TENANT, decision_id="d1", signer_id="u-1")
    decisions.sign("d1")
    for seller, price in (("s-1", 500), ("s-2", 480)):
        await service.remember_price(
            tenant_id=TENANT,
            seller_id=seller,
            product_id="p-1",
            unit_price_eur_minor=price,
            quantity=10,
            currency="EUR",
            decision_id="d1",
        )
    reference = await service.reference_prices(tenant_id=TENANT, product_id="p-1")
    assert sorted(r.unit_price_eur_minor for r in reference) == [480, 500]
    assert await service.reference_prices(tenant_id="tenant-b", product_id="p-1") == []
