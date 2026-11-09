"""Mission runner (D4-09 → D4-10 → D4-11): the straight line from a plan to the human queue."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from apex.agents.analysis import AnalysisDeps, AnalysisNodes
from apex.agents.gate import GateAgent, GateDeps, GateRules, InMemoryGateStore
from apex.agents.mission_runner import (
    MissionNotRunnable,
    MissionRunner,
    MissionRunnerDeps,
)
from apex.agents.missions import (
    InMemoryMissionStore,
    Mission,
    MissionEventBus,
    MissionEventType,
    MissionStatus,
)
from apex.agents.offers import InMemoryOfferStore, InMemorySellerConfidenceStore
from apex.agents.ports import (
    ConfidenceBand,
    DecisionRef,
    FitOutcome,
    PriceBand,
    SanityOutcome,
    TrustOutcome,
)
from apex.agents.scraping import RawOffer, ScrapingDeps, ScrapingService, WorkerSearchResult
from apex.agents.sourcing import PlanStep, SourcingPlan
from apex.common.clock import FixedClock

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
RULES = GateRules(sla_hours=24, max_renegotiations=1, stretch_gate_threshold_eur_minor=500_000)


class _Worker:
    def __init__(self, offers: list[RawOffer] | Exception) -> None:
        self.offers = offers
        self.calls: list[dict[str, Any]] = []

    async def search(
        self, *, tenant_id: str, mission_id: str, step: PlanStep, quantity: int
    ) -> WorkerSearchResult:
        self.calls.append({"platform": step.platform_id, "quantity": quantity})
        if isinstance(self.offers, Exception):
            raise self.offers
        return WorkerSearchResult(platform_id=step.platform_id, offers=list(self.offers))


class _Fx:
    async def to_eur_unit(
        self, *, amount_minor: int, currency: str, tenant_id: str
    ) -> tuple[int, bool]:
        return amount_minor, False


class _Trust:
    def __init__(self, band: ConfidenceBand = ConfidenceBand.HIGH) -> None:
        self.band = band

    async def score(self, offer: Any, *, tenant_id: str) -> TrustOutcome:
        return TrustOutcome(band=self.band, score=80, model_version="trust-v3")


class _Sanity:
    def __init__(self, band: PriceBand = PriceBand.NORMAL) -> None:
        self.band = band

    async def check(self, offer: Any, *, tenant_id: str, price_minor: int | None) -> SanityOutcome:
        return SanityOutcome(band=self.band, config_version="cfg-7")


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


def _raw(**overrides: Any) -> RawOffer:
    base: dict[str, Any] = {
        "platform_id": "mock-a",
        "platform_offer_id": "a-1",
        "seller_id": "s-1",
        "product_id": "p-1",
        "unit_price_minor": 445,
        "currency": "EUR",
        "quantity_available": 500,
        "raw_signals": {"rating": 4.8},
    }
    return RawOffer(**{**base, **overrides})


def _plan() -> SourcingPlan:
    return SourcingPlan(
        steps=[PlanStep(platform_id="mock-a", transport="http", query="gloves")],
        rationale="test",
        config_version="cfg-7",
    )


def _mission(**overrides: Any) -> Mission:
    base: dict[str, Any] = {
        "id": "m-1",
        "tenant_id": TENANT,
        "sourcing_request_id": "sr-1",
        "quantity": 500,
        "status": MissionStatus.PLANNED,
        "config_version": "cfg-7",
        "created_at": NOW,
        "updated_at": NOW,
        "plan": _plan(),
    }
    return Mission(**{**base, **overrides})


def _runner(
    *,
    worker: _Worker | None = None,
    trust: ConfidenceBand = ConfidenceBand.HIGH,
    sanity: PriceBand = PriceBand.NORMAL,
) -> tuple[
    MissionRunner, InMemoryMissionStore, InMemoryOfferStore, InMemoryGateStore, MissionEventBus
]:
    clock = FixedClock(NOW)
    offer_store = InMemoryOfferStore()
    gate_store = InMemoryGateStore()
    bus = MissionEventBus()
    mission_store = InMemoryMissionStore()
    worker = worker or _Worker([_raw()])
    runner = MissionRunner(
        MissionRunnerDeps(
            scraping=ScrapingService(
                ScrapingDeps(worker=worker, fx=_Fx(), offers=offer_store, bus=bus, clock=clock)
            ),
            nodes=AnalysisNodes(
                AnalysisDeps(
                    trust=_Trust(trust),
                    sanity=_Sanity(sanity),
                    finance=_Finance(),
                    offers=offer_store,
                    confidence=InMemorySellerConfidenceStore(),
                    audit=_Audit(),
                    config=_Config(),
                    clock=clock,
                )
            ),
            gate=GateAgent(
                GateDeps(store=gate_store, decisions=_Decisions(), clock=clock, ids=_Ids())
            ),
            store=mission_store,
            bus=bus,
            clock=clock,
            rules_for=lambda tenant_id: RULES,
        )
    )
    return runner, mission_store, offer_store, gate_store, bus


async def _seed(store: InMemoryMissionStore, mission: Mission | None = None) -> Mission:
    return await store.create(mission or _mission())


# ----- the happy path ----------------------------------------------------------------------------


async def test_a_planned_mission_is_scraped_analysed_and_queued() -> None:
    runner, store, offers, gate, _ = _runner()
    await _seed(store)
    result = await runner.run(tenant_id=TENANT, mission_id="m-1")
    assert result.mission.status is MissionStatus.RUNNING
    assert result.offers_collected == 1 and result.offers_analysed == 1
    assert len(await offers.list_for_mission(TENANT, "m-1")) == 1
    assert result.gate_items == 0, "a clean offer needs no human"
    assert await gate.list_open(TENANT) == []


async def test_a_risky_offer_lands_in_the_gate_queue() -> None:
    runner, store, _, gate, _ = _runner(sanity=PriceBand.ATYPICAL)
    await _seed(store)
    result = await runner.run(tenant_id=TENANT, mission_id="m-1")
    assert result.gate_items == 1
    items = await gate.list_open(TENANT)
    assert items[0].causes[0].value == "price_atypical"
    assert items[0].offer_id == "mock-a:a-1"


async def test_a_low_confidence_seller_lands_in_the_gate_queue() -> None:
    runner, store, _, gate, _ = _runner(trust=ConfidenceBand.LOW)
    await _seed(store)
    result = await runner.run(tenant_id=TENANT, mission_id="m-1")
    assert result.gate_items == 1
    assert (await gate.list_open(TENANT))[0].causes[0].value == "seller_low"


async def test_the_mission_quantity_is_what_the_worker_is_asked_for() -> None:
    worker = _Worker([_raw()])
    runner, store, _, _, _ = _runner(worker=worker)
    await _seed(store)
    await runner.run(tenant_id=TENANT, mission_id="m-1")
    assert worker.calls == [{"platform": "mock-a", "quantity": 500}]


async def test_the_mission_emits_one_named_event_per_step() -> None:
    runner, store, _, _, _ = _runner()
    await _seed(store)
    result = await runner.run(tenant_id=TENANT, mission_id="m-1")
    assert [e.type for e in result.mission.events] == [
        MissionEventType.SOURCING_STARTED,
        MissionEventType.OFFERS_COLLECTED,
        MissionEventType.ANALYSIS_COMPLETED,
    ]
    assert result.mission.events[0].payload["platforms"] == ["mock-a"]
    assert result.mission.events[1].payload["offers_kept"] == 1
    assert result.mission.events[2].payload["gate_items"] == 0


async def test_the_mission_stays_running_because_the_deals_await_humans() -> None:
    runner, store, _, _, _ = _runner(sanity=PriceBand.ATYPICAL)
    await _seed(store)
    result = await runner.run(tenant_id=TENANT, mission_id="m-1")
    assert result.mission.status is MissionStatus.RUNNING
    assert MissionStatus.COMPLETED not in [
        MissionStatus(e.payload.get("stage", "x"))
        for e in result.mission.events
        if e.payload.get("stage") in {s.value for s in MissionStatus}
    ]


# ----- refusals and failures ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [MissionStatus.QUEUED, MissionStatus.RUNNING, MissionStatus.COMPLETED, MissionStatus.FAILED],
)
async def test_only_a_planned_mission_can_be_run(status: MissionStatus) -> None:
    runner, store, _, _, _ = _runner()
    await _seed(store, _mission(status=status))
    with pytest.raises(MissionNotRunnable):
        await runner.run(tenant_id=TENANT, mission_id="m-1")


async def test_an_unknown_mission_is_a_lookup_error() -> None:
    runner, _, _, _, _ = _runner()
    with pytest.raises(LookupError):
        await runner.run(tenant_id=TENANT, mission_id="nope")


async def test_an_unwired_port_fails_the_mission_with_the_owner_named() -> None:
    """The browser worker is D5-01: the mission must fail loudly, not hang forever."""
    runner, store, _, _, _ = _runner(
        worker=_Worker(NotImplementedError("browser worker is not wired yet (owner: DEV-5, D5-01)"))
    )
    await _seed(store)
    result = await runner.run(tenant_id=TENANT, mission_id="m-1")
    assert result.mission.status is MissionStatus.FAILED
    assert result.failed_reason is not None
    assert "D5-01" in result.failed_reason
    assert result.mission.events[-1].type is MissionEventType.MISSION_FAILED


async def test_a_failed_mission_keeps_its_reason_for_the_ui() -> None:
    runner, store, _, _, _ = _runner(worker=_Worker(NotImplementedError("owner: DEV-5, D5-01")))
    await _seed(store)
    await runner.run(tenant_id=TENANT, mission_id="m-1")
    stored = await store.get(TENANT, "m-1")
    assert stored is not None and stored.failure_reason is not None
    assert "D5-01" in stored.failure_reason
