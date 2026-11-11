"""Seam guard between the engine's result and the graph's port (DEV-5 -> DEV-4).

`apex.agents.ports.NegotiationResult` validates what `apex.negotiation.node.to_result` produces. #241 gave one
escalation a price (the gate quote) and #361 relaxed the port to accept it; before that, the graph would have
raised the day the engine was wired. These tests keep the two in step without importing the graph itself.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apex.agents.ports import NegotiationOutcomeKind
from apex.agents.ports import NegotiationResult as GraphResult
from apex.negotiation.models import NegotiationOutcome
from apex.negotiation.node import to_result
from tests.negotiation.fakes import (
    cooperative_seller,
    harness,
    params,
    request,
    run_autonomous,
)


async def test_the_gate_quote_survives_the_graph_port() -> None:
    """#241: `escalated` + `best_quote_above_target` carries a price, and the port must accept it."""
    h = harness(lambda agent, n: "Sorry, our best price is EUR 4.40. That is as low as we can go.")
    session = await run_autonomous(
        h, await h.engine.start(request(params(semi_automatic=False)), idempotency_key="k")
    )

    result = to_result(session)
    assert result.outcome is NegotiationOutcome.ESCALATED
    assert result.reason == "best_quote_above_target"
    assert result.price_minor is not None

    port = GraphResult.model_validate(result.model_dump())

    assert port.outcome is NegotiationOutcomeKind.ESCALATED
    assert port.price_minor == result.price_minor
    assert port.currency == result.currency
    assert port.quantity == result.quantity


async def test_an_agreement_survives_the_graph_port() -> None:
    h = harness(cooperative_seller())
    session = await run_autonomous(
        h, await h.engine.start(request(params(semi_automatic=False)), idempotency_key="k")
    )

    result = to_result(session)
    assert result.outcome is NegotiationOutcome.AGREED

    port = GraphResult.model_validate(result.model_dump())
    assert port.outcome is NegotiationOutcomeKind.AGREED
    assert port.price_minor == result.price_minor


async def test_no_agreement_without_a_quote_survives_the_graph_port() -> None:
    h = harness(lambda agent, n: "Our price is EUR 4.65, no discounts.")
    session = await run_autonomous(
        h, await h.engine.start(request(params(semi_automatic=False)), idempotency_key="k")
    )

    result = to_result(session)
    assert result.outcome is NegotiationOutcome.NO_AGREEMENT
    assert result.price_minor is None

    port = GraphResult.model_validate(result.model_dump())
    assert port.price_minor is None


def test_the_port_still_refuses_a_price_on_any_other_escalation() -> None:
    """The relaxation is narrow: a price outside `agreed` and outside the #241 escalation is still a bug."""
    with pytest.raises(ValidationError):
        GraphResult(
            outcome=NegotiationOutcomeKind.ESCALATED,
            negotiation_id="n1",
            price_minor=414,
            currency="EUR",
            quantity=5000,
            reason="seller_off_platform_contact",
        )
