"""Incremental simulation session (D5-11): one exchange at a time, so the model answers while you watch.

``run_scenario`` runs every buyer to completion and returns a report; the page then replays messages that were
generated minutes earlier. This session exposes the same pipeline as small steps:

- ``start``   search and pick a supplier for every buyer, open the thread and draft the opening message;
- ``step``    advance one buyer (or all of them) by one exchange, which performs the real LLM calls;
- ``all``     run to the end for when you do not want to click.

Each step is a real round trip to whatever answers on the LLM endpoint, so the latency the page shows is the
model's. Nothing here changes the rules: the playbook picks the prices, the personas the seller's, and the
engine guards discard any sentence whose number drifted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apex.common.errors import Problem
from apex.negotiation.engine import NegotiationEngine, NegotiationError
from apex.negotiation.models import (
    BEST_QUOTE_ABOVE_TARGET,
    NegotiationOutcome,
    NegotiationSession,
)
from apex.negotiation.sim.market import (
    MarketItem,
    Marketplace,
    MarketplaceError,
    MarketplaceUnavailable,
    SupplierMetrics,
)
from apex.negotiation.sim.models import BuyerProfile, Money, ScenarioConfig, Step, TranscriptLine
from apex.negotiation.sim.pipeline import (
    EngineFactory,
    SimContext,
    _first_at,
    _negotiate,
    _pick,
    _seller_reports,
)

TERMINAL = frozenset({"agreed", "escalated", "no_agreement", "error"})


def money(minor: int, currency: str) -> Money:
    return Money(amount_minor=minor, currency=currency)  # type: ignore[arg-type]


@dataclass
class BuyerState:
    """Everything the page needs to draw one buyer, plus the engine that produces it."""

    profile: BuyerProfile
    engine: NegotiationEngine | None = None
    session: NegotiationSession | None = None
    chosen: MarketItem | None = None
    supplier_name: str = ""
    asking: Money | None = None
    status: str = "pending"
    reason: str | None = None
    final: Money | None = None
    steps: list[Step] = field(default_factory=list)
    transcript: list[TranscriptLine] = field(default_factory=list)
    seen_seq: int = 0
    started: bool = False


class SimSession:
    """One demo run, advanced by the page a message at a time."""

    def __init__(
        self,
        config: ScenarioConfig,
        marketplace: Marketplace,
        ctx: SimContext,
        factory: EngineFactory,
        run_id: str,
        *,
        owns_marketplace: bool,
    ) -> None:
        self.config = config
        self.market = marketplace
        self.ctx = ctx
        self.factory = factory
        self.run_id = run_id
        self._owns_marketplace = owns_marketplace
        self._buyers = [BuyerState(profile=profile) for profile in config.buyers]
        self._items: dict[str, MarketItem] = {}
        self._seller_cache: dict[str, SupplierMetrics] = {}
        self.started_at = ctx.clock.now()

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Search, pick and open the thread for every buyer. One LLM call each (the opening message)."""
        await self.market.health()
        for state in self._buyers:
            await self._ensure_started(state)

    async def step(self, buyer_id: str | None = None) -> None:
        """Advance one buyer by one exchange; with no id, advance every buyer (one round)."""
        targets = [self._target(buyer_id)] if buyer_id else list(self._buyers)
        for state in targets:
            if state.status in TERMINAL:
                continue
            if not state.started:
                await self._ensure_started(state)
                continue
            await self._advance(state)

    async def run_all(self) -> None:
        """Step until every buyer is terminal. Guarded so a stuck engine cannot loop forever."""
        guard = 4 * self.config.limits.max_rounds + 8
        for _ in range(guard):
            if self.finished:
                return
            await self.step()
        for state in self._buyers:
            if state.status not in TERMINAL:
                self._fail(state, "step_limit")

    async def close(self) -> None:
        await self.ctx.gateway.aclose()
        if self._owns_marketplace:
            await self.market.aclose()

    @property
    def finished(self) -> bool:
        return all(state.status in TERMINAL for state in self._buyers)

    # ------------------------------------------------------------------ per buyer

    async def _ensure_started(self, state: BuyerState) -> None:
        if state.started:
            return
        state.started = True
        buyer = state.profile
        try:
            offers = await self.market.search(self.config.search_query, limit=50)
        except MarketplaceUnavailable:
            raise
        except MarketplaceError as exc:
            self._fail(state, f"search failed: {exc}")
            return
        for offer in offers:
            self._items.setdefault(offer.item_id, offer)
        candidates = [
            offer
            for offer in offers
            if offer.currency == buyer.currency and offer.min_order <= buyer.quantity
        ]
        self._step(
            state,
            "search",
            f"{len(offers)} offers for {self.config.search_query!r}; "
            f"{len(candidates)} buyable in {buyer.currency} at {buyer.quantity} units",
        )
        if not candidates:
            self._fail(state, f"no {buyer.currency} offer within the buyer's quantity")
            return

        chosen = await _pick(candidates, self.market, self._seller_cache)
        state.chosen = chosen
        state.asking = money(chosen.unit_price_minor, chosen.currency)
        state.supplier_name = chosen.supplier_name or chosen.supplier_id
        self._step(
            state,
            "pick",
            f"{chosen.item_id} — {state.supplier_name} at {state.asking.amount_minor / 100:.2f} "
            f"{state.asking.currency}",
            state.asking,
        )
        try:
            engine, session = await _negotiate(self.ctx, buyer, chosen, self.factory)
        except MarketplaceUnavailable:
            raise
        except (NegotiationError, MarketplaceError) as exc:
            self._fail(state, f"negotiation failed: {exc}")
            return
        state.engine = engine
        state.session = session
        state.status = "running"
        self._step(state, "open", f"thread {session.chat_id}", at=_first_at(session))
        await self._sync(state)

    async def _advance(self, state: BuyerState) -> None:
        if state.engine is None or state.session is None:
            return
        try:
            state.session = await state.engine.advance(
                state.session.id, tenant_id=self.config.tenant_id
            )
        except MarketplaceUnavailable:
            raise
        except (NegotiationError, MarketplaceError) as exc:
            self._fail(state, f"negotiation failed: {exc}")
            return
        await self._sync(state)

    async def _sync(self, state: BuyerState) -> None:
        """Read what was said since the last step and turn it into transcript lines and steps."""
        session = state.session
        if session is None or session.chat_id is None:
            return
        try:
            thread = await self.market.messages(session.chat_id, after_seq=state.seen_seq)
        except MarketplaceError:
            thread = []
        for message in thread:
            if message.seq <= state.seen_seq:
                continue
            state.seen_seq = message.seq
            line = TranscriptLine(
                seq=message.seq,
                role="seller" if message.author == "supplier" else "buyer",
                text=message.body,
                at=message.sent_at,
            )
            state.transcript.append(line)
            self._step(
                state,
                "message",
                message.body if message.author == "buyer" else f"seller: {message.body}",
                at=message.sent_at,
            )
        if session.terminal:
            self._finish_state(state)

    def _finish_state(self, state: BuyerState) -> None:
        session = state.session
        if session is None:
            return
        status = session.status
        reason = session.stop_reason
        if status is NegotiationOutcome.AGREED and session.agreed is not None:
            state.status = "agreed"
            state.final = money(session.agreed.unit_price_minor, session.agreed.currency)
        elif status is NegotiationOutcome.ESCALATED:
            state.status = "escalated"
            best = session.best_quote
            if reason == BEST_QUOTE_ABOVE_TARGET and best is not None:
                state.final = money(best.unit_price_minor, best.currency)
        elif status is NegotiationOutcome.STOPPED_ANOMALOUS_PRICE:
            state.status = "escalated"
            best = session.best_quote
            if best is not None:
                state.final = money(best.unit_price_minor, best.currency)
        else:
            state.status = "no_agreement"
        state.reason = reason
        self._step(state, state.status, reason or state.status, state.final)

    def _fail(self, state: BuyerState, reason: str) -> None:
        state.status = "error"
        state.reason = reason
        self._step(state, "error", reason)

    def _step(
        self,
        state: BuyerState,
        kind: str,
        detail: str,
        price: Money | None = None,
        at: datetime | None = None,
    ) -> None:
        state.steps.append(
            Step(kind=kind, at=at or self.ctx.clock.now(), detail=detail, price=price)  # type: ignore[arg-type]
        )

    def _target(self, buyer_id: str) -> BuyerState:
        for state in self._buyers:
            if state.profile.id == buyer_id:
                return state
        raise Problem(404, "Not Found", detail=f"unknown buyer {buyer_id}", reason="unknown_buyer")

    # ------------------------------------------------------------------ view

    async def view(self) -> dict[str, Any]:
        """The whole state the page needs. Small enough to re-render on every step."""
        sellers = await _seller_reports(self.market, self._items, self._seller_cache)
        return {
            "run_id": self.run_id,
            "finished": self.finished,
            "items": [
                {
                    "item_id": item.item_id,
                    "title": item.title,
                    "supplier_id": item.supplier_id,
                    "supplier_name": item.supplier_name,
                    "unit_price": money(item.unit_price_minor, item.currency).model_dump(
                        mode="json"
                    ),
                    "moq": item.min_order,
                }
                for item in sorted(self._items.values(), key=lambda entry: entry.item_id)
            ],
            "sellers": sellers,
            "buyers": [self._buyer_view(state) for state in self._buyers],
        }

    @staticmethod
    def _buyer_view(state: BuyerState) -> dict[str, Any]:
        return {
            "buyer_id": state.profile.id,
            "name": state.profile.name,
            "outcome": state.status,
            "reason": state.reason,
            "final_price": state.final.model_dump(mode="json") if state.final else None,
            "chosen": None
            if state.chosen is None
            else {
                "item_id": state.chosen.item_id,
                "supplier_id": state.chosen.supplier_id,
                "supplier_name": state.supplier_name,
                "asking_price": state.asking.model_dump(mode="json") if state.asking else None,
            },
            "steps": [step.model_dump(mode="json") for step in state.steps],
            "transcript": [line.model_dump(mode="json") for line in state.transcript],
        }


__all__ = ["BuyerState", "SimSession", "money"]
