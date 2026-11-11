"""Offers as the orchestrator stores them, and the per-offer analysis attached to each (D4-10).

An offer is what D4-09 collected and normalised: a price in EUR minor units per unit, the platform and
seller it came from, and the raw signals the trust engine needs. The analysis (seller confidence, price
sanity, financial fit) is *attached*, never recomputed here: this module stores what the engines returned,
together with the versions that produced it, so a decision can be audited later.

Nothing in this module computes a band, a score or a verdict.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from apex.agents.ports import ConfidenceBand, FitOutcome, SanityOutcome, TrustOutcome


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Offer(_Model):
    """One normalised offer. ``unit_price_eur_minor`` is EUR per unit, integer minor units."""

    id: str
    tenant_id: str
    mission_id: str
    platform_id: str
    seller_id: str
    product_id: str
    title: str = ""
    """Product title as the adapter saw it. Display only: no engine reads it."""
    moq: int = Field(default=1, ge=1)
    """As the adapter reported it (``RawOffer.moq``, which defaults to 1)."""
    unit_price_eur_minor: int = Field(ge=0)
    list_price_eur_minor: int | None = Field(default=None, ge=0)
    """The seller's list price per unit when the adapter saw one. Used only to report savings."""
    currency: str = Field(pattern="^(EUR|USD|CNY)$")
    quantity: int = Field(gt=0)
    seller_name: str = ""
    collected_at: datetime
    raw_signals: dict[str, Any] = Field(default_factory=dict)
    """Raw seller signals as the adapter returned them. Input to the trust engine, never to the LLM."""


class OfferAnalysis(_Model):
    """The three engine verdicts for one offer, with the versions that produced them."""

    offer_id: str
    confidence: TrustOutcome
    sanity: SanityOutcome
    fit: FitOutcome
    analysed_at: datetime
    negotiation_id: str | None = None
    """The negotiation opened for this offer once the gate cleared it. None = never negotiated."""

    @property
    def is_analysed(self) -> bool:
        return True


class AnalysedOffer(_Model):
    """An offer with its analysis. What ``GET /v1/missions/{id}/offers`` returns."""

    offer: Offer
    analysis: OfferAnalysis | None = None


class SellerConfidenceRecord(_Model):
    """One entry of a seller's confidence history. Append-only: recomputing adds a record."""

    seller_id: str
    tenant_id: str
    platform_id: str = ""
    """The platform the snapshot came from, for the ``platform`` metric label."""
    flags: tuple[str, ...] = ()
    """Structural manipulation flags reported by the trust engine (D3-06). Closed set."""
    band: ConfidenceBand
    score: int | None
    model_version: str
    config_version: str
    computed_at: datetime
    signals_used: int = Field(ge=0)


class OfferStore(Protocol):
    """Tenant-scoped storage for offers and their analysis (D2-05 implements the real one)."""

    async def add(self, offer: Offer) -> Offer: ...

    async def list_for_mission(self, tenant_id: str, mission_id: str) -> list[Offer]: ...

    async def set_analysis(self, tenant_id: str, analysis: OfferAnalysis) -> None: ...

    async def get_analysis(self, tenant_id: str, offer_id: str) -> OfferAnalysis | None: ...

    async def get(self, tenant_id: str, offer_id: str) -> Offer | None: ...


class SellerConfidenceStore(Protocol):
    """Append-only confidence history per seller (D2-03's ``seller_confidences`` table)."""

    async def append(self, record: SellerConfidenceRecord) -> SellerConfidenceRecord: ...

    async def history(self, tenant_id: str, seller_id: str) -> list[SellerConfidenceRecord]: ...

    async def latest(self, tenant_id: str, seller_id: str) -> SellerConfidenceRecord | None: ...


class InMemoryOfferStore:
    def __init__(self) -> None:
        self._offers: dict[tuple[str, str], Offer] = {}
        self._analysis: dict[tuple[str, str], OfferAnalysis] = {}
        self._lock = asyncio.Lock()

    async def add(self, offer: Offer) -> Offer:
        async with self._lock:
            key = (offer.tenant_id, offer.id)
            existing = self._offers.get(key)
            if existing is not None:
                if existing != offer:
                    raise ValueError(f"offer {offer.id} already stored with different content")
                return existing
            self._offers[key] = offer
            return offer

    async def get(self, tenant_id: str, offer_id: str) -> Offer | None:
        return self._offers.get((tenant_id, offer_id))

    async def list_for_mission(self, tenant_id: str, mission_id: str) -> list[Offer]:
        found = [
            o for (t, _), o in self._offers.items() if t == tenant_id and o.mission_id == mission_id
        ]
        return sorted(found, key=lambda o: (o.unit_price_eur_minor, o.id))

    async def set_analysis(self, tenant_id: str, analysis: OfferAnalysis) -> None:
        async with self._lock:
            self._analysis[(tenant_id, analysis.offer_id)] = analysis

    async def get_analysis(self, tenant_id: str, offer_id: str) -> OfferAnalysis | None:
        return self._analysis.get((tenant_id, offer_id))


class InMemorySellerConfidenceStore:
    """Append-only history. ``latest`` is the last appended record for the seller."""

    def __init__(self) -> None:
        self._records: list[SellerConfidenceRecord] = []
        self._lock = asyncio.Lock()

    async def append(self, record: SellerConfidenceRecord) -> SellerConfidenceRecord:
        async with self._lock:
            self._records.append(record)
            return record

    async def history(self, tenant_id: str, seller_id: str) -> list[SellerConfidenceRecord]:
        return [r for r in self._records if r.tenant_id == tenant_id and r.seller_id == seller_id]

    async def latest(self, tenant_id: str, seller_id: str) -> SellerConfidenceRecord | None:
        history = await self.history(tenant_id, seller_id)
        return history[-1] if history else None


def offer_payload(offer: Offer) -> Mapping[str, Any]:
    """The shape the engine ports consume. Kept in one place so nodes and tests cannot drift."""
    return {
        "offer_id": offer.id,
        "tenant_id": offer.tenant_id,
        "mission_id": offer.mission_id,
        "platform_id": offer.platform_id,
        "seller_id": offer.seller_id,
        "product_id": offer.product_id,
        "unit_price_eur_minor": offer.unit_price_eur_minor,
        "list_price_eur_minor": offer.list_price_eur_minor,
        "currency": offer.currency,
        "quantity": offer.quantity,
        "raw_signals": offer.raw_signals,
    }


__all__ = [
    "AnalysedOffer",
    "InMemoryOfferStore",
    "InMemorySellerConfidenceStore",
    "Offer",
    "OfferAnalysis",
    "OfferStore",
    "SellerConfidenceRecord",
    "SellerConfidenceStore",
    "offer_payload",
]
