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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

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
    product_id: str = Field(min_length=1)
    title: str = ""
    unit_price_minor: int = Field(ge=0)
    list_price_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(pattern="^(EUR|USD|CNY)$")
    quantity_available: int = Field(gt=0)
    moq: int = Field(default=1, ge=1)
    raw_signals: dict[str, Any] = Field(default_factory=dict)


class WorkerSearchResult(_Model):
    platform_id: str
    offers: list[RawOffer]
    truncated: bool = False


class BrowserWorkerPort(Protocol):
    """D5-01's internal API: dispatch a search job and collect what the adapter found."""

    async def search(
        self, *, tenant_id: str, mission_id: str, step: PlanStep, quantity: int
    ) -> WorkerSearchResult: ...


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
    fx_provisional: bool


@dataclass(frozen=True)
class ScrapingDeps:
    worker: BrowserWorkerPort
    fx: FxPort
    offers: OfferStore
    bus: MissionEventBus
    clock: Clock


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
        for step in plan.steps:
            result = await self._deps.worker.search(
                tenant_id=tenant_id, mission_id=mission_id, step=step, quantity=quantity
            )
            platforms.append(result.platform_id)
            raw.extend(result.offers)
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
            fx_provisional=provisional,
        )
        return outcome

    async def _normalise(
        self, *, tenant_id: str, mission_id: str, raw: Sequence[RawOffer]
    ) -> tuple[list[Offer], list[DuplicateOffer], bool]:
        """Convert to EUR, then keep one offer per (seller, product): the cheapest."""
        provisional = False
        converted: list[tuple[Offer, RawOffer]] = []
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
            offer = Offer(
                id=f"{item.platform_id}:{item.platform_offer_id}",
                tenant_id=tenant_id,
                mission_id=mission_id,
                platform_id=item.platform_id,
                seller_id=item.seller_id,
                product_id=item.product_id,
                unit_price_eur_minor=unit_eur,
                list_price_eur_minor=list_eur,
                currency="EUR",
                quantity=item.quantity_available,
                collected_at=self._deps.clock.now(),
                raw_signals=dict(item.raw_signals),
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
    "ScrapingDeps",
    "SUPPORTED_CURRENCIES",
    "ScrapingService",
    "WorkerSearchResult",
    "offers_from_fixture",
]
