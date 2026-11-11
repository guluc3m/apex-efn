"""EvaluatorAgent: explainable ranking of a mission's offers (D4-12, spec 3.7).

Division of labour:

* **DEV-3's MCDA engine ranks** (``apex.domain.mcda``). Order, scores, contributions, exclusions and
  trade-offs come from it unchanged.
* **The profile comes from tenant config** (``scoring.profiles``). An unknown profile is a 404, never a
  default set of weights.
* **The LLM only narrates.** It receives the ranking as JSON and writes prose for the top offer. Its text is
  dropped if it contains a number that is not in the input. If narration fails for any reason the
  recommendation is returned without it: the numbers never depend on the model.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence

from apex.agents.missions import MissionStore
from apex.agents.offers import Offer, OfferAnalysis, OfferStore
from apex.agents.ports import PriceBand
from apex.agents.schemas import RecommendationNarrative
from apex.common.clock import Clock
from apex.contracts.generated.models import (
    Currency,
    ExcludedOffer,
    FinancialVerdict,
    Money,
    NullableMoney,
    Recommendation,
    SellerConfidenceBand,
)
from apex.domain import mcda
from apex.llm.config import LLMRole
from apex.llm.gateway import LLMGateway
from apex.llm.prompts import PromptRegistry
from apex.tenant_config.service import TenantConfigService

log = logging.getLogger(__name__)

# A standalone number: not part of an identifier such as an offer id ("o-2") or a word ("v3").
_NUMBER = re.compile(r"(?<![\w.\-])\d+(?:[.,]\d+)?(?![\w\-])")

MIN_RECOMMENDED_BAND = SellerConfidenceBand.medium
"""Criterion 11: a ``low`` (or worse) seller cannot go to purchase without a signed unblock, so it is never
recommended. A spec rule, not a tunable."""

EXCLUDED_PRICE_BANDS = frozenset({PriceBand.ATYPICAL, PriceBand.IMPLAUSIBLE})
"""Spec 3.7: the price band is a hard constraint. Out-of-range prices are excluded with a visible reason."""


class UnknownProfile(LookupError):
    pass


class NarrativeUngrounded(Exception):
    """The narrator used a number that is not in the ranking."""

    def __init__(self, numbers: set[str]) -> None:
        super().__init__(f"narrative contains numbers absent from the ranking: {sorted(numbers)}")
        self.numbers = numbers


class EvaluatorAgent:
    """``RecommendationProvider`` over the stored offers and their analysis."""

    def __init__(
        self,
        *,
        offers: OfferStore,
        missions: MissionStore,
        config: TenantConfigService,
        gateway: LLMGateway,
        prompts: PromptRegistry,
        clock: Clock,
        language: str = "en",
    ) -> None:
        self._offers, self._missions, self._config = offers, missions, config
        self._gateway, self._prompts, self._clock = gateway, prompts, clock
        self._language = language

    async def analysed_offers(
        self, tenant_id: str, mission_id: str
    ) -> list[tuple[Offer, OfferAnalysis | None]]:
        """The mission's offers with their analysis (``None`` when not analysed yet)."""
        if await self._missions.get(tenant_id, mission_id) is None:
            raise LookupError(f"mission {mission_id} not found")
        return [
            (o, await self._offers.get_analysis(tenant_id, o.id))
            for o in await self._offers.list_for_mission(tenant_id, mission_id)
        ]

    async def recommendation(
        self, *, tenant_id: str, mission_id: str, profile_id: str
    ) -> Recommendation:
        rows = await self.analysed_offers(tenant_id, mission_id)
        effective = await self._config.effective(tenant_id)
        profiles = effective.typed.scoring.profiles or {}
        if profile_id not in profiles:
            raise UnknownProfile(f"profile {profile_id} is not configured for this tenant")
        profile = mcda.Profile(
            profile_id=profile_id,
            weights={c: float(w) for c, w in profiles[profile_id].weights.items()},
        )
        config_version = f"v{effective.config_version}:{effective.content_hash[:12]}"

        analysed = [(o, a) for o, a in rows if a is not None]
        candidates = [_candidate(o, a) for o, a in analysed]
        price_excluded = [
            ExcludedOffer(offer_id=o.id, reasons=[f"price band {a.sanity.band.value}"])
            for o, a in analysed
            if a.sanity.band in EXCLUDED_PRICE_BANDS
        ]
        dropped = {e.offer_id for e in price_excluded}
        competing = [c for c in candidates if c.offer_id not in dropped]
        ranked, excluded = mcda.rank(
            competing, profile, mcda.Constraints(min_accepted_seller_band=MIN_RECOMMENDED_BAND)
        )
        rec = mcda.recommendation(
            mission_id=mission_id,
            profile_id=profile_id,
            ranked=ranked,
            excluded=[*price_excluded, *excluded],
            candidates=candidates,
            config_version=config_version,
            now=self._clock.now(),
        )
        rec = rec.model_copy(
            update={
                "alternatives": mcda.trade_offs(ranked, candidates),
                "savings": rec.savings.model_copy(
                    update={"vs_market_median": _vs_median(ranked, candidates)}
                ),
            }
        )
        if rec.ranking:
            narrative = await self._narrate(tenant_id, mission_id, rec, candidates)
            if narrative is not None:
                top = rec.ranking[0].model_copy(update={"narrative": narrative})
                rec = rec.model_copy(update={"ranking": [top, *rec.ranking[1:]]})
        return rec

    async def _narrate(
        self,
        tenant_id: str,
        mission_id: str,
        rec: Recommendation,
        candidates: Sequence[mcda.Candidate],
    ) -> str | None:
        by_id = {c.offer_id: c for c in candidates}
        ranking_json = json.dumps(
            [
                {
                    "rank": r.rank,
                    "offer_id": r.offer_id,
                    "score": r.score,
                    "unit_price_eur_minor": by_id[r.offer_id].landed_unit_cost_minor,
                    "seller_confidence_band": by_id[r.offer_id].seller_band.value,
                    "seller_confidence_score": by_id[r.offer_id].seller_confidence_score,
                }
                for r in rec.ranking
            ],
            ensure_ascii=False,
        )
        try:
            rendered = self._prompts.render(
                "narrator_recommendation", language=self._language, ranking_json=ranking_json
            )
            draft = await self._gateway.chat_structured(
                LLMRole.NARRATOR,
                rendered.messages,
                RecommendationNarrative,
                mission_id=mission_id,
                tenant_id=tenant_id,
                prompt_version=rendered.prompt_version,
            )
            _require_grounded(draft.narrative, ranking_json)
            return draft.narrative
        except Exception as exc:  # noqa: BLE001 - the ranking never depends on the narrator
            log.warning("recommendation narration skipped: %s", type(exc).__name__)
            return None


def _candidate(offer: Offer, analysis: OfferAnalysis) -> mcda.Candidate:
    return mcda.Candidate(
        offer_id=offer.id,
        # ponytail: the stored analysis keeps the verdict, not the landed breakdown, so the unit price in EUR
        # stands in for landed cost. Store LandedCostBreakdown.total per unit to rank on the real figure.
        landed_unit_cost_minor=offer.unit_price_eur_minor,
        seller_confidence_score=analysis.confidence.score,
        seller_band=SellerConfidenceBand(analysis.confidence.band.value),
        financial_verdict=FinancialVerdict(analysis.fit.verdict),
        platform=offer.platform_id,
        list_price_minor=offer.list_price_eur_minor,
    )


def _vs_median(
    ranked: Sequence[mcda.Ranked], candidates: Sequence[mcda.Candidate]
) -> NullableMoney:
    """Winner's saving against the median unit price of every analysed offer. Lower middle: exact."""
    if not ranked:
        return NullableMoney(None)
    prices = sorted(c.landed_unit_cost_minor for c in candidates)
    median = prices[(len(prices) - 1) // 2]
    winner = next(c for c in candidates if c.offer_id == ranked[0].offer_id)
    saving = median - winner.landed_unit_cost_minor
    if saving <= 0:
        return NullableMoney(None)
    return NullableMoney(Money(amount_minor=saving, currency=Currency.EUR))


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def _require_grounded(text: str, source: str) -> None:
    """Every number in the prose must appear in the ranking it was given."""
    invented = _numbers(text) - _numbers(source)
    if invented:
        raise NarrativeUngrounded(invented)


__all__ = ["EvaluatorAgent", "NarrativeUngrounded", "UnknownProfile"]
