"""The DEV-4 metrics are emitted with the names and closed labels the catalogue requires.

``docs/observability/metrics.md`` is the contract the Grafana dashboards query, so this test reads the
instruments through an in-memory reader and checks names, types and label values.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from apex.agents.analysis import AnalysisDeps, AnalysisNodes
from apex.agents.gate import GateAgent, GateDeps, GateRules, InMemoryGateStore
from apex.agents.offers import (
    InMemoryOfferStore,
    InMemorySellerConfidenceStore,
    Offer,
)
from apex.agents.ports import (
    ConfidenceBand,
    DecisionRef,
    FitOutcome,
    PriceBand,
    SanityOutcome,
    TrustOutcome,
)
from apex.common import metrics as metrics_module
from apex.common.clock import FixedClock
from apex.common.metrics import GATE_CAUSES, closed

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
RULES = GateRules(sla_hours=24, max_renegotiations=1, stretch_gate_threshold_eur_minor=500_000)


@pytest.fixture
def reader(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemoryMetricReader]:
    """Build the instruments on a private meter provider and inject them for the duration of the test.

    ``tests/conftest.py`` sets ``OTEL_SDK_DISABLED=true`` for the whole session to keep the other tests
    quiet; the SDK honours it by turning every provider into a no-op, so it has to be lifted here.
    """
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics_module.set_metrics_for_tests(metrics_module.Metrics(provider.get_meter("apex-test")))
    try:
        yield reader
    finally:
        metrics_module.reset_metrics_for_tests()
        provider.shutdown()


def _points(reader: InMemoryMetricReader) -> dict[str, list[Any]]:
    data = reader.get_metrics_data()
    out: dict[str, list[Any]] = {}
    if data is None:
        return out
    for resource_metrics in data.resource_metrics:
        for scope in resource_metrics.scope_metrics:
            for metric in scope.metrics:
                out.setdefault(metric.name, []).extend(list(metric.data.data_points))
    return out


# ----- label hygiene ------------------------------------------------------------------------------


def test_a_value_outside_its_closed_set_becomes_other() -> None:
    assert closed("high", frozenset({"high", "low"})) == "high"
    assert closed("something_new", frozenset({"high", "low"})) == "other"


def test_the_gate_cause_set_matches_the_specification() -> None:
    """The catalogue says the label is the closed set of causes from spec §3.8."""
    assert {
        "price_atypical",
        "price_insufficient_reference",
        "seller_low",
        "seller_insufficient_data",
        "out_of_budget",
        "stretch_above_threshold",
        "negotiator_escalated",
        "financials_stale",
        "fx_provisional",
        "dual_control_pending",
    } == GATE_CAUSES


# ----- price sanity and seller confidence (D4-10) --------------------------------------------------


class _Trust:
    def __init__(
        self, band: ConfidenceBand = ConfidenceBand.HIGH, flags: tuple[str, ...] = ()
    ) -> None:
        self.band, self.flags = band, flags

    async def score(self, offer: Any, *, tenant_id: str) -> TrustOutcome:
        outcome = TrustOutcome(band=self.band, score=81, model_version="trust-v3")
        object.__setattr__(outcome, "flags", self.flags)
        return outcome


class _Sanity:
    def __init__(self, band: PriceBand = PriceBand.NORMAL, deviation: float | None = 0.25) -> None:
        self.band, self.deviation = band, deviation

    async def check(self, offer: Any, *, tenant_id: str, price_minor: int | None) -> SanityOutcome:
        outcome = SanityOutcome(band=self.band, config_version="cfg-7")
        object.__setattr__(outcome, "relative_deviation", self.deviation)
        return outcome


class _Finance:
    async def fit(self, offer: Any, *, tenant_id: str) -> FitOutcome:
        return FitOutcome(verdict="within_budget")


class _Audit:
    async def append(self, event: Any, *, tenant_id: str) -> None:
        return None


class _Config:
    def config_version(self, tenant_id: str) -> str:
        return "cfg-7"

    def seller_snapshot_max_age_days(self, tenant_id: str) -> int:
        return 30


def _offer() -> Offer:
    return Offer(
        id="o-1",
        tenant_id=TENANT,
        mission_id="m-1",
        platform_id="mock-a",
        seller_id="s-1",
        product_id="p-1",
        unit_price_eur_minor=412,
        currency="EUR",
        quantity=100,
        collected_at=NOW,
        raw_signals={"rating": 4.8},
    )


def _nodes(trust: _Trust | None = None, sanity: _Sanity | None = None) -> AnalysisNodes:
    return AnalysisNodes(
        AnalysisDeps(
            trust=trust or _Trust(),
            sanity=sanity or _Sanity(),
            finance=_Finance(),
            offers=InMemoryOfferStore(),
            confidence=InMemorySellerConfidenceStore(),
            audit=_Audit(),
            config=_Config(),
            clock=FixedClock(NOW),
        )
    )


async def test_price_sanity_metrics_carry_the_band_and_no_amount(
    reader: InMemoryMetricReader,
) -> None:
    nodes = _nodes(sanity=_Sanity(band=PriceBand.ATYPICAL, deviation=0.62))
    await nodes.analyse_offer(tenant_id=TENANT, offer=_offer())
    points = _points(reader)
    checks = points["apex.price_sanity.checks"]
    assert checks[0].value == 1
    assert checks[0].attributes == {"platform": "mock-a", "band": "atypical"}
    deviation = points["apex.price_sanity.relative_deviation"]
    assert deviation[0].sum == pytest.approx(0.62)
    assert deviation[0].attributes == {"platform": "mock-a"}


async def test_seller_confidence_metrics_carry_band_score_and_flags(
    reader: InMemoryMetricReader,
) -> None:
    nodes = _nodes(trust=_Trust(band=ConfidenceBand.LOW, flags=("burst", "five_star_share")))
    await nodes.analyse_offer(tenant_id=TENANT, offer=_offer())
    points = _points(reader)
    assessment = points["apex.seller_confidence.assessments"][0]
    assert assessment.attributes == {"platform": "mock-a", "band": "low"}
    score = points["apex.seller_confidence.score"][0]
    assert score.sum == 81 and score.attributes == {"platform": "mock-a"}
    flags = {p.attributes["flag"] for p in points["apex.seller_confidence.manipulation_flags"]}
    assert flags == {"burst", "five_star_share"}


async def test_an_unknown_manipulation_flag_becomes_other(reader: InMemoryMetricReader) -> None:
    nodes = _nodes(trust=_Trust(flags=("something_new",)))
    await nodes.analyse_offer(tenant_id=TENANT, offer=_offer())
    flags = {
        p.attributes["flag"] for p in _points(reader)["apex.seller_confidence.manipulation_flags"]
    }
    assert flags == {"other"}


# ----- gate health (D4-11) ------------------------------------------------------------------------


class _Decisions:
    async def create_decision(
        self, type: str, subject_ref: str, payload: Any, *, tenant_id: str
    ) -> DecisionRef:
        return DecisionRef(id="d1", status="pending_signature")

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> Any:
        raise NotImplementedError

    async def sign_service_event(self, service: str, payload: Any, *, tenant_id: str) -> str:
        return "sig"


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> str:
        self.n += 1
        return f"g{self.n}"


def _agent(clock: FixedClock | None = None) -> GateAgent:
    return GateAgent(
        GateDeps(
            store=InMemoryGateStore(),
            decisions=_Decisions(),
            clock=clock or FixedClock(NOW),
            ids=_Ids(),
        )
    )


def _analysis(price: PriceBand = PriceBand.ATYPICAL) -> Any:
    from apex.agents.offers import OfferAnalysis

    return OfferAnalysis(
        offer_id="o-1",
        confidence=TrustOutcome(band=ConfidenceBand.HIGH, score=80, model_version="trust-v3"),
        sanity=SanityOutcome(band=price, config_version="cfg-7"),
        fit=FitOutcome(verdict="within_budget"),
        analysed_at=NOW,
    )


async def test_gate_queue_gauges_cover_every_cause_and_zero_the_empty_ones(
    reader: InMemoryMetricReader,
) -> None:
    agent = _agent()
    await agent.enqueue(tenant_id=TENANT, offer=_offer(), analysis=_analysis(), rules=RULES)
    await agent.list_open(tenant_id=TENANT)
    points = _points(reader)
    depth = {p.attributes["cause"]: p.value for p in points["apex.gate.queue.depth"]}
    assert set(depth) == GATE_CAUSES, "every cause is set, so a drained cause is explicitly zero"
    assert depth["price_atypical"] == 1
    assert depth["seller_low"] == 0
    age = {p.attributes["cause"]: p.value for p in points["apex.gate.oldest_item.age"]}
    assert age["price_atypical"] == 0


async def test_an_item_past_its_sla_counts_as_missed(reader: InMemoryMetricReader) -> None:
    clock = FixedClock(NOW)
    agent = _agent(clock)
    await agent.enqueue(tenant_id=TENANT, offer=_offer(), analysis=_analysis(), rules=RULES)
    clock.advance(timedelta(hours=25))
    await agent.list_open(tenant_id=TENANT)
    points = _points(reader)
    missed = points["apex.gate.sla.missed"][0]
    assert missed.value == 1 and missed.attributes == {"cause": "price_atypical"}
    age = {p.attributes["cause"]: p.value for p in points["apex.gate.oldest_item.age"]}
    assert age["price_atypical"] == 25 * 3600


async def test_resolving_an_item_counts_it_by_cause_and_action(
    reader: InMemoryMetricReader,
) -> None:
    agent = _agent()
    item = await agent.enqueue(tenant_id=TENANT, offer=_offer(), analysis=_analysis(), rules=RULES)
    assert item is not None
    await agent.decide_queue_action(
        tenant_id=TENANT,
        item_id=item.id,
        action=__import__("apex.agents.gate", fromlist=["QueueAction"]).QueueAction.UNBLOCK,
    )
    resolved = _points(reader)["apex.gate.items.resolved"][0]
    assert resolved.value == 1
    assert resolved.attributes == {"cause": "price_atypical", "action": "unblock"}


# ----- LLM health (D4-04) -------------------------------------------------------------------------


async def test_llm_metrics_come_from_the_gateway(reader: InMemoryMetricReader) -> None:
    import httpx

    from apex.llm.accounting import InMemorySink
    from apex.llm.budget import InMemoryBudgetStore, TokenBudget
    from apex.llm.config import LLMRole
    from apex.llm.gateway import LLMGateway
    from tests.llm.fakes import chat_body, endpoint_cfg, provider, roles_config, secrets

    cfg = endpoint_cfg(model="stub-model")
    gateway = LLMGateway(
        config_provider=provider(roles_config(cfg, role=LLMRole.PLANNER)),
        secrets=secrets(),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=1_000_000),
        sink=InMemorySink(),
        clock=FixedClock(NOW),
        http_client_factory=lambda _cfg: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=chat_body("{}")))
        ),
    )
    await gateway.chat(
        LLMRole.PLANNER,
        [{"role": "user", "content": "hi"}],
        mission_id="m-1",
        tenant_id=TENANT,
        prompt_version="planner_sourcing_plan@v1",
    )
    points = _points(reader)
    request = points["apex.llm.requests"][0]
    assert request.attributes == {"role": "planner", "endpoint": "primary", "outcome": "ok"}
    assert request.value == 1
    tokens = {p.attributes["direction"]: p.value for p in points["apex.llm.tokens"]}
    assert tokens == {"input": 10, "output": 5}
    duration = points["apex.llm.request.duration"][0]
    assert duration.attributes == {"role": "planner", "endpoint": "primary"}


async def test_the_circuit_state_gauge_is_set_per_endpoint(reader: InMemoryMetricReader) -> None:
    """The catalogue wants the breaker state as a gauge: 0 closed, 1 half-open, 2 open."""
    import httpx

    from apex.llm.accounting import InMemorySink
    from apex.llm.budget import InMemoryBudgetStore, TokenBudget
    from apex.llm.config import LLMRole
    from apex.llm.gateway import LLMGateway
    from tests.llm.fakes import chat_body, endpoint_cfg, provider, roles_config, secrets

    cfg = endpoint_cfg(model="stub-model")
    gateway = LLMGateway(
        config_provider=provider(roles_config(cfg, role=LLMRole.PLANNER)),
        secrets=secrets(),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=1_000_000),
        sink=InMemorySink(),
        clock=FixedClock(NOW),
        http_client_factory=lambda _cfg: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=chat_body("{}")))
        ),
    )
    await gateway.chat(
        LLMRole.PLANNER,
        [{"role": "user", "content": "hi"}],
        mission_id="m-1",
        tenant_id=TENANT,
        prompt_version="planner_sourcing_plan@v1",
    )
    states = _points(reader)["apex.llm.circuit.state"]
    assert states[-1].value == 0  # closed after a successful call
    assert states[-1].attributes == {"endpoint": "primary"}


async def test_a_failed_mission_records_its_llm_cost_once(reader: InMemoryMetricReader) -> None:
    """§5 of the catalogue: one observation per mission when it closes, with no labels."""
    from apex.agents.mission_runner import MissionRunner, MissionRunnerDeps
    from apex.agents.missions import InMemoryMissionStore, Mission, MissionEventBus, MissionStatus
    from apex.agents.sourcing import PlanStep, SourcingPlan

    class _Scraping:
        async def scrape(self, **_: Any) -> Any:
            # What an unwired port does: the runner turns this into a failed mission naming the owner.
            raise NotImplementedError("the worker is not wired yet (owner: DEV-5, D5-01)")

    store = InMemoryMissionStore()
    runner = MissionRunner(
        MissionRunnerDeps(
            scraping=_Scraping(),  # type: ignore[arg-type]
            nodes=None,  # type: ignore[arg-type]
            gate=None,  # type: ignore[arg-type]
            store=store,
            bus=MissionEventBus(),
            clock=FixedClock(NOW),
            rules_for=lambda _t: RULES,
            mission_cost_minor=lambda mission_id: 1_250 if mission_id == "m-1" else None,
        )
    )
    plan = SourcingPlan(
        steps=[PlanStep(platform_id="mock-a", transport="http", query="q")],
        rationale="r",
        config_version="v1",
    )
    await store.create(
        Mission(
            id="m-1",
            tenant_id=TENANT,
            sourcing_request_id="sr-1",
            quantity=500,
            status=MissionStatus.PLANNED,
            config_version="v1",
            created_at=NOW,
            updated_at=NOW,
            plan=plan,
        )
    )
    await runner.run(tenant_id=TENANT, mission_id="m-1")
    costs = _points(reader)["apex.mission.llm_cost"]
    assert len(costs) == 1
    assert costs[0].sum == pytest.approx(12.50)  # 1250 minor units -> 12.50
    assert costs[0].attributes == {}  # no mission ids, ever
