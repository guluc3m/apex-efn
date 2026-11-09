"""Test doubles for the negotiation engine: a scripted seller chat, a fake LLM and a fake sanity check.

``ScriptedChat`` replays seller lines written in the same style as the D5-04 mock marketplace personas.
Each seller turn is a function of the agent's last message, so tests cover counter-offers end to end.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from apex.common.clock import FixedClock
from apex.negotiation.engine import NegotiationEngine, OpenRequest
from apex.negotiation.models import (
    NegotiationContext,
    NegotiationParams,
    NegotiationSession,
    Plan,
    Quote,
    SanityBand,
)
from apex.negotiation.ports import (
    ChatLine,
    Draft,
    Extraction,
    InMemoryAccountSendLog,
    InMemoryNegotiationStore,
    InMemorySellerGuard,
    InMemorySellerSendLog,
)
from apex.negotiation.templates import render
from apex.negotiation.text import find_prices

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
SUPPORTED = frozenset({"EUR", "USD", "CNY"})
T = "tenant-a"

SellerTurn = Callable[[str, int], str | None]
"""(agent's last message, agent message count) -> seller reply, or None for silence."""


@dataclass
class ScriptedChat:
    seller: SellerTurn
    opened: list[dict[str, str]] = field(default_factory=list)
    lines: list[ChatLine] = field(default_factory=list)
    sent: list[str] = field(default_factory=list)

    async def open(self, *, platform: str, seller_id: str, product_id: str, account_id: str) -> str:
        self.opened.append(
            {
                "platform": platform,
                "seller_id": seller_id,
                "product_id": product_id,
                "account_id": account_id,
            }
        )
        return "chat-1"

    async def send(self, chat_id: str, text: str) -> None:
        self.sent.append(text)
        self.lines.append(ChatLine(len(self.lines) + 1, "buyer", text))
        reply = self.seller(text, len(self.sent))
        if reply is not None:
            self.lines.append(ChatLine(len(self.lines) + 1, "seller", reply))

    async def read(self, chat_id: str, *, after_seq: int) -> Sequence[ChatLine]:
        return [line for line in self.lines if line.seq > after_seq]


class TemplateDrafter:
    """Behaves like a compliant LLM: returns the template, optionally overridden per call."""

    def __init__(self, overrides: Sequence[str] = (), *, fail: bool = False) -> None:
        self.overrides = list(overrides)
        self.fail = fail
        self.calls = 0

    async def draft(
        self, plan: Plan, session: NegotiationSession, seller_text: str | None
    ) -> Draft:
        self.calls += 1
        if self.fail:
            raise RuntimeError("llm down")
        if self.overrides:
            return Draft(text=self.overrides.pop(0), tokens=50)
        return Draft(text=render(plan, session), tokens=50)


class RegexExtractor:
    """Behaves like a well-behaved LLM extractor: the lowest price in the message."""

    def __init__(self, *, lie: int | None = None) -> None:
        self.lie = lie

    async def extract(self, seller_text: str, session: NegotiationSession) -> Extraction:
        if self.lie is not None:
            return Extraction(
                unit_price_minor=self.lie, currency=session.params.currency, tokens=10
            )
        prices = find_prices(seller_text)
        if not prices:
            return Extraction(unit_price_minor=None, currency=None, tokens=10)
        best = min(prices, key=lambda p: p.minor)
        return Extraction(unit_price_minor=best.minor, currency=best.currency, tokens=10)


class BandSanity:
    """Fake DEV-3 sanity check: anything below ``floor`` (EUR minor) is atypical."""

    def __init__(self, floor: int = 300) -> None:
        self.floor = floor
        self.checked: list[Quote] = []

    async def check(self, quote: Quote, *, session: NegotiationSession) -> SanityBand:
        self.checked.append(quote)
        return SanityBand.ATYPICAL if quote.unit_price_minor < self.floor else SanityBand.NORMAL


def params(**overrides: object) -> NegotiationParams:
    # Test values only: real limits come from tenant config (ADR-900 Q7 and #96).
    base: dict[str, object] = {
        "currency": "EUR",
        "reference_price_minor": 465,
        "quantity": 5000,
        "target_discount_bp": 800,
        "max_discount_bp": 1500,
        "max_rounds": 6,
        "max_tokens": 20_000,
        "max_messages_per_hour": 20,
        "max_message_chars": 1200,
        "supported_currencies": SUPPORTED,
        "context": NegotiationContext(
            product_title="nitrile gloves M (box of 100)", destination="Madrid", recurring=True
        ),
    }
    base.update(overrides)
    return NegotiationParams.model_validate(base)


def request(p: NegotiationParams | None = None) -> OpenRequest:
    return OpenRequest(
        tenant_id="tenant-a",
        platform="mock-b",
        seller_id="b-standard-coop",
        product_id="b-gloves-03",
        account_id="acct-1",
        config_version="7",
        params=p or params(),
    )


@dataclass
class Harness:
    engine: NegotiationEngine
    chat: ScriptedChat
    drafter: TemplateDrafter
    sanity: BandSanity
    store: InMemoryNegotiationStore
    send_log: InMemoryAccountSendLog
    seller_log: InMemorySellerSendLog
    seller_guard: InMemorySellerGuard
    clock: FixedClock


def harness(
    seller: SellerTurn,
    *,
    drafter: TemplateDrafter | None = None,
    extractor: RegexExtractor | None = None,
    sanity: BandSanity | None = None,
) -> Harness:
    chat = ScriptedChat(seller)
    d = drafter or TemplateDrafter()
    s = sanity or BandSanity()
    store = InMemoryNegotiationStore()
    log = InMemoryAccountSendLog()
    seller_log = InMemorySellerSendLog()
    guard = InMemorySellerGuard()
    clock = FixedClock(NOW)
    counter = itertools.count(1)
    engine = NegotiationEngine(
        transport=chat,
        drafter=d,
        extractor=extractor or RegexExtractor(),
        sanity=s,
        store=store,
        send_log=log,
        seller_log=seller_log,
        seller_guard=guard,
        clock=clock,
        new_id=lambda: f"id-{next(counter)}",
    )
    return Harness(engine, chat, d, s, store, log, seller_log, guard, clock)


async def run_autonomous(
    h: Harness, session: NegotiationSession, *, steps: int = 20
) -> NegotiationSession:
    for _ in range(steps):
        h.clock.advance(timedelta(minutes=1))
        session = await h.engine.advance(session.id, tenant_id=T)
        if session.terminal:
            break
    return session


async def run_semi_automatic(
    h: Harness, session: NegotiationSession, *, steps: int = 20
) -> NegotiationSession:
    for _ in range(steps):
        h.clock.advance(timedelta(minutes=1))
        if session.pending is not None:
            session = await h.engine.approve(
                session.id, session.pending.id, approver="buyer-1", tenant_id=T
            )
        session = await h.engine.advance(session.id, tenant_id=T)
        if session.terminal:
            break
    return session


def cooperative_seller(floor: int = 428, list_price: int = 465) -> SellerTurn:
    """Mirrors the D5-04 ``cooperative`` persona: tiers, concessions to a floor, written confirmation."""
    state = {"ask": list_price, "agreed": False}

    def turn(agent: str, n: int) -> str | None:
        if "confirm" in agent.lower() or "confirmar" in agent.lower():
            return (
                f"Confirmed in writing: EUR {state['ask'] / 100:.2f} per unit for 5000 units, FOB."
            )
        prices = [p.minor for p in find_prices(agent)]
        if "tiers" in agent.lower():
            return "Our volume tiers are: 300-999 units: EUR 4.65; 1000+ units: EUR 4.40."
        if not prices:
            return f"Unit price is EUR {state['ask'] / 100:.2f}, minimum order 300 units."
        offer = prices[-1]
        if offer >= floor:
            state["ask"] = offer
            return f"OK, we can accept EUR {offer / 100:.2f} per unit for 5000 units."
        state["ask"] = max(floor, state["ask"] - (state["ask"] - offer) // 2)
        return f"Sorry, that is too low. Our best price is EUR {state['ask'] / 100:.2f} per unit."

    return turn
