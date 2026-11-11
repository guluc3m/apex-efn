"""The simulation pipeline: search, pick, negotiate, report (D5-11).

For every buyer profile, in order:

1. **search** the mock marketplace;
2. **pick** the cheapest offer in the buyer's currency that the buyer's volume can actually buy
   (``min_order <= quantity``), breaking ties by supplier rating;
3. **open** the marketplace thread and **negotiate** with the real ``NegotiationEngine`` in autonomous
   mode, one message per advance;
4. map the terminal state to an outcome: ``agreed``, ``escalated`` (the human gate), ``no_agreement``
   or ``error``.

The engine is real; the ports are in-memory, the LLM is the OpenAI-compatible stub (or templates when no
``llm_url`` is given) and the sanity re-check is the neutral stand-in of :mod:`apex.negotiation.sim.sanity`.
No database, no Docker, no network beyond the two configured URLs.

Outcome mapping notes:

- ``AGREED`` carries the agreed unit price.
- ``ESCALATED`` with ``stop_reason == "best_quote_above_target"`` carries the seller's best quote: the
  gate needs the number to judge it (#241). Other escalations carry no price.
- ``STOPPED_ANOMALOUS_PRICE`` is also mapped to ``escalated`` with the best quote, because the product
  stops for the gate instead of discarding the offer (criterion 13); the stand-in sanity check never
  produces it, the real DEV-3 engine does.
- Everything else terminal is ``no_agreement``.

Buyers run sequentially and keep distinct account ids and idempotency keys. mock-c opens one thread per
item, so two buyers that pick the same item share a thread; that is accepted for the demo (each run keeps
its own transcript and steps), and a scenario with different currencies or items avoids it entirely.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from apex.common.clock import Clock, SystemClock
from apex.common.ids import IdGenerator
from apex.negotiation.engine import NegotiationEngine, NegotiationError, OpenRequest
from apex.negotiation.llm import LLMDrafter, LLMExtractor
from apex.negotiation.models import (
    BEST_QUOTE_ABOVE_TARGET,
    NegotiationContext,
    NegotiationOutcome,
    NegotiationParams,
    NegotiationSession,
    TranscriptMessage,
)
from apex.negotiation.ports import (
    InMemoryAccountSendLog,
    InMemoryNegotiationStore,
    InMemorySellerGuard,
    InMemorySellerSendLog,
)
from apex.negotiation.sim.market import (
    HttpMarketplace,
    MarketItem,
    Marketplace,
    MarketplaceError,
    MarketplaceUnavailable,
    SupplierMetrics,
)
from apex.negotiation.sim.models import (
    CURRENCIES,
    BuyerProfile,
    BuyerRun,
    ChosenOffer,
    ItemReport,
    Money,
    ScenarioConfig,
    ScenarioReport,
    SellerReport,
    Step,
    StepKind,
    TranscriptLine,
    money,
)
from apex.negotiation.sim.sanity import NormalSanity
from apex.negotiation.sim.stub_llm import SimGateway, build_gateway
from apex.negotiation.sim.transport import MarketChatTransport
from apex.negotiation.templates import format_price
from apex.negotiation.text import find_prices

__all__ = [
    "CONFIG_VERSION",
    "PLATFORM",
    "EngineFactory",
    "SimContext",
    "default_engine_factory",
    "run_scenario",
]

PLATFORM = "mock-c"
"""Platform id the simulation negotiates on."""

CONFIG_VERSION = "sim-v1"
"""Version label for the scenario's in-code limits (no tenant config is read)."""

EngineFactory = Callable[["SimContext", str], NegotiationEngine]
"""Builds an engine for one buyer mission. Injectable so tests can replace ports."""


@dataclass(frozen=True, slots=True)
class SimContext:
    """Collaborators shared by the buyers of one scenario run."""

    market: Marketplace
    gateway: SimGateway
    clock: Clock
    config: ScenarioConfig
    run_id: str = ""


def default_engine_factory(ctx: SimContext, mission_id: str) -> NegotiationEngine:
    """The real negotiation engine with in-memory ports and the simulation adapters."""
    ids = IdGenerator(ctx.clock)
    return NegotiationEngine(
        transport=MarketChatTransport(ctx.market, run_id=ctx.run_id),
        drafter=LLMDrafter(ctx.gateway, mission_id=mission_id),
        extractor=LLMExtractor(ctx.gateway, mission_id=mission_id),
        sanity=NormalSanity(),
        store=InMemoryNegotiationStore(),
        send_log=InMemoryAccountSendLog(),
        seller_log=InMemorySellerSendLog(),
        seller_guard=InMemorySellerGuard(),
        clock=ctx.clock,
        new_id=ids.new_id,
    )


async def run_scenario(
    config: ScenarioConfig,
    *,
    client: Marketplace | None = None,
    engine_factory: EngineFactory | None = None,
    clock: Clock | None = None,
) -> ScenarioReport:
    """Run every buyer of ``config`` and return the JSON-serialisable report.

    ``client``, ``engine_factory`` and ``clock`` exist so tests can drive the pipeline without HTTP;
    production callers (the CLI) pass only the config. ``MarketplaceUnavailable`` propagates so the CLI
    can exit 1.
    """
    clock = clock or SystemClock()
    market = (
        client
        if client is not None
        else HttpMarketplace(
            config.marketplace_url,
            llm_url=config.llm_url,
            llm_api_key=config.llm_api_key,
            llm_model=config.llm_model,
        )
    )
    gateway = build_gateway(config.llm_url, api_key=config.llm_api_key, model=config.llm_model)
    factory = engine_factory or default_engine_factory
    run_id = uuid4().hex[:8]
    ctx = SimContext(market=market, gateway=gateway, clock=clock, config=config, run_id=run_id)
    seen_items: dict[str, MarketItem] = {}
    seller_cache: dict[str, SupplierMetrics] = {}
    started_at = clock.now()
    buyers: list[BuyerRun] = []
    try:
        await market.health()
        for buyer in config.buyers:
            buyers.append(await _run_buyer(ctx, buyer, factory, seen_items, seller_cache))
        sellers = await _seller_reports(market, seen_items, seller_cache)
    finally:
        await gateway.aclose()
        if client is None:
            await market.aclose()
    return ScenarioReport(
        started_at=started_at,
        finished_at=clock.now(),
        marketplace_url=config.marketplace_url,
        llm_url=config.llm_url,
        items=[
            ItemReport(
                item_id=item.item_id,
                title=item.title,
                supplier_id=item.supplier_id,
                supplier_name=item.supplier_name,
                unit_price=money(item.unit_price_minor, item.currency),
                moq=item.min_order,
            ).model_dump(mode="json")
            for item in sorted(seen_items.values(), key=lambda entry: entry.item_id)
        ],
        sellers=sellers,
        buyers=buyers,
    )


async def _run_buyer(
    ctx: SimContext,
    buyer: BuyerProfile,
    factory: EngineFactory,
    seen_items: dict[str, MarketItem],
    seller_cache: dict[str, SupplierMetrics],
) -> BuyerRun:
    steps: list[Step] = []
    transcript: list[TranscriptLine] = []

    def step(
        kind: StepKind, detail: str, price: Money | None = None, at: datetime | None = None
    ) -> None:
        steps.append(Step(kind=kind, at=at or ctx.clock.now(), detail=detail, price=price))

    def fail(reason: str) -> BuyerRun:
        step("error", reason)
        return BuyerRun(
            buyer_id=buyer.id,
            name=buyer.name,
            steps=steps,
            transcript=transcript,
            outcome="error",
            reason=reason,
        )

    try:
        offers = await ctx.market.search(ctx.config.search_query, limit=50)
    except MarketplaceUnavailable:
        raise
    except MarketplaceError as exc:
        return fail(f"search failed: {exc}")
    for offer in offers:
        seen_items.setdefault(offer.item_id, offer)

    candidates = [
        offer
        for offer in offers
        if offer.currency == buyer.currency and offer.min_order <= buyer.quantity
    ]
    step(
        "search",
        f"{len(offers)} offers for {ctx.config.search_query!r}; "
        f"{len(candidates)} buyable in {buyer.currency} at {buyer.quantity} units",
    )
    if not candidates:
        return fail(f"no {buyer.currency} offer within the buyer's quantity")

    chosen = await _pick(candidates, ctx.market, seller_cache)
    asking = money(chosen.unit_price_minor, chosen.currency)
    supplier_name = chosen.supplier_name or chosen.supplier_id
    step(
        "pick",
        f"{chosen.item_id} — {supplier_name} at "
        f"{format_price(chosen.unit_price_minor, chosen.currency)}/unit",
        asking,
    )

    try:
        engine, session = await _negotiate(ctx, buyer, chosen, factory)
    except MarketplaceUnavailable:
        raise
    except (NegotiationError, MarketplaceError) as exc:
        return fail(f"negotiation failed: {exc}")

    step("open", f"thread {session.chat_id}", at=_first_at(session))
    for line in session.transcript:
        _append_transcript(transcript, line)
        _append_message_step(steps, line, buyer)
    seen = len(session.transcript)

    max_steps = 2 * ctx.config.limits.max_rounds + 4  # loop guard, not a business limit
    try:
        for _ in range(max_steps):
            if session.terminal:
                break
            session = await engine.advance(session.id, tenant_id=ctx.config.tenant_id)
            for line in session.transcript[seen:]:
                _append_transcript(transcript, line)
                _append_message_step(steps, line, buyer)
            seen = len(session.transcript)
    except MarketplaceUnavailable:
        raise
    except (NegotiationError, MarketplaceError) as exc:
        return fail(f"negotiation failed: {exc}")

    # The marketplace thread is the authoritative record of what was said, in order: read it once at the
    # end instead of stitching engine slices (which a re-read can duplicate or reorder).
    if session.chat_id:
        try:
            thread = await ctx.market.messages(session.chat_id, after_seq=0)
        except MarketplaceError:
            thread = []
        if thread:
            transcript = [
                TranscriptLine(
                    seq=message.seq,
                    role="seller" if message.author == "supplier" else "buyer",
                    text=message.body,
                    at=message.sent_at,
                )
                for message in thread
            ]
    return _finish(ctx, buyer, chosen, supplier_name, asking, session, steps, transcript)


async def _negotiate(
    ctx: SimContext, buyer: BuyerProfile, chosen: MarketItem, factory: EngineFactory
) -> tuple[NegotiationEngine, NegotiationSession]:
    params = NegotiationParams(
        currency=buyer.currency,
        reference_price_minor=chosen.unit_price_minor,
        quantity=buyer.quantity,
        target_discount_bp=buyer.target_discount_bp,
        max_discount_bp=buyer.max_discount_bp,
        max_rounds=ctx.config.limits.max_rounds,
        max_tokens=ctx.config.limits.max_tokens,
        max_messages_per_hour=ctx.config.limits.max_messages_per_hour,
        max_message_chars=ctx.config.limits.max_message_chars,
        supported_currencies=CURRENCIES,
        language=ctx.config.limits.language,
        semi_automatic=False,  # the simulation runs the autonomous mode
        context=NegotiationContext(product_title=chosen.title, recurring=True),
    )
    mission_id = f"sim-{buyer.id}"
    request = OpenRequest(
        tenant_id=ctx.config.tenant_id,
        platform=PLATFORM,
        seller_id=chosen.supplier_id,
        product_id=chosen.item_id,
        account_id=buyer.account_id,
        config_version=CONFIG_VERSION,
        params=params,
        offer_id=chosen.item_id,
        mission_id=mission_id,
        trace_id=mission_id,
    )
    engine = factory(ctx, mission_id)
    session = await engine.start(request, idempotency_key=f"sim:{buyer.id}:{chosen.item_id}")
    return engine, session


async def _pick(
    candidates: list[MarketItem],
    market: Marketplace,
    seller_cache: dict[str, SupplierMetrics],
) -> MarketItem:
    """Cheapest offer; equal prices are broken by the supplier's rating (unknown rating ranks last)."""
    best_price = min(offer.unit_price_minor for offer in candidates)
    cheapest = [offer for offer in candidates if offer.unit_price_minor == best_price]
    if len(cheapest) == 1:
        return cheapest[0]
    scored: list[tuple[float, MarketItem]] = []
    for offer in cheapest:
        metrics = await _metrics(market, seller_cache, offer.supplier_id)
        rating = metrics.rating_avg if metrics.rating_avg is not None else float("-inf")
        scored.append((rating, offer))
    return max(scored, key=lambda pair: pair[0])[1]


async def _metrics(
    market: Marketplace, cache: dict[str, SupplierMetrics], supplier_id: str
) -> SupplierMetrics:
    cached = cache.get(supplier_id)
    if cached is not None:
        return cached
    try:
        metrics = await market.metrics(supplier_id)
    except MarketplaceUnavailable:
        raise
    except MarketplaceError:
        # A supplier without metrics is still a valid offer; the rating simply stays unknown.
        metrics = SupplierMetrics(
            supplier_id=supplier_id, name=supplier_id, rating_avg=None, orders_total=None
        )
    cache[supplier_id] = metrics
    return metrics


async def _seller_reports(
    market: Marketplace,
    items: dict[str, MarketItem],
    cache: dict[str, SupplierMetrics],
) -> list[dict[str, Any]]:
    names = {
        item.supplier_id: item.supplier_name
        for item in items.values()
        if item.supplier_name is not None
    }
    suppliers = sorted({item.supplier_id for item in items.values()})
    reports: list[dict[str, Any]] = []
    for supplier_id in suppliers:
        metrics = await _metrics(market, cache, supplier_id)
        reports.append(
            SellerReport(
                supplier_id=supplier_id,
                name=names.get(supplier_id) or metrics.name,
                rating_avg=metrics.rating_avg,
                orders_total=metrics.orders_total,
                persona=metrics.persona,
            ).model_dump(mode="json")
        )
    return reports


def _first_at(session: NegotiationSession) -> datetime | None:
    return session.transcript[0].at if session.transcript else None


def _append_transcript(target: list[TranscriptLine], line: TranscriptMessage) -> None:
    target.append(
        TranscriptLine(
            seq=line.seq,
            role="seller" if line.role == "seller" else "buyer",
            text=line.text,
            at=line.at,
        )
    )


def _append_message_step(steps: list[Step], line: TranscriptMessage, buyer: BuyerProfile) -> None:
    """One step per message the buyer side sent (the offer ladder of the UI)."""
    if line.role == "seller":
        return
    prices = [p for p in find_prices(line.text) if p.currency == buyer.currency]
    price = money(prices[0].minor, buyer.currency) if prices else None
    steps.append(Step(kind="message", at=line.at, detail=line.text, price=price))


def _finish(
    ctx: SimContext,
    buyer: BuyerProfile,
    chosen: MarketItem,
    supplier_name: str,
    asking: Money,
    session: NegotiationSession,
    steps: list[Step],
    transcript: list[TranscriptLine],
) -> BuyerRun:
    status = session.status
    reason = session.stop_reason
    final: Money | None = None
    outcome: StepKind
    if status is NegotiationOutcome.AGREED and session.agreed is not None:
        outcome = "agreed"
        final = money(session.agreed.unit_price_minor, session.agreed.currency)
    elif status is NegotiationOutcome.ESCALATED:
        outcome = "escalated"
        best = session.best_quote
        if reason == BEST_QUOTE_ABOVE_TARGET and best is not None:
            final = money(best.unit_price_minor, best.currency)
    elif status is NegotiationOutcome.STOPPED_ANOMALOUS_PRICE:
        outcome = "escalated"
        stopped = session.best_quote
        if stopped is not None:
            final = money(stopped.unit_price_minor, stopped.currency)
    else:
        outcome = "no_agreement"
        if reason is None:
            reason = "step_limit" if not session.terminal else f"status:{status.value}"

    detail = reason or outcome
    steps.append(Step(kind=outcome, at=ctx.clock.now(), detail=detail, price=final))
    return BuyerRun(
        buyer_id=buyer.id,
        name=buyer.name,
        chosen=ChosenOffer(
            item_id=chosen.item_id,
            supplier_id=chosen.supplier_id,
            supplier_name=supplier_name,
            asking_price=asking,
        ).model_dump(mode="json"),
        steps=steps,
        transcript=transcript,
        outcome=outcome,
        final_price=final,
        reason=reason,
    )
