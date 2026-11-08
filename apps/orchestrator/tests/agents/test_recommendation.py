"""EvaluatorAgent (D4-12): the MCDA engine ranks, code computes savings, the LLM only narrates."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from apex.agents.offers import Offer, OfferAnalysis
from apex.agents.ports import ConfidenceBand, FitOutcome, PriceBand, SanityOutcome, TrustOutcome
from apex.agents.recommendation import (
    Candidate,
    EvaluatorAgent,
    EvaluatorDeps,
    NarrativeUngrounded,
    NoCandidates,
    RankedCandidate,
    RankedRecommendation,
)
from apex.agents.schemas import RecommendationNarrative
from apex.common.clock import FixedClock
from apex.llm.config import LLMRole
from apex.llm.prompts import PromptRegistry

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"


class _Mcda:
    """Deterministic fake: ranks by unit price ascending and records what it was given."""

    def __init__(self, order: list[str] | None = None) -> None:
        self.order = order
        self.calls: list[dict[str, Any]] = []

    async def rank(
        self,
        candidates: list[Candidate],
        *,
        profile: str,
        tenant_id: str,
        config_version: str,
    ) -> RankedRecommendation:
        self.calls.append(
            {"candidates": list(candidates), "profile": profile, "config_version": config_version}
        )
        ids = self.order or [
            c.offer_id for c in sorted(candidates, key=lambda c: c.unit_price_eur_minor)
        ]
        return RankedRecommendation(
            ranked=[
                RankedCandidate(
                    offer_id=offer_id,
                    rank=index + 1,
                    score=f"0.{90 - index * 10}",
                    contributions={"price": "0.5", "confidence": "0.3", "fit": "0.2"},
                )
                for index, offer_id in enumerate(ids)
            ],
            profile=profile,
            config_version=config_version,
        )


class _Gateway:
    def __init__(self, draft: Any) -> None:
        self.draft = draft
        self.calls: list[dict[str, Any]] = []

    async def chat_structured(
        self,
        role: LLMRole,
        messages: list[dict[str, Any]],
        schema: type[Any],
        *,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        **_: Any,
    ) -> Any:
        self.calls.append(
            {
                "role": role,
                "schema": schema.__name__,
                "messages": messages,
                "prompt_version": prompt_version,
            }
        )
        return self.draft


def _offer(offer_id: str, price: int, *, list_price: int | None = None) -> Offer:
    return Offer(
        id=offer_id,
        tenant_id=TENANT,
        mission_id="m-1",
        platform_id="mock-a",
        seller_id=f"s-{offer_id}",
        product_id="p-1",
        unit_price_eur_minor=price,
        list_price_eur_minor=list_price,
        currency="EUR",
        quantity=100,
        collected_at=NOW,
        raw_signals={},
    )


def _analysis(offer_id: str, band: ConfidenceBand = ConfidenceBand.HIGH) -> OfferAnalysis:
    return OfferAnalysis(
        offer_id=offer_id,
        confidence=TrustOutcome(band=band, score=80, model_version="trust-v3"),
        sanity=SanityOutcome(band=PriceBand.NORMAL, config_version="cfg-7"),
        fit=FitOutcome(verdict="within_budget"),
        analysed_at=NOW,
    )


def _agent(draft: Any = None, mcda: Any = None) -> tuple[EvaluatorAgent, _Gateway, _Mcda]:
    # Default draft carries no numbers, so it is grounded for any price a test happens to use.
    gateway = _Gateway(
        draft
        or RecommendationNarrative(
            top_offer_id="ignored-by-code",
            narrative="Offer o-1 ranks first on price and seller confidence.",
            trade_offs=["o-2 ranks second."],
        )
    )
    engine = mcda or _Mcda()
    return (
        EvaluatorAgent(
            EvaluatorDeps(
                gateway=gateway,  # type: ignore[arg-type]
                prompts=PromptRegistry(),
                mcda=engine,
                clock=FixedClock(NOW),
            )
        ),
        gateway,
        engine,
    )


async def _recommend(
    agent: EvaluatorAgent, offers: list[tuple[Offer, OfferAnalysis]], **kwargs: Any
) -> Any:
    return await agent.recommend(
        tenant_id=TENANT,
        mission_id="m-1",
        profile=kwargs.get("profile", "balanced"),
        config_version="cfg-7",
        offers=offers,
        language=kwargs.get("language", "en"),
    )


# ----- the engine decides the order ---------------------------------------------------------------


async def test_the_engine_order_is_returned_unchanged() -> None:
    agent, _, engine = _agent(mcda=_Mcda(order=["o-2", "o-1"]))
    recommendation = await _recommend(
        agent, [(_offer("o-1", 412), _analysis("o-1")), (_offer("o-2", 900), _analysis("o-2"))]
    )
    assert [i.offer_id for i in recommendation.items] == ["o-2", "o-1"]
    assert [i.rank for i in recommendation.items] == [1, 2]
    assert engine.calls[0]["profile"] == "balanced"


async def test_the_model_top_offer_is_ignored_when_it_disagrees_with_the_engine() -> None:
    agent, _, _ = _agent(
        draft=RecommendationNarrative(
            top_offer_id="o-2",  # the model prefers the second
            narrative="Offer o-1 is cheapest at 412.",
            trade_offs=[],
        ),
        mcda=_Mcda(order=["o-1", "o-2"]),
    )
    recommendation = await _recommend(
        agent, [(_offer("o-1", 412), _analysis("o-1")), (_offer("o-2", 900), _analysis("o-2"))]
    )
    assert recommendation.items[0].offer_id == "o-1"


async def test_candidates_carry_the_analysis_verdicts_not_raw_signals() -> None:
    agent, _, engine = _agent()
    await _recommend(agent, [(_offer("o-1", 412), _analysis("o-1", ConfidenceBand.LOW))])
    candidate = engine.calls[0]["candidates"][0]
    assert candidate.seller_confidence_band == "low"
    assert candidate.price_band == "normal"
    assert candidate.financial_verdict == "within_budget"
    assert not hasattr(candidate, "raw_signals")


# ----- savings are arithmetic ----------------------------------------------------------------------


async def test_savings_against_list_price_and_market_median() -> None:
    agent, _, _ = _agent(mcda=_Mcda(order=["o-1", "o-2", "o-3"]))
    recommendation = await _recommend(
        agent,
        [
            (_offer("o-1", 400, list_price=500), _analysis("o-1")),
            (_offer("o-2", 600), _analysis("o-2")),
            (_offer("o-3", 800), _analysis("o-3")),
        ],
    )
    first = recommendation.items[0]
    assert first.savings.vs_list_price_eur_minor == 100
    assert first.savings.market_median_eur_minor == 600  # lower middle of 400/600/800
    assert first.savings.vs_market_median_eur_minor == 200


async def test_savings_are_null_when_the_reference_does_not_exist() -> None:
    agent, _, _ = _agent()
    recommendation = await _recommend(agent, [(_offer("o-1", 400), _analysis("o-1"))])
    assert recommendation.items[0].savings.vs_list_price_eur_minor is None
    assert recommendation.items[0].savings.vs_market_median_eur_minor == 0


# ----- the narrator -------------------------------------------------------------------------------


async def test_the_narrator_receives_the_ranking_and_its_prompt_version() -> None:
    agent, gateway, _ = _agent()
    await _recommend(agent, [(_offer("o-1", 412), _analysis("o-1"))], language="es")
    call = gateway.calls[0]
    assert call["role"] is LLMRole.NARRATOR
    assert call["schema"] == "RecommendationNarrative"
    assert call["prompt_version"].startswith("narrator_recommendation@v")
    assert "es" in call["messages"][0]["content"]
    body = call["messages"][1]["content"].split("Ranking (JSON, best first):")[1]
    payload, _ = json.JSONDecoder().raw_decode(body.strip())
    assert payload[0]["offer_id"] == "o-1"
    assert payload[0]["seller_confidence_band"] == "high"
    assert payload[0]["unit_price_eur_minor"] == 412


def test_offer_ids_and_scores_do_not_count_as_invented_numbers() -> None:
    from apex.agents.recommendation import _require_grounded

    source = json.dumps([{"offer_id": "o-2", "unit_price_eur_minor": 412, "score": "0.9"}])
    _require_grounded("Offer o-2 costs 412, score 0.9.", source)  # no raise
    with pytest.raises(NarrativeUngrounded):
        _require_grounded("Offer o-2 costs 413.", source)


@pytest.mark.parametrize(
    "narrative",
    [
        "Offer o-1 costs 999 per unit.",  # 999 is not in the ranking
        "That is 12% cheaper.",  # 12 is not in the ranking
        "Confidence 95.",  # 95 is not in the ranking
    ],
)
async def test_a_narrative_that_invents_a_number_is_rejected(narrative: str) -> None:
    agent, _, _ = _agent(
        draft=RecommendationNarrative(top_offer_id="o-1", narrative=narrative, trade_offs=[])
    )
    with pytest.raises(NarrativeUngrounded):
        await _recommend(agent, [(_offer("o-1", 412), _analysis("o-1"))])


async def test_a_trade_off_that_invents_a_number_is_rejected() -> None:
    agent, _, _ = _agent(
        draft=RecommendationNarrative(
            top_offer_id="o-1",
            narrative="Offer o-1 is cheapest at 412.",
            trade_offs=["o-2 costs 777 more."],
        )
    )
    with pytest.raises(NarrativeUngrounded):
        await _recommend(
            agent, [(_offer("o-1", 412), _analysis("o-1")), (_offer("o-2", 500), _analysis("o-2"))]
        )


async def test_a_grounded_narrative_is_returned_as_written() -> None:
    agent, _, _ = _agent(
        draft=RecommendationNarrative(
            top_offer_id="o-1",
            narrative="Offer o-1 is cheapest at 412 minor units per unit.",
            trade_offs=["o-2 costs 500 minor units per unit."],
        )
    )
    recommendation = await _recommend(
        agent, [(_offer("o-1", 412), _analysis("o-1")), (_offer("o-2", 500), _analysis("o-2"))]
    )
    assert "412" in recommendation.narrative
    assert recommendation.trade_offs == ["o-2 costs 500 minor units per unit."]


async def test_no_offers_is_a_loud_error() -> None:
    agent, _, _ = _agent()
    with pytest.raises(NoCandidates):
        await _recommend(agent, [])


async def test_the_recommendation_records_the_profile_and_config_version() -> None:
    agent, _, _ = _agent()
    recommendation = await _recommend(
        agent, [(_offer("o-1", 412), _analysis("o-1"))], profile="cheapest"
    )
    assert recommendation.profile == "cheapest"
    assert recommendation.config_version == "cfg-7"
    assert recommendation.generated_at == NOW
