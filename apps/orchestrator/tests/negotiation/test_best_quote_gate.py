"""#241: a quote between the target and the list price goes to the human gate, not to /dev/null.

The playbook refuses to concede past `target_discount`, which is right. What was wrong is what happened when
the seller held just above it: the negotiation ended `no_agreement` and a real discount disappeared without a
human seeing it. The engine now stops with `escalated` / `best_quote_above_target` and puts the best quote in
`NegotiationResult.price_minor`, so DEV-4's gate can judge it.
"""

from __future__ import annotations

from apex.negotiation.models import NegotiationOutcome
from apex.negotiation.node import to_result
from apex.negotiation.playbook import target_price_minor
from tests.negotiation.fakes import (
    cooperative_seller,
    harness,
    params,
    request,
    run_autonomous,
)

# List EUR 4.65, target 8%, max 15%. A seller holding at EUR 4.40 is above the target and still a 5% discount.
LIST = 465
TARGET = target_price_minor(LIST, 800)


def holds_at(price_minor: int):  # type: ignore[no-untyped-def]
    def turn(agent: str, n: int) -> str:
        return f"Sorry, our best price is EUR {price_minor / 100:.2f}. That is as low as we can go."

    return turn


async def test_a_quote_above_the_target_goes_to_the_gate_with_its_price() -> None:
    h = harness(holds_at(440))
    session = await run_autonomous(
        h, await h.engine.start(request(params(semi_automatic=False)), idempotency_key="k")
    )

    assert session.status is NegotiationOutcome.ESCALATED
    assert session.stop_reason == "best_quote_above_target"
    assert session.best_quote is not None
    assert session.best_quote.unit_price_minor == 440 > TARGET

    result = to_result(session)
    assert result.outcome is NegotiationOutcome.ESCALATED
    assert result.price_minor == 440  # the gate needs the number
    assert result.currency == "EUR"
    assert result.quantity == 5000
    assert result.reason == "best_quote_above_target"


async def test_the_agent_never_concedes_past_the_target_to_get_there() -> None:
    h = harness(holds_at(440))
    await run_autonomous(
        h, await h.engine.start(request(params(semi_automatic=False)), idempotency_key="k")
    )
    # The ladder opens at the floor allowed by max_discount and climbs to the target, never past it.
    from apex.negotiation.text import find_prices

    offered = [p.minor for message in h.chat.sent for p in find_prices(message)]
    assert offered, "the agent did send offers"
    assert max(offered) <= TARGET


async def test_a_seller_who_never_discounts_ends_without_agreement() -> None:
    h = harness(holds_at(LIST))
    session = await run_autonomous(
        h, await h.engine.start(request(params(semi_automatic=False)), idempotency_key="k")
    )

    assert session.status is NegotiationOutcome.NO_AGREEMENT
    assert session.stop_reason in {"max_rounds", "ladder_exhausted"}
    assert to_result(session).price_minor is None  # nothing to judge: no discount was ever offered


async def test_a_quote_at_the_target_is_still_an_agreement() -> None:
    h = harness(cooperative_seller())
    session = await run_autonomous(
        h, await h.engine.start(request(params(semi_automatic=False)), idempotency_key="k")
    )

    assert session.status is NegotiationOutcome.AGREED
    assert session.stop_reason == "seller_confirmed_in_writing"
    result = to_result(session)
    assert result.price_minor is not None
    assert result.price_minor <= TARGET
