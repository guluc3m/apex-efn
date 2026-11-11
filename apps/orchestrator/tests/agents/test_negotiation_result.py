"""NegotiationResult accepts the #241 gate quote and nothing else priced outside ``agreed`` (issue #325)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apex.agents.ports import NegotiationOutcomeKind as K
from apex.agents.ports import NegotiationResult

PRICE = {"price_minor": 414, "currency": "EUR", "quantity": 5000}


def test_agreed_with_a_price_is_valid() -> None:
    NegotiationResult(outcome=K.AGREED, negotiation_id="n", **PRICE)


def test_agreed_without_a_price_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NegotiationResult(outcome=K.AGREED, negotiation_id="n")


def test_the_gate_quote_carries_a_price() -> None:
    NegotiationResult(
        outcome=K.ESCALATED, negotiation_id="n", reason="best_quote_above_target", **PRICE
    )


def test_the_gate_quote_needs_currency_and_quantity() -> None:
    with pytest.raises(ValidationError):
        NegotiationResult(
            outcome=K.ESCALATED,
            negotiation_id="n",
            reason="best_quote_above_target",
            price_minor=414,
        )


@pytest.mark.parametrize("reason", [None, "off_platform_payment"])
def test_an_escalation_with_another_reason_cannot_carry_a_price(reason: str | None) -> None:
    with pytest.raises(ValidationError):
        NegotiationResult(outcome=K.ESCALATED, negotiation_id="n", reason=reason, **PRICE)
