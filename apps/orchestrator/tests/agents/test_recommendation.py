"""EvaluatorAgent (D4-12): DEV-3's MCDA ranks with the tenant's profile, the LLM only narrates.

Invariants: an out_of_budget offer is never #1 (criterion 15), a low seller is never #1 (criterion 11), and a
profile switch reorders deterministically (criterion 27). Narration failure never loses the numbers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from apex.agents.offers import InMemoryOfferStore, Offer, OfferAnalysis
from apex.agents.ports import ConfidenceBand, FitOutcome, PriceBand, SanityOutcome, TrustOutcome
from apex.agents.recommendation import EvaluatorAgent, UnknownProfile
from apex.agents.schemas import RecommendationNarrative
from apex.common.clock import FixedClock
from apex.llm.prompts import PromptRegistry
from apex.tenant_config.load_defaults import seed
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.service import TenantConfigService

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
MISSION = "m-1"


class _Missions:
    async def get(self, tenant_id: str, mission_id: str) -> Any:
        return object() if mission_id == MISSION else None


class _Gateway:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls = 0

    async def chat_structured(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


async def _agent(rows: list[tuple[Offer, OfferAnalysis]], narrative: Any = None) -> EvaluatorAgent:
    store = InMemoryOfferStore()
    for offer, analysis in rows:
        await store.add(offer)
        await store.set_analysis(TENANT, analysis)
    repo = InMemoryConfigRepository()
    await seed([TENANT], repo, demo_values=True)
    config = TenantConfigService(repo, None, FixedClock(NOW))  # type: ignore[arg-type]
    gateway = _Gateway(
        narrative
        or RecommendationNarrative(top_offer_id="x", narrative="The top offer.", trade_offs=[])
    )
    return EvaluatorAgent(
        offers=store,
        missions=_Missions(),  # type: ignore[arg-type]
        config=config,
        gateway=gateway,  # type: ignore[arg-type]
        prompts=PromptRegistry(),
        clock=FixedClock(NOW),
    )


def _row(
    offer_id: str,
    price: int,
    *,
    band: ConfidenceBand = ConfidenceBand.HIGH,
    score: int = 80,
    verdict: str = "within_budget",
    price_band: PriceBand = PriceBand.NORMAL,
) -> tuple[Offer, OfferAnalysis]:
    offer = Offer(
        id=f"mock-a:{offer_id}",
        tenant_id=TENANT,
        mission_id=MISSION,
        platform_id="mock-a",
        seller_id=f"s-{offer_id}",
        product_id="p-1",
        unit_price_eur_minor=price,
        list_price_eur_minor=price + 500,
        currency="EUR",
        quantity=100,
        collected_at=NOW,
    )
    analysis = OfferAnalysis(
        offer_id=offer.id,
        confidence=TrustOutcome(band=band, score=score, model_version="trust-v1"),
        sanity=SanityOutcome(band=price_band, config_version="c1"),
        fit=FitOutcome(verdict=verdict),  # type: ignore[arg-type]
        analysed_at=NOW,
    )
    return offer, analysis


async def _rank(agent: EvaluatorAgent, profile: str = "founder") -> list[str]:
    rec = await agent.recommendation(tenant_id=TENANT, mission_id=MISSION, profile_id=profile)
    return [r.offer_id for r in rec.ranking]


async def test_out_of_budget_is_never_first() -> None:
    agent = await _agent(
        [_row("cheap", 100, verdict="out_of_budget", score=99), _row("ok", 900, score=60)]
    )
    rec = await agent.recommendation(tenant_id=TENANT, mission_id=MISSION, profile_id="founder")
    assert [r.offer_id for r in rec.ranking] == ["mock-a:ok"]
    assert rec.excluded[0].offer_id == "mock-a:cheap"


async def test_low_seller_is_never_first() -> None:
    agent = await _agent(
        [_row("cheap", 100, band=ConfidenceBand.LOW, score=30), _row("ok", 900, score=60)]
    )
    assert await _rank(agent) == ["mock-a:ok"]


async def test_out_of_range_price_is_excluded_with_a_reason() -> None:
    agent = await _agent([_row("weird", 10, price_band=PriceBand.ATYPICAL), _row("ok", 900)])
    rec = await agent.recommendation(tenant_id=TENANT, mission_id=MISSION, profile_id="founder")
    assert [r.offer_id for r in rec.ranking] == ["mock-a:ok"]
    assert rec.excluded[0].reasons == ["price band atypical"]


async def test_a_profile_switch_reorders_deterministically() -> None:
    # cheap: low price, stretch budget. safe: dearer, within budget. founder weighs landed cost, cfo weighs fit.
    rows = [
        _row("cheap", 100, verdict="stretch", score=70),
        _row("safe", 400, verdict="within_budget", score=70),
    ]
    agent = await _agent(rows)
    assert await _rank(agent, "founder") == ["mock-a:cheap", "mock-a:safe"]
    assert await _rank(agent, "cfo") == ["mock-a:safe", "mock-a:cheap"]
    assert await _rank(agent, "founder") == ["mock-a:cheap", "mock-a:safe"]


async def test_narrative_is_attached_to_the_top_offer_only() -> None:
    agent = await _agent([_row("a", 100), _row("b", 400)])
    rec = await agent.recommendation(tenant_id=TENANT, mission_id=MISSION, profile_id="founder")
    assert rec.ranking[0].narrative == "The top offer."
    assert rec.ranking[1].narrative is None
    assert rec.alternatives and rec.alternatives[0].versus_offer_id == rec.ranking[0].offer_id
    assert rec.savings.vs_list_price.root is not None


@pytest.mark.parametrize(
    "narrative",
    [
        RuntimeError("llm down"),
        RecommendationNarrative(top_offer_id="x", narrative="Costs 12345 EUR.", trade_offs=[]),
    ],
)
async def test_narration_failure_keeps_the_numbers(narrative: Any) -> None:
    agent = await _agent([_row("a", 100), _row("b", 400)], narrative)
    rec = await agent.recommendation(tenant_id=TENANT, mission_id=MISSION, profile_id="founder")
    assert [r.narrative for r in rec.ranking] == [None, None]
    assert len(rec.ranking) == 2


async def test_unknown_mission_and_profile_are_lookup_errors() -> None:
    agent = await _agent([_row("a", 100)])
    with pytest.raises(LookupError):
        await agent.recommendation(tenant_id=TENANT, mission_id="nope", profile_id="founder")
    with pytest.raises(UnknownProfile):
        await agent.recommendation(tenant_id=TENANT, mission_id=MISSION, profile_id="nope")
