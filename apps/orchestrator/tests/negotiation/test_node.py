"""NegotiationPort adapter (ADR-900 contract with DEV-4's mission graph) and the Q15 counterpart cap."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from apex.negotiation.guardrails import Counterpart
from apex.negotiation.models import NegotiationOutcome, NegotiationParams
from apex.negotiation.node import EngineNegotiationPort, OfferInput
from tests.negotiation.fakes import cooperative_seller, harness, params

OFFER = {
    "offer_id": "o-1",
    "platform": "mock-b",
    "seller_id": "b-standard-coop",
    "platform_offer_id": "b-gloves-03",
    "price_minor": 465,
    "anything_else": True,
}


def resolver(p: NegotiationParams):  # type: ignore[no-untyped-def]
    async def resolve(offer: OfferInput, tenant_id: str) -> tuple[NegotiationParams, str, str]:
        assert offer.product_id == "b-gloves-03"
        return p, "cfg-7", f"acct-{tenant_id}"

    return resolve


async def test_result_is_non_terminal_until_agreed_and_price_only_when_agreed() -> None:
    h = harness(cooperative_seller())
    port = EngineNegotiationPort(h.engine, h.store, resolver(params(semi_automatic=False)))
    key = "negotiate:offer:m1:o-1:1"

    first = await port.negotiate(OFFER, tenant_id="tenant-a", idempotency_key=key)
    assert first.outcome is NegotiationOutcome.AWAITING_SELLER
    assert first.price_minor is None and first.currency is None and first.quantity is None
    assert h.chat.opened[0]["account_id"] == "acct-tenant-a"

    result = first
    for _ in range(20):
        h.clock.advance(timedelta(minutes=1))
        result = await port.negotiate(OFFER, tenant_id="tenant-a", idempotency_key=key)
        if result.outcome is not NegotiationOutcome.AWAITING_SELLER:
            break
    assert result.outcome is NegotiationOutcome.AGREED
    assert result.negotiation_id == first.negotiation_id
    assert result.price_minor is not None and result.price_minor <= 428
    assert result.currency == "EUR"
    assert result.quantity == 5000
    assert len(h.chat.opened) == 1


async def test_semi_automatic_reports_awaiting_human_approval() -> None:
    h = harness(cooperative_seller())
    port = EngineNegotiationPort(h.engine, h.store, resolver(params()))
    result = await port.negotiate(OFFER, tenant_id="tenant-a", idempotency_key="k")
    assert result.outcome is NegotiationOutcome.AWAITING_HUMAN_APPROVAL
    assert h.chat.sent == []


async def test_new_attempt_key_starts_a_new_negotiation_once_the_previous_one_is_terminal() -> None:
    h = harness(cooperative_seller())
    port = EngineNegotiationPort(h.engine, h.store, resolver(params()))
    a = await port.negotiate(OFFER, tenant_id="tenant-a", idempotency_key="negotiate:x:1")
    await h.engine.abort(a.negotiation_id, reason="buyer_cancelled", tenant_id="tenant-a")
    b = await port.negotiate(OFFER, tenant_id="tenant-a", idempotency_key="negotiate:x:2")
    assert a.negotiation_id != b.negotiation_id
    assert len(h.chat.opened) == 2


async def test_a_new_attempt_never_opens_a_second_chat_with_a_busy_seller() -> None:
    """D5-08: one active negotiation per seller. The graph routes the refusal to the human gate."""
    h = harness(cooperative_seller())
    port = EngineNegotiationPort(h.engine, h.store, resolver(params()))
    first = await port.negotiate(OFFER, tenant_id="tenant-a", idempotency_key="negotiate:x:1")
    second = await port.negotiate(OFFER, tenant_id="tenant-a", idempotency_key="negotiate:x:2")
    assert second.outcome is NegotiationOutcome.ESCALATED
    assert second.reason == "seller_busy"
    assert second.negotiation_id == first.negotiation_id
    assert second.price_minor is None
    assert len(h.chat.opened) == 1  # only the first negotiation touched the seller


async def test_escalation_carries_the_reason_and_no_price() -> None:
    h = harness(lambda agent, n: "Add me on WhatsApp for a better price.")
    port = EngineNegotiationPort(h.engine, h.store, resolver(params(semi_automatic=False)))
    await port.negotiate(OFFER, tenant_id="t", idempotency_key="k")
    result = await port.negotiate(OFFER, tenant_id="t", idempotency_key="k")
    assert result.outcome is NegotiationOutcome.ESCALATED
    assert result.price_minor is None
    assert result.reason is not None and "seller_off_platform_contact" in result.reason


def test_offer_requires_the_negotiation_keys() -> None:
    with pytest.raises(ValidationError):
        OfferInput.model_validate({"platform": "mock-b"})


class TestPhase1Counterparts:
    def test_higher_volume_and_framework_contract_are_allowed(self) -> None:
        p = params(
            allowed_counterparts=frozenset(
                {Counterpart.HIGHER_VOLUME, Counterpart.FRAMEWORK_CONTRACT}
            )
        )
        assert Counterpart.FRAMEWORK_CONTRACT in p.allowed_counterparts

    @pytest.mark.parametrize(
        "counterpart",
        [
            Counterpart.PREPAYMENT,
            Counterpart.PAYMENT_TERMS,
            Counterpart.GUARANTEE,
            Counterpart.PENALTY,
        ],
    )
    def test_other_counterparts_are_refused_even_if_the_profile_lists_them(
        self, counterpart: Counterpart
    ) -> None:
        with pytest.raises(ValidationError, match="ADR-900 Q15"):
            params(allowed_counterparts=frozenset({counterpart}))

    def test_target_cannot_exceed_max_discount(self) -> None:
        with pytest.raises(ValidationError):
            params(target_discount_bp=1600, max_discount_bp=1500)
