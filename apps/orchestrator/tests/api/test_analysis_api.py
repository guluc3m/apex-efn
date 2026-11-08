"""HTTP surface for D4-10: seller confidence (with history), audited recompute, mission offers."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.agents.analysis import AnalysisDeps, AnalysisNodes
from apex.agents.missions import InMemoryMissionStore, Mission, MissionEventBus, MissionStatus
from apex.agents.offers import InMemoryOfferStore, InMemorySellerConfidenceStore, Offer
from apex.agents.ports import ConfidenceBand, FitOutcome, PriceBand, SanityOutcome, TrustOutcome
from apex.api import missions as missions_api
from apex.api import sellers as sellers_api
from apex.common.clock import FixedClock
from apex.common.errors import install_problem_handlers
from apex.llm.prompts import PromptRegistry

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"


class _Trust:
    async def score(self, offer: Any, *, tenant_id: str) -> TrustOutcome:
        return TrustOutcome(band=ConfidenceBand.MEDIUM, score=61, model_version="trust-v3")


class _Sanity:
    async def check(self, offer: Any, *, tenant_id: str, price_minor: int | None) -> SanityOutcome:
        return SanityOutcome(band=PriceBand.NORMAL, config_version="cfg-7")


class _Finance:
    async def fit(self, offer: Any, *, tenant_id: str) -> FitOutcome:
        return FitOutcome(verdict="stretch")


class _Audit:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def append(self, event: Any, *, tenant_id: str) -> None:
        self.events.append(event)


class _Config:
    def config_version(self, tenant_id: str) -> str:
        return "cfg-7"

    def seller_snapshot_max_age_days(self, tenant_id: str) -> int:
        return 30


class _MissionService:
    """Stands in for SourcingService: the offers endpoint only needs ``get_mission``."""

    def __init__(self, store: InMemoryMissionStore) -> None:
        self._store = store

    async def get_mission(self, *, tenant_id: str, mission_id: str) -> Mission:
        from apex.agents.sourcing_service import MissionMissing

        mission = await self._store.get(tenant_id, mission_id)
        if mission is None:
            raise MissionMissing(mission_id)
        return mission


@pytest.fixture(autouse=True)
def _tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")


@pytest.fixture
def app() -> Iterator[FastAPI]:
    clock = FixedClock(NOW)
    offer_store = InMemoryOfferStore()
    nodes = AnalysisNodes(
        AnalysisDeps(
            trust=_Trust(),
            sanity=_Sanity(),
            finance=_Finance(),
            offers=offer_store,
            confidence=InMemorySellerConfidenceStore(),
            audit=_Audit(),
            config=_Config(),
            clock=clock,
        )
    )
    mission_store = InMemoryMissionStore()
    application = FastAPI()
    install_problem_handlers(application)
    application.include_router(sellers_api.router, prefix="/sellers")
    application.include_router(missions_api.router, prefix="/missions")
    application.dependency_overrides[sellers_api.get_analysis_nodes] = lambda: nodes
    application.dependency_overrides[missions_api.get_analysis_nodes] = lambda: nodes
    application.dependency_overrides[missions_api.get_sourcing_service] = lambda: _MissionService(
        mission_store
    )
    application.state.mission_event_bus = MissionEventBus()
    application.state.offer_store = offer_store
    application.state.mission_store = mission_store
    yield application


def _h(tenant: str = TENANT) -> dict[str, str]:
    return {"X-Tenant-Id": tenant}


def _offer(**overrides: Any) -> Offer:
    base: dict[str, Any] = {
        "id": "o-1",
        "tenant_id": TENANT,
        "mission_id": "m-1",
        "platform_id": "mock-a",
        "seller_id": "s-1",
        "product_id": "p-1",
        "unit_price_eur_minor": 412,
        "currency": "EUR",
        "quantity": 100,
        "collected_at": NOW,
        "raw_signals": {"age_days": 400, "sales": 120},
    }
    return Offer(**{**base, **overrides})


# ----- sellers -----------------------------------------------------------------------------------


def test_confidence_of_an_unknown_seller_is_an_empty_history(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/sellers/s-unknown/confidence", headers=_h())
    assert response.status_code == 200
    assert response.json() == {
        "seller_id": "s-unknown",
        "tenant_id": TENANT,
        "latest": None,
        "history": [],
    }


def test_recompute_then_read_returns_the_record_and_its_history(app: FastAPI) -> None:
    with TestClient(app) as client:
        recompute = client.post("/sellers/s-1/confidence/recompute", headers=_h())
        assert recompute.status_code == 202
        assert recompute.json()["recomputed"] is True
        assert recompute.json()["latest"]["band"] == "medium"
        assert recompute.json()["latest"]["model_version"] == "trust-v3"

        read = client.get("/sellers/s-1/confidence", headers=_h()).json()
    assert read["latest"]["score"] == 61
    assert len(read["history"]) == 1
    assert read["history"][0]["config_version"] == "cfg-7"


def test_recompute_is_audited(app: FastAPI) -> None:
    nodes = app.dependency_overrides[sellers_api.get_analysis_nodes]()
    with TestClient(app) as client:
        client.post("/sellers/s-1/confidence/recompute", headers=_h())
    audit = nodes._deps.audit  # type: ignore[attr-defined]
    assert [e["event"] for e in audit.events] == ["seller_confidence_recomputed"]


def test_sellers_need_a_tenant(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_ALLOW_TENANT_HEADER", raising=False)
    with TestClient(app) as client:
        assert client.get("/sellers/s-1/confidence", headers=_h()).status_code == 401


# ----- mission offers ----------------------------------------------------------------------------


def _seed_mission(app: FastAPI, *, tenant: str = TENANT) -> None:
    store = app.state.mission_store
    import asyncio

    asyncio.run(
        store.create(
            Mission(
                id="m-1",
                tenant_id=tenant,
                sourcing_request_id="sr-1",
                status=MissionStatus.PLANNED,
                config_version="cfg-7",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    )


def test_mission_offers_lists_offers_with_their_analysis(app: FastAPI) -> None:
    _seed_mission(app)
    import asyncio

    asyncio.run(app.state.offer_store.add(_offer()))
    nodes = app.dependency_overrides[missions_api.get_analysis_nodes]()
    asyncio.run(nodes.analyse_offer(tenant_id=TENANT, offer=_offer()))

    with TestClient(app) as client:
        response = client.get("/missions/m-1/offers", headers=_h())
    assert response.status_code == 200
    offers = response.json()["offers"]
    assert len(offers) == 1
    assert offers[0]["unit_price_eur_minor"] == 412
    assert offers[0]["seller_confidence"]["band"] == "medium"
    assert offers[0]["price_sanity"]["band"] == "normal"
    assert offers[0]["financial_fit"]["verdict"] == "stretch"


def test_mission_offers_shows_an_unanalysed_offer_with_nulls(app: FastAPI) -> None:
    _seed_mission(app)
    import asyncio

    asyncio.run(app.state.offer_store.add(_offer()))
    with TestClient(app) as client:
        offers = client.get("/missions/m-1/offers", headers=_h()).json()["offers"]
    assert offers[0]["seller_confidence"] is None
    assert offers[0]["price_sanity"] is None


def test_mission_offers_404s_for_an_unknown_or_foreign_mission(app: FastAPI) -> None:
    _seed_mission(app)
    with TestClient(app) as client:
        assert client.get("/missions/nope/offers", headers=_h()).status_code == 404
        assert client.get("/missions/m-1/offers", headers=_h("tenant-b")).status_code == 404


# ----- recommendation (D4-12) --------------------------------------------------------------------

from apex.agents.recommendation import (  # noqa: E402
    EvaluatorAgent,
    EvaluatorDeps,
    RankedCandidate,
    RankedRecommendation,
)
from apex.agents.schemas import RecommendationNarrative  # noqa: E402


class _Mcda:
    async def rank(self, candidates, *, profile, tenant_id, config_version):  # type: ignore[no-untyped-def]
        return RankedRecommendation(
            ranked=[
                RankedCandidate(offer_id=c.offer_id, rank=i + 1, score="0.9")
                for i, c in enumerate(sorted(candidates, key=lambda c: c.unit_price_eur_minor))
            ],
            profile=profile,
            config_version=config_version,
        )


class _Narrator:
    def __init__(self, narrative: str) -> None:
        self.narrative = narrative

    async def chat_structured(self, role, messages, schema, **kwargs):  # type: ignore[no-untyped-def]
        return RecommendationNarrative(
            top_offer_id="whatever", narrative=self.narrative, trade_offs=[]
        )


def _evaluator(app: FastAPI, narrative: str = "Offer o-1 ranks first.") -> EvaluatorAgent:
    return EvaluatorAgent(
        EvaluatorDeps(
            gateway=_Narrator(narrative),  # type: ignore[arg-type]
            prompts=PromptRegistry(),
            mcda=_Mcda(),
            clock=FixedClock(NOW),
        )
    )


def test_recommendation_ranks_analysed_offers_and_returns_savings(app: FastAPI) -> None:
    _seed_mission(app)
    import asyncio

    nodes = app.dependency_overrides[missions_api.get_analysis_nodes]()
    for offer in (
        _offer(id="o-2", unit_price_eur_minor=900),
        _offer(id="o-1", unit_price_eur_minor=412),
    ):
        asyncio.run(app.state.offer_store.add(offer))
        asyncio.run(nodes.analyse_offer(tenant_id=TENANT, offer=offer))
    app.dependency_overrides[missions_api.get_evaluator] = lambda: _evaluator(app)

    with TestClient(app) as client:
        response = client.get("/missions/m-1/recommendation", headers=_h())
    assert response.status_code == 200
    body = response.json()
    assert [i["offer_id"] for i in body["items"]] == ["o-1", "o-2"]
    assert body["items"][0]["rank"] == 1
    assert body["items"][0]["savings"]["market_median_eur_minor"] == 412
    assert body["profile"] == "balanced"
    assert body["narrative"] == "Offer o-1 ranks first."


def test_recommendation_409s_when_nothing_is_analysed(app: FastAPI) -> None:
    _seed_mission(app)
    app.dependency_overrides[missions_api.get_evaluator] = lambda: _evaluator(app)
    with TestClient(app) as client:
        response = client.get("/missions/m-1/recommendation", headers=_h())
    assert response.status_code == 409
    assert response.json()["reason"] == "no_analysed_offers"


def test_recommendation_502s_when_the_narrative_invents_a_number(app: FastAPI) -> None:
    _seed_mission(app)
    import asyncio

    nodes = app.dependency_overrides[missions_api.get_analysis_nodes]()
    asyncio.run(app.state.offer_store.add(_offer()))
    asyncio.run(nodes.analyse_offer(tenant_id=TENANT, offer=_offer()))
    app.dependency_overrides[missions_api.get_evaluator] = lambda: _evaluator(
        app, "Offer o-1 costs 999."
    )
    with TestClient(app) as client:
        response = client.get("/missions/m-1/recommendation", headers=_h())
    assert response.status_code == 502
    assert response.json()["reason"] == "narrative_ungrounded"


def test_recommendation_404s_for_a_foreign_mission(app: FastAPI) -> None:
    _seed_mission(app)
    app.dependency_overrides[missions_api.get_evaluator] = lambda: _evaluator(app)
    with TestClient(app) as client:
        assert client.get("/missions/m-1/recommendation", headers=_h("tenant-b")).status_code == 404
