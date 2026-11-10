"""Playbook for spec 3.6 steps 1-8 (D5-07b). Pure functions: no I/O, no clock, no LLM.

The buyer anchors at the deepest discount it may ask for (``max_discount``) and concedes upwards along a
ladder with decreasing increments until ``target_discount``. Any seller quote at or below the target
price ends the bargaining: the agent then sends a written summary and the human decides (step 6: the
agent negotiates, it never buys).
"""

from __future__ import annotations

from dataclasses import dataclass

from apex.negotiation.guardrails import BP_DENOMINATOR, IncomingVerdict, price_floor_minor
from apex.negotiation.models import (
    BEST_QUOTE_ABOVE_TARGET,
    Intent,
    NegotiationOutcome,
    NegotiationSession,
    Plan,
    Quote,
)
from apex.negotiation.text import find_prices

# Rounds reserved outside the ladder: the opening message and the written summary.
_RESERVED_ROUNDS = 2


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def target_price_minor(reference_minor: int, target_discount_bp: int) -> int:
    """Highest unit price the buyer is happy with: reference minus ``target_discount``, rounded up."""
    return _ceil_div(reference_minor * (BP_DENOMINATOR - target_discount_bp), BP_DENOMINATOR)


def counter_ladder(anchor_minor: int, target_minor: int, rungs: int) -> list[int]:
    """Increasing proposals from ``anchor`` to ``target`` with non-increasing increments (step 4).

    Each increment is half of what is left (rounded up), and the last rung is always the target.
    Duplicates are dropped, so the ladder may be shorter than ``rungs`` when the gap is small.
    """
    if rungs < 1:
        raise ValueError("rungs must be >= 1")
    if anchor_minor > target_minor:
        raise ValueError("anchor must not exceed target")
    ladder = [anchor_minor]
    remaining = target_minor - anchor_minor
    for i in range(1, rungs):
        step = remaining if i == rungs - 1 else _ceil_div(remaining, 2)
        if step <= 0:
            break
        ladder.append(ladder[-1] + step)
        remaining -= step
    if ladder[-1] != target_minor:
        ladder.append(target_minor)
    return ladder


def build_ladder(session: NegotiationSession) -> list[int]:
    p = session.params
    rungs = max(1, p.max_rounds - _RESERVED_ROUNDS)
    anchor = price_floor_minor(p.limits())
    target = target_price_minor(p.reference_price_minor, p.target_discount_bp)
    return counter_ladder(anchor, target, rungs)


@dataclass(frozen=True, slots=True)
class Stop:
    outcome: NegotiationOutcome
    reason: str


Decision = Plan | Stop


def select_quote(
    verdict: IncomingVerdict,
    currency: str,
    at_round: int,
    *,
    offered: frozenset[int] = frozenset(),
) -> Quote | None:
    """Deterministic fallback when no grounded extraction exists: the lowest fresh price in ``currency``.

    ``offered`` are the prices the buyer side already proposed. Sellers echo them ("EUR 3.79 is too low,
    our best is EUR 4.12"), so they are never the seller's quote. Sellers usually list volume tiers in
    decreasing order and the buyer asks for the largest volume, so the lowest fresh price is the relevant tier.
    """
    prices = [p.minor for p in verdict.prices if p.currency == currency and p.minor not in offered]
    return (
        Quote(unit_price_minor=min(prices), currency=currency, at_round=at_round)
        if prices
        else None
    )


def offered_prices(session: NegotiationSession) -> frozenset[int]:
    """Prices in the negotiation currency that the agent or a human already sent to the seller."""
    currency = session.params.currency
    return frozenset(
        p.minor
        for m in session.transcript
        if m.role != "seller"
        for p in find_prices(m.text)
        if p.currency == currency
    )


def quote_for_the_gate(session: NegotiationSession) -> Quote | None:
    """The seller's best grounded quote when it is a real discount, for a human to judge (#241).

    A seller holding above the buyer's target still offered something below the listed price. Ending as
    ``no_agreement`` would drop that discount silently, so the engine stops and the gate decides.
    """
    best = session.best_quote
    if best is None or best.unit_price_minor >= session.params.reference_price_minor:
        return None
    return best


def decide(session: NegotiationSession, verdict: IncomingVerdict, quote: Quote | None) -> Decision:
    """Next step after a seller turn. ``quote`` has already passed the sanity re-check."""
    p = session.params
    if verdict.escalate:
        return Stop(
            NegotiationOutcome.ESCALATED, ",".join(sorted(h.code.value for h in verdict.hits))
        )
    target = target_price_minor(p.reference_price_minor, p.target_discount_bp)
    if (
        quote is not None
        and quote.unit_price_minor <= target
        and session.rounds_sent < p.max_rounds
    ):
        return Plan(intent=Intent.SUMMARY, price_minor=quote.unit_price_minor)
    # The last round is always kept for the written summary.
    if session.rounds_sent >= p.max_rounds - 1:
        if quote_for_the_gate(session) is not None:
            return Stop(NegotiationOutcome.ESCALATED, BEST_QUOTE_ABOVE_TARGET)
        return Stop(NegotiationOutcome.NO_AGREEMENT, "max_rounds")

    foreign = [pr for pr in verdict.prices if pr.currency != p.currency]
    if quote is None and foreign:
        return Plan(intent=Intent.REQUEST_CURRENCY)

    if not session.quotes and not session.asked_for_price:
        return Plan(intent=Intent.REQUEST_PRICE)
    if session.next_rung >= len(session.ladder):
        if quote_for_the_gate(session) is not None:
            return Stop(NegotiationOutcome.ESCALATED, BEST_QUOTE_ABOVE_TARGET)
        return Stop(NegotiationOutcome.NO_AGREEMENT, "ladder_exhausted")
    price = session.ladder[session.next_rung]
    intent = Intent.ANCHOR if session.next_rung == 0 else Intent.COUNTER
    return Plan(intent=intent, price_minor=price)
