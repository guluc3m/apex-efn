"""Trust, Sanity and Finance nodes (D4-10).

Each node is a thin adapter: it resolves the tenant's effective config, calls the DEV-3 engine through its
port, and persists what the engine returned together with the versions that produced it. No node computes a
band, a score or a verdict, and none of them calls an LLM.

The nodes also enforce **freshness**: a seller snapshot older than ``seller.snapshot_max_age_days`` is
recomputed before it is used, so a decision never rests on stale signals (spec §3.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Protocol

from apex.agents.offers import (
    Offer,
    OfferAnalysis,
    OfferStore,
    SellerConfidenceRecord,
    SellerConfidenceStore,
    offer_payload,
)
from apex.agents.ports import (
    AuditPort,
    FinancePort,
    FitOutcome,
    SanityOutcome,
    SanityPort,
    TrustOutcome,
    TrustPort,
)
from apex.common.clock import Clock
from apex.common.metrics import (
    CONFIDENCE_BANDS,
    MANIPULATION_FLAGS,
    PRICE_BANDS,
    closed,
    get_metrics,
)


class AnalysisConfig(Protocol):
    """The slice of effective tenant config the nodes need. Unset keys raise (never a default)."""

    def config_version(self, tenant_id: str) -> str: ...

    def seller_snapshot_max_age_days(self, tenant_id: str) -> int: ...


class AnalysisDeps:
    """Collaborators of the nodes. Plain class so callers can build it positionally or by keyword."""

    __slots__ = ("trust", "sanity", "finance", "offers", "confidence", "audit", "config", "clock")

    def __init__(
        self,
        *,
        trust: TrustPort,
        sanity: SanityPort,
        finance: FinancePort,
        offers: OfferStore,
        confidence: SellerConfidenceStore,
        audit: AuditPort,
        config: AnalysisConfig,
        clock: Clock,
    ) -> None:
        self.trust = trust
        self.sanity = sanity
        self.finance = finance
        self.offers = offers
        self.confidence = confidence
        self.audit = audit
        self.config = config
        self.clock = clock


class StaleConfigError(Exception):
    """The config key a node needs is unset. Loud: a node never substitutes a default."""


class AnalysisNodes:
    def __init__(self, deps: AnalysisDeps) -> None:
        self._deps = deps

    # ------------------------------------------------------------------ trust

    async def score_seller(
        self,
        *,
        tenant_id: str,
        seller_id: str,
        signals: Mapping[str, Any],
        captured_at: datetime | None = None,
        force: bool = False,
    ) -> SellerConfidenceRecord:
        """Recompute seller confidence unless a fresh snapshot exists, and append it to the history.

        ``force`` is what ``POST /sellers/{id}/confidence/recompute`` sets: it always recomputes and always
        writes an audit event, because a forced recomputation is an operator action.
        """
        now = self._deps.clock.now()
        max_age = timedelta(days=self._deps.config.seller_snapshot_max_age_days(tenant_id))
        latest = None if force else await self._deps.confidence.latest(tenant_id, seller_id)
        if latest is not None and now - latest.computed_at < max_age:
            return latest
        outcome: TrustOutcome = await self._deps.trust.score(
            {
                "seller_id": seller_id,
                "raw_signals": dict(signals),
                "collected_at": captured_at or now,
            },
            tenant_id=tenant_id,
        )
        record = SellerConfidenceRecord(
            seller_id=seller_id,
            tenant_id=tenant_id,
            platform_id=str(signals.get("platform_id", "")),
            flags=tuple(str(f) for f in getattr(outcome, "flags", ())),
            band=outcome.band,
            score=outcome.score,
            model_version=outcome.model_version,
            config_version=self._deps.config.config_version(tenant_id),
            computed_at=now,
            signals_used=_count_signals(signals),
        )
        await self._deps.confidence.append(record)
        _record_confidence(record)
        if force:
            await self._audit(
                tenant_id,
                {
                    "event": "seller_confidence_recomputed",
                    "seller_id": seller_id,
                    "band": record.band.value,
                    "model_version": record.model_version,
                    "config_version": record.config_version,
                    "signals_used": record.signals_used,
                },
            )
        return record

    # ------------------------------------------------------------------ per-offer analysis

    async def analyse_offer(self, *, tenant_id: str, offer: Offer) -> OfferAnalysis:
        """Run trust, sanity and finance for one offer and persist the result."""
        payload = offer_payload(offer)
        confidence = await self.score_seller(
            tenant_id=tenant_id,
            seller_id=offer.seller_id,
            signals={**offer.raw_signals, "platform_id": offer.platform_id},
            captured_at=offer.collected_at,
        )
        sanity: SanityOutcome = await self._deps.sanity.check(
            payload, tenant_id=tenant_id, price_minor=offer.unit_price_eur_minor
        )
        _record_sanity(offer.platform_id, sanity)
        fit: FitOutcome = await self._deps.finance.fit(payload, tenant_id=tenant_id)
        analysis = OfferAnalysis(
            offer_id=offer.id,
            confidence=TrustOutcome(
                band=confidence.band, score=confidence.score, model_version=confidence.model_version
            ),
            sanity=sanity,
            fit=fit,
            analysed_at=self._deps.clock.now(),
        )
        await self._deps.offers.set_analysis(tenant_id, analysis)
        return analysis

    async def analyse_mission(self, *, tenant_id: str, mission_id: str) -> list[OfferAnalysis]:
        """Analyse every offer of a mission that has no analysis yet. Idempotent per offer."""
        results: list[OfferAnalysis] = []
        for offer in await self._deps.offers.list_for_mission(tenant_id, mission_id):
            existing = await self._deps.offers.get_analysis(tenant_id, offer.id)
            results.append(existing or await self.analyse_offer(tenant_id=tenant_id, offer=offer))
        return results

    # ------------------------------------------------------------------ read side

    async def mission_offers(
        self, *, tenant_id: str, mission_id: str
    ) -> list[tuple[Offer, OfferAnalysis | None]]:
        offers = await self._deps.offers.list_for_mission(tenant_id, mission_id)
        return [(o, await self._deps.offers.get_analysis(tenant_id, o.id)) for o in offers]

    async def seller_history(
        self, *, tenant_id: str, seller_id: str
    ) -> list[SellerConfidenceRecord]:
        return await self._deps.confidence.history(tenant_id, seller_id)

    async def _audit(self, tenant_id: str, event: Mapping[str, Any]) -> None:
        await self._deps.audit.append(event, tenant_id=tenant_id)


def _record_sanity(platform_id: str, outcome: SanityOutcome) -> None:
    """``apex.price_sanity.*`` — band and relative deviation, never an amount."""
    metrics = get_metrics()
    metrics.price_sanity_checks.add(
        1, {"platform": platform_id, "band": closed(outcome.band.value, PRICE_BANDS)}
    )
    deviation = getattr(outcome, "relative_deviation", None)
    if deviation is not None:
        metrics.price_sanity_relative_deviation.record(float(deviation), {"platform": platform_id})


def _record_confidence(record: SellerConfidenceRecord) -> None:
    """``apex.seller_confidence.*`` — band, score and manipulation flags."""
    metrics = get_metrics()
    metrics.seller_confidence_assessments.add(
        1, {"platform": record.platform_id, "band": closed(record.band.value, CONFIDENCE_BANDS)}
    )
    if record.score is not None:
        metrics.seller_confidence_score.record(record.score, {"platform": record.platform_id})
    for flag in record.flags:
        metrics.seller_confidence_flags.add(
            1, {"platform": record.platform_id, "flag": closed(flag, MANIPULATION_FLAGS)}
        )


def _count_signals(signals: Mapping[str, Any]) -> int:
    """How many raw signals were present. ``seller.min_signals`` counts present signals (ADR-900 Q3)."""
    return sum(1 for value in signals.values() if value is not None)


__all__ = ["AnalysisConfig", "AnalysisDeps", "AnalysisNodes", "StaleConfigError"]
