"""Scraping orchestration and enrichment (D4-09, spec §3.2).

The orchestrator never touches a marketplace. It asks the browser worker (D5-01) for results, then does the
part that is *its* job:

* **Normalise** what each adapter returned into one :class:`~apex.agents.offers.Offer` shape.
* **Deduplicate** the same seller and product seen on several platforms, keeping the cheapest and recording
  what was dropped.
* **Convert** every price to EUR per unit at ingestion, through DEV-3's FX (D3-03), so nothing downstream
  has to think about currencies.
* **Persist** the offers and emit a mission event.

Adapters return **raw** signals; normalisation and scoring belong here and in DEV-3, never in the adapter.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from apex.agents.fx import FxUnavailable
from apex.agents.missions import MissionEventBus, MissionEventType, apply_event
from apex.agents.offers import Offer, OfferStore
from apex.agents.sourcing import PlanStep, SourcingPlan
from apex.common.clock import Clock

SUPPORTED_CURRENCIES = frozenset({"EUR", "USD", "CNY"})
"""Closed enum from spec §6. Anything else is rejected at ingestion rather than guessed."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RawOffer(_Model):
    """What an adapter returns: platform ids, a list price and the raw seller signals. No EUR, no bands."""

    platform_id: str = Field(min_length=1)
    platform_offer_id: str = Field(min_length=1)
    seller_id: str = Field(min_length=1)
    seller_name: str = ""
    product_id: str = Field(min_length=1)
    title: str = ""
    unit_price_minor: int = Field(ge=0)
    list_price_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(pattern="^(EUR|USD|CNY)$")
    quantity_available: int = Field(gt=0)
    moq: int = Field(default=1, ge=1)
    raw_signals: dict[str, Any] = Field(default_factory=dict)


class SkippedListing(_Model):
    """A listing the adapter found but did not return as an offer, with the contract's closed reason."""

    platform_id: str
    platform_offer_id: str
    reason: str
    currency_raw: str | None = None


class WorkerSearchResult(_Model):
    platform_id: str
    offers: list[RawOffer]
    skipped: list[SkippedListing] = Field(default_factory=list)
    truncated: bool = False


class WorkerError(Exception):
    """A worker failure the scraping service can react to.

    ``retryable`` comes from the worker contract's ``JobError``: a ``rate_limited`` or ``captcha`` failure is
    worth another attempt, a ``dom_changed`` one is not. The base lives here so the HTTP client can subclass
    it without a circular import.
    """

    retryable: bool = False


class BrowserWorkerPort(Protocol):
    """D5-01's internal API: dispatch a search job and collect what the adapter found."""

    async def search(
        self, *, tenant_id: str, mission_id: str, step: PlanStep, quantity: int
    ) -> WorkerSearchResult: ...

    async def seller_signals(
        self, *, tenant_id: str, mission_id: str, platform: str, seller_id: str
    ) -> Mapping[str, Any]:
        """Raw seller signals (spec §3.4.1). They feed the trust engine, never the LLM."""
        ...


class FxPort(Protocol):
    """DEV-3's ``apex.domain.fx.convert`` (D3-03). Returns EUR minor units for one unit."""

    async def to_eur_unit(
        self, *, amount_minor: int, currency: str, tenant_id: str
    ) -> tuple[int, bool]:
        """``(unit_price_eur_minor, fx_provisional)``."""
        ...


class DuplicateOffer(_Model):
    """An offer dropped because the same seller and product were already collected cheaper."""

    platform_id: str
    platform_offer_id: str
    seller_id: str
    product_id: str
    unit_price_eur_minor: int
    kept_platform_id: str
    kept_platform_offer_id: str


class ScrapeResult(_Model):
    mission_id: str
    platforms: list[str]
    collected: int
    kept: int
    duplicates: list[DuplicateOffer]
    skipped: list[SkippedListing] = Field(default_factory=list)
    """Listings the adapters refused, with the reason. Visible, never silently dropped."""
    fx_provisional: bool


async def _no_sleep(_seconds: float) -> None:
    """Default sleep for the retry loop. Tests inject a recorder so nothing waits."""


@dataclass(frozen=True)
class ScrapingDeps:
    worker: BrowserWorkerPort
    fx: FxPort
    offers: OfferStore
    bus: MissionEventBus
    clock: Clock
    max_attempts: int = 3
    """Attempts per plan step when the worker reports a retryable failure."""
    retry_backoff_s: float = 1.0
    sleep: Callable[[float], Awaitable[None]] = _no_sleep


class ScrapingService:
    def __init__(self, deps: ScrapingDeps) -> None:
        self._deps = deps

    async def scrape(
        self,
        *,
        tenant_id: str,
        mission_id: str,
        plan: SourcingPlan,
        quantity: int,
    ) -> ScrapeResult:
        """Run every step of the plan, then normalise, deduplicate, convert and persist."""
        raw: list[RawOffer] = []
        platforms: list[str] = []
        skipped: list[SkippedListing] = []
        for step in plan.steps:
            result = await self._search_with_retries(
                tenant_id=tenant_id, mission_id=mission_id, step=step, quantity=quantity
            )
            platforms.append(result.platform_id)
            raw.extend(result.offers)
            skipped.extend(result.skipped)
        kept, duplicates, provisional = await self._normalise(
            tenant_id=tenant_id, mission_id=mission_id, raw=raw
        )
        for offer in kept:
            await self._deps.offers.add(offer)
        outcome = ScrapeResult(
            mission_id=mission_id,
            platforms=sorted(set(platforms)),
            collected=len(raw),
            kept=len(kept),
            duplicates=duplicates,
            skipped=skipped,
            fx_provisional=provisional,
        )
        return outcome

    async def _search_with_retries(
        self, *, tenant_id: str, mission_id: str, step: PlanStep, quantity: int
    ) -> WorkerSearchResult:
        """One step, retried while the worker says the failure is retryable and attempts remain.

        A non-retryable failure (``dom_changed``, ``platform_disabled``) is raised immediately: retrying it
        would only burn the mission's time budget.
        """
        attempt = 1
        while True:
            try:
                return await self._deps.worker.search(
                    tenant_id=tenant_id, mission_id=mission_id, step=step, quantity=quantity
                )
            except WorkerError as exc:
                if not exc.retryable or attempt >= self._deps.max_attempts:
                    raise
                await self._deps.sleep(self._deps.retry_backoff_s * attempt)
                attempt += 1

    async def _signals_for(
        self,
        *,
        tenant_id: str,
        mission_id: str,
        platform: str,
        seller_id: str,
        cache: dict[tuple[str, str], tuple[Mapping[str, Any], bool]],
    ) -> tuple[Mapping[str, Any], bool]:
        """Seller signals for one seller, fetched once per mission, with ``gmv_12m`` in EUR.

        A failure here is not fatal: the offer keeps the listing signals and the trust engine answers
        ``insufficient_data`` for that seller, which is a visible verdict, not a silent zero.

        ``gmv_12m`` is converted here because ingestion is where every other amount becomes EUR: the trust
        engine refuses a non-EUR GMV (``gmv_not_eur``) rather than hiding a missing conversion. The returned
        flag is the ``fx_provisional`` of that conversion, so the gate sees a stale rate too.
        """
        key = (platform, seller_id)
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            signals = await self._deps.worker.seller_signals(
                tenant_id=tenant_id, mission_id=mission_id, platform=platform, seller_id=seller_id
            )
        except WorkerError:
            entry: tuple[Mapping[str, Any], bool] = ({}, False)
        else:
            entry = await self._gmv_to_eur(signals=signals, tenant_id=tenant_id)
        cache[key] = entry
        return entry

    async def _gmv_to_eur(
        self, *, signals: Mapping[str, Any], tenant_id: str
    ) -> tuple[Mapping[str, Any], bool]:
        """Return the signals with ``gmv_12m`` in EUR, never inventing a rate or a value.

        A currency outside the closed enum, or a rate the FX engine refuses, turns the GMV into ``None``:
        one of 21 signals is missing, visible as such, and the rest still score.
        """
        gmv = signals.get("gmv_12m")
        if not isinstance(gmv, Mapping):
            return signals, False
        currency = gmv.get("currency")
        amount_minor = gmv.get("amount_minor")
        if currency == "EUR":
            return signals, False
        if not isinstance(amount_minor, int) or currency not in SUPPORTED_CURRENCIES:
            return {**signals, "gmv_12m": None}, False
        try:
            converted, provisional = await self._deps.fx.to_eur_unit(
                amount_minor=amount_minor, currency=str(currency), tenant_id=tenant_id
            )
        except FxUnavailable:
            # A missing rate must not cost the whole mission: the engine scores the other signals and the
            # snapshot shows the gap.
            return {**signals, "gmv_12m": None}, False
        return {**signals, "gmv_12m": {"amount_minor": converted, "currency": "EUR"}}, provisional

    async def _normalise(
        self, *, tenant_id: str, mission_id: str, raw: Sequence[RawOffer]
    ) -> tuple[list[Offer], list[DuplicateOffer], bool]:
        """Convert to EUR, then keep one offer per (seller, product): the cheapest."""
        provisional = False
        converted: list[tuple[Offer, RawOffer]] = []
        signals_cache: dict[tuple[str, str], tuple[Mapping[str, Any], bool]] = {}
        for item in raw:
            unit_eur, fx_provisional = await self._deps.fx.to_eur_unit(
                amount_minor=item.unit_price_minor, currency=item.currency, tenant_id=tenant_id
            )
            provisional = provisional or fx_provisional
            list_eur: int | None = None
            if item.list_price_minor is not None:
                list_eur, list_provisional = await self._deps.fx.to_eur_unit(
                    amount_minor=item.list_price_minor, currency=item.currency, tenant_id=tenant_id
                )
                provisional = provisional or list_provisional
            seller_signals, signals_provisional = await self._signals_for(
                tenant_id=tenant_id,
                mission_id=mission_id,
                platform=item.platform_id,
                seller_id=item.seller_id,
                cache=signals_cache,
            )
            provisional = provisional or signals_provisional
            offer = Offer(
                id=f"{item.platform_id}:{item.platform_offer_id}",
                tenant_id=tenant_id,
                mission_id=mission_id,
                platform_id=item.platform_id,
                seller_id=item.seller_id,
                product_id=item.product_id,
                title=item.title,
                moq=item.moq,
                unit_price_eur_minor=unit_eur,
                list_price_eur_minor=list_eur,
                currency="EUR",
                quantity=item.quantity_available,
                seller_name=item.seller_name,
                collected_at=self._deps.clock.now(),
                raw_signals={
                    **dict(item.raw_signals),
                    **({"seller_signals": dict(seller_signals)} if seller_signals else {}),
                },
            )
            converted.append((offer, item))

        # Cheapest first, then a stable tie-break so the result never depends on arrival order.
        converted.sort(key=lambda pair: (pair[0].unit_price_eur_minor, pair[0].id))
        kept: list[Offer] = []
        seen: dict[tuple[str, str], Offer] = {}
        duplicates: list[DuplicateOffer] = []
        for offer, item in converted:
            key = (offer.seller_id, offer.product_id)
            winner = seen.get(key)
            if winner is None:
                seen[key] = offer
                kept.append(offer)
                continue
            duplicates.append(
                DuplicateOffer(
                    platform_id=offer.platform_id,
                    platform_offer_id=item.platform_offer_id,
                    seller_id=offer.seller_id,
                    product_id=offer.product_id,
                    unit_price_eur_minor=offer.unit_price_eur_minor,
                    kept_platform_id=winner.platform_id,
                    kept_platform_offer_id=winner.id.split(":", 1)[1],
                )
            )
        return kept, duplicates, provisional

    async def record_events(self, *, mission: Any, result: ScrapeResult) -> Any:
        """Append the sourcing event to the mission and publish it to the SSE bus."""
        at = self._deps.clock.now()
        updated = apply_event(
            mission,
            MissionEventType.PLAN_READY,
            at=at,
            payload={
                "offers_collected": result.collected,
                "offers_kept": result.kept,
                "platforms": result.platforms,
                "duplicates": len(result.duplicates),
                "fx_provisional": result.fx_provisional,
            },
        )
        self._deps.bus.publish(mission.id, updated.events[-1])
        return updated


def offers_from_fixture(payload: Mapping[str, Any], *, platform_id: str) -> list[RawOffer]:
    """Turn one mock-marketplace product document into a :class:`RawOffer`.

    Used by the criterion 3 test: the fixtures in ``apps/mock-marketplace/fixtures`` are the same data the
    mock serves, so the orchestrator is exercised against realistic shapes without a network.
    """
    return [
        RawOffer(
            platform_id=platform_id,
            platform_offer_id=str(product["id"]),
            seller_id=str(product["sellerId"]),
            product_id=str(product["productKey"]),
            title=str(product.get("title", "")),
            unit_price_minor=int(product["unitPriceMinor"]),
            list_price_minor=(
                int(product["listPriceMinor"])
                if product.get("listPriceMinor") is not None
                else None
            ),
            currency=str(product["currency"]),
            quantity_available=int(product.get("moq") or 1),
            moq=int(product.get("moq") or 1),
            raw_signals={"certifications": list(product.get("certifications", []))},
        )
        for product in payload.get("products", [])
        if product.get("platform") == platform_id
        # The currency enum is closed (EUR|USD|CNY): an offer quoted in anything else cannot be converted
        # and is not collected. The adapter still reports it in its own logs.
        and product.get("currency") in SUPPORTED_CURRENCIES
    ]


__all__ = [
    "BrowserWorkerPort",
    "DuplicateOffer",
    "FxPort",
    "RawOffer",
    "ScrapeResult",
    "SkippedListing",
    "ScrapingDeps",
    "SUPPORTED_CURRENCIES",
    "ScrapingService",
    "WorkerError",
    "WorkerSearchResult",
    "offers_from_fixture",
]
