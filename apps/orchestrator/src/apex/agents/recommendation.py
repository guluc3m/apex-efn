"""EvaluatorAgent: explainable ranking of a mission's offers (D4-12).

Division of labour, and the reason this module exists:

* **The MCDA engine ranks.** ``McdaPort.rank`` is DEV-3's deterministic scoring (D3-09). The order, the
  scores and the per-criterion contributions come from it and are returned unchanged.
* **Code computes the savings.** List price and market median are arithmetic over the mission's offers, done
  here with integers, never by the model.
* **The LLM only narrates.** It receives the ranking as JSON and writes prose. Its ``top_offer_id`` is
  ignored: the first offer of the ranking is the top offer, full stop. Its text is rejected if it contains a
  number that is not in the input, so the prose cannot invent a price or a score.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from apex.agents.offers import Offer, OfferAnalysis
from apex.agents.schemas import RecommendationNarrative
from apex.common.clock import Clock
from apex.llm.config import LLMRole
from apex.llm.gateway import LLMGateway
from apex.llm.prompts import PromptRegistry

# A standalone number: not part of an identifier such as an offer id ("o-2") or a word ("v3").
_NUMBER = re.compile(r"(?<![\w.\-])\d+(?:[.,]\d+)?(?![\w\-])")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Candidate(_Model):
    """One offer as the MCDA engine sees it: the numbers plus the analysis verdicts."""

    offer_id: str
    platform_id: str
    seller_id: str
    unit_price_eur_minor: int = Field(ge=0)
    list_price_eur_minor: int | None
    quantity: int = Field(gt=0)
    seller_confidence_score: int | None
    seller_confidence_band: str
    price_band: str
    financial_verdict: str


class RankedCandidate(_Model):
    """What the MCDA engine returns for one candidate. ``contributions`` is the explanation."""

    offer_id: str
    rank: int = Field(ge=1)
    score: str
    """Decimal string: scores are exact, never floats."""
    contributions: dict[str, str] = Field(default_factory=dict)
    excluded_reason: str | None = None


class RankedRecommendation(_Model):
    ranked: list[RankedCandidate]
    profile: str
    config_version: str


class McdaPort(Protocol):
    """DEV-3's ``apex.domain.mcda.rank`` (D3-09). Deterministic; the only thing that decides order."""

    async def rank(
        self,
        candidates: Sequence[Candidate],
        *,
        profile: str,
        tenant_id: str,
        config_version: str,
    ) -> RankedRecommendation: ...


class Savings(_Model):
    """Integer minor units per unit. ``None`` when the reference does not exist for this offer."""

    vs_list_price_eur_minor: int | None
    vs_market_median_eur_minor: int | None
    market_median_eur_minor: int | None


class RecommendationItem(_Model):
    rank: int
    offer_id: str
    platform_id: str
    seller_id: str
    unit_price_eur_minor: int
    seller_confidence_band: str
    seller_confidence_score: int | None
    score: str
    contributions: dict[str, str]
    savings: Savings
    excluded_reason: str | None


class Recommendation(_Model):
    mission_id: str
    profile: str
    config_version: str
    items: list[RecommendationItem]
    narrative: str
    trade_offs: list[str]
    generated_at: datetime


class NarrativeUngrounded(Exception):
    """The narrator used a number that is not in the ranking. A loud failure, never a silent rewrite."""

    def __init__(self, numbers: set[str]) -> None:
        super().__init__(f"narrative contains numbers absent from the ranking: {sorted(numbers)}")
        self.numbers = numbers


@dataclass(frozen=True)
class EvaluatorDeps:
    gateway: LLMGateway
    prompts: PromptRegistry
    mcda: McdaPort
    clock: Clock


class EvaluatorAgent:
    def __init__(self, deps: EvaluatorDeps) -> None:
        self._deps = deps

    async def recommend(
        self,
        *,
        tenant_id: str,
        mission_id: str,
        profile: str,
        config_version: str,
        offers: Sequence[tuple[Offer, OfferAnalysis]],
        language: str,
    ) -> Recommendation:
        candidates = [_candidate(offer, analysis) for offer, analysis in offers]
        if not candidates:
            raise NoCandidates(mission_id)
        ranking = await self._deps.mcda.rank(
            candidates, profile=profile, tenant_id=tenant_id, config_version=config_version
        )
        by_id = {c.offer_id: c for c in candidates}
        median = _median([c.unit_price_eur_minor for c in candidates])
        items = [
            _item(ranked, by_id[ranked.offer_id], median)
            for ranked in sorted(ranking.ranked, key=lambda r: r.rank)
            if ranked.offer_id in by_id
        ]
        narrative, trade_offs = await self._narrate(
            tenant_id=tenant_id,
            mission_id=mission_id,
            language=language,
            items=items,
        )
        return Recommendation(
            mission_id=mission_id,
            profile=profile,
            config_version=config_version,
            items=items,
            narrative=narrative,
            trade_offs=trade_offs,
            generated_at=self._deps.clock.now(),
        )

    async def _narrate(
        self, *, tenant_id: str, mission_id: str, language: str, items: list[RecommendationItem]
    ) -> tuple[str, list[str]]:
        ranking_json = json.dumps(
            [
                {
                    "rank": i.rank,
                    "offer_id": i.offer_id,
                    "unit_price_eur_minor": i.unit_price_eur_minor,
                    "seller_confidence_band": i.seller_confidence_band,
                    "seller_confidence_score": i.seller_confidence_score,
                    "score": i.score,
                }
                for i in items
            ],
            ensure_ascii=False,
        )
        rendered = self._deps.prompts.render(
            "narrator_recommendation", language=language, ranking_json=ranking_json
        )
        draft = await self._deps.gateway.chat_structured(
            LLMRole.NARRATOR,
            rendered.messages,
            RecommendationNarrative,
            mission_id=mission_id,
            tenant_id=tenant_id,
            prompt_version=rendered.prompt_version,
        )
        _require_grounded(draft.narrative, ranking_json)
        for text in draft.trade_offs:
            _require_grounded(text, ranking_json)
        return draft.narrative, list(draft.trade_offs)


class NoCandidates(Exception):
    def __init__(self, mission_id: str) -> None:
        super().__init__(f"mission {mission_id} has no offers to rank")
        self.mission_id = mission_id


def _candidate(offer: Offer, analysis: OfferAnalysis) -> Candidate:
    return Candidate(
        offer_id=offer.id,
        platform_id=offer.platform_id,
        seller_id=offer.seller_id,
        unit_price_eur_minor=offer.unit_price_eur_minor,
        list_price_eur_minor=offer.list_price_eur_minor,
        quantity=offer.quantity,
        seller_confidence_score=analysis.confidence.score,
        seller_confidence_band=analysis.confidence.band.value,
        price_band=analysis.sanity.band.value,
        financial_verdict=analysis.fit.verdict,
    )


def _item(ranked: RankedCandidate, candidate: Candidate, median: int | None) -> RecommendationItem:
    return RecommendationItem(
        rank=ranked.rank,
        offer_id=candidate.offer_id,
        platform_id=candidate.platform_id,
        seller_id=candidate.seller_id,
        unit_price_eur_minor=candidate.unit_price_eur_minor,
        seller_confidence_band=candidate.seller_confidence_band,
        seller_confidence_score=candidate.seller_confidence_score,
        score=ranked.score,
        contributions=dict(ranked.contributions),
        savings=Savings(
            vs_list_price_eur_minor=(
                candidate.list_price_eur_minor - candidate.unit_price_eur_minor
                if candidate.list_price_eur_minor is not None
                else None
            ),
            vs_market_median_eur_minor=(
                median - candidate.unit_price_eur_minor if median is not None else None
            ),
            market_median_eur_minor=median,
        ),
        excluded_reason=ranked.excluded_reason,
    )


def _median(values: list[int]) -> int | None:
    """Integer median of integer values. Even counts take the lower middle value: exact, no rounding."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def _require_grounded(text: str, source: str) -> None:
    """Every number in the prose must appear in the ranking it was given."""
    invented = _numbers(text) - _numbers(source)
    if invented:
        raise NarrativeUngrounded(invented)


__all__ = [
    "Candidate",
    "EvaluatorAgent",
    "EvaluatorDeps",
    "McdaPort",
    "NarrativeUngrounded",
    "NoCandidates",
    "RankedCandidate",
    "RankedRecommendation",
    "Recommendation",
    "RecommendationItem",
    "Savings",
]
