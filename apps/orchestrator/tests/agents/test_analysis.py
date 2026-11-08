"""Trust, Sanity and Finance nodes (D4-10): thin adapters, freshness, versions, audit."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apex.agents.analysis import AnalysisDeps, AnalysisNodes
from apex.agents.offers import (
    InMemoryOfferStore,
    InMemorySellerConfidenceStore,
    Offer,
    offer_payload,
)
from apex.agents.ports import ConfidenceBand, FitOutcome, PriceBand, SanityOutcome, TrustOutcome
from apex.common.clock import FixedClock

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"


class _Trust:
    def __init__(
        self, band: ConfidenceBand = ConfidenceBand.HIGH, score_value: int | None = 82
    ) -> None:
        self.band, self.score_value = band, score_value
        self.calls: list[Mapping[str, Any]] = []

    async def score(self, offer: Mapping[str, Any], *, tenant_id: str) -> TrustOutcome:
        self.calls.append(offer)
        return TrustOutcome(band=self.band, score=self.score_value, model_version="trust-v3")


class _Sanity:
    def __init__(self, band: PriceBand = PriceBand.NORMAL) -> None:
        self.band = band
        self.calls: list[Any] = []

    async def check(
        self, offer: Mapping[str, Any], *, tenant_id: str, price_minor: int | None
    ) -> SanityOutcome:
        self.calls.append(price_minor)
        return SanityOutcome(band=self.band, config_version="cfg-7")


class _Finance:
    def __init__(self, verdict: str = "within_budget") -> None:
        self.verdict = verdict

    async def fit(self, offer: Mapping[str, Any], *, tenant_id: str) -> FitOutcome:
        return FitOutcome(verdict=self.verdict)  # type: ignore[arg-type]


class _Audit:
    def __init__(self) -> None:
        self.events: list[Mapping[str, Any]] = []

    async def append(self, event: Mapping[str, Any], *, tenant_id: str) -> None:
        self.events.append(event)


class _Config:
    def __init__(self, max_age_days: int = 30, version: str = "cfg-7") -> None:
        self.max_age_days, self.version = max_age_days, version

    def config_version(self, tenant_id: str) -> str:
        return self.version

    def seller_snapshot_max_age_days(self, tenant_id: str) -> int:
        return self.max_age_days


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
        "raw_signals": {"age_days": 400, "sales": 120, "rating": "4.8"},
    }
    return Offer(**{**base, **overrides})


def _nodes(**overrides: Any) -> tuple[AnalysisNodes, dict[str, Any]]:
    clock = overrides.pop("clock", FixedClock(NOW))
    parts: dict[str, Any] = {
        "trust": overrides.pop("trust", _Trust()),
        "sanity": overrides.pop("sanity", _Sanity()),
        "finance": overrides.pop("finance", _Finance()),
        "offers": overrides.pop("offers", InMemoryOfferStore()),
        "confidence": overrides.pop("confidence", InMemorySellerConfidenceStore()),
        "audit": overrides.pop("audit", _Audit()),
        "config": overrides.pop("config", _Config()),
        "clock": clock,
    }
    return AnalysisNodes(AnalysisDeps(**parts)), parts


# ----- per-offer analysis ------------------------------------------------------------------------


async def test_analyse_offer_records_all_three_verdicts_with_their_versions() -> None:
    nodes, parts = _nodes()
    offer = _offer()
    analysis = await nodes.analyse_offer(tenant_id=TENANT, offer=offer)
    assert analysis.confidence.band is ConfidenceBand.HIGH
    assert analysis.confidence.model_version == "trust-v3"
    assert analysis.sanity.config_version == "cfg-7"
    assert analysis.fit.verdict == "within_budget"
    assert analysis.analysed_at == NOW
    stored = await parts["offers"].get_analysis(TENANT, "o-1")
    assert stored == analysis


async def test_the_sanity_engine_receives_the_eur_unit_price() -> None:
    nodes, parts = _nodes()
    await nodes.analyse_offer(tenant_id=TENANT, offer=_offer(unit_price_eur_minor=412))
    assert parts["sanity"].calls == [412]


async def test_the_trust_engine_receives_the_raw_signals_not_a_summary() -> None:
    nodes, parts = _nodes()
    await nodes.analyse_offer(tenant_id=TENANT, offer=_offer())
    payload = parts["trust"].calls[0]
    assert payload["seller_id"] == "s-1"
    assert payload["raw_signals"]["age_days"] == 400


async def test_offer_payload_is_the_single_shape_the_ports_see() -> None:
    payload = offer_payload(_offer())
    assert set(payload) == {
        "offer_id", "tenant_id", "mission_id", "platform_id", "seller_id",
        "product_id", "unit_price_eur_minor", "list_price_eur_minor", "currency", "quantity",
        "raw_signals",
    }  # fmt: skip


# ----- freshness and history ---------------------------------------------------------------------


async def test_a_fresh_snapshot_is_reused_without_calling_the_engine_again() -> None:
    nodes, parts = _nodes()
    first = await nodes.score_seller(tenant_id=TENANT, seller_id="s-1", signals={"a": 1})
    second = await nodes.score_seller(tenant_id=TENANT, seller_id="s-1", signals={"a": 1})
    assert first is second
    assert len(parts["trust"].calls) == 1


async def test_a_stale_snapshot_is_recomputed() -> None:
    clock = FixedClock(NOW)
    nodes, parts = _nodes(clock=clock, config=_Config(max_age_days=30))
    await nodes.score_seller(tenant_id=TENANT, seller_id="s-1", signals={"a": 1})
    clock.advance(timedelta(days=31))
    await nodes.score_seller(tenant_id=TENANT, seller_id="s-1", signals={"a": 1})
    assert len(parts["trust"].calls) == 2


async def test_history_is_append_only_and_keeps_every_version() -> None:
    clock = FixedClock(NOW)
    nodes, parts = _nodes(clock=clock)
    await nodes.score_seller(tenant_id=TENANT, seller_id="s-1", signals={"a": 1})
    clock.advance(timedelta(days=40))
    await nodes.score_seller(tenant_id=TENANT, seller_id="s-1", signals={"a": 1, "b": 2})
    history = await nodes.seller_history(tenant_id=TENANT, seller_id="s-1")
    assert [r.signals_used for r in history] == [1, 2]
    assert all(r.model_version == "trust-v3" for r in history)


async def test_signals_used_counts_present_signals_only() -> None:
    nodes, parts = _nodes()
    record = await nodes.score_seller(
        tenant_id=TENANT, seller_id="s-1", signals={"a": 1, "b": None, "c": 0}
    )
    assert record.signals_used == 2  # None is absent; 0 is present


async def test_a_forced_recompute_always_runs_and_is_audited() -> None:
    nodes, parts = _nodes()
    await nodes.score_seller(tenant_id=TENANT, seller_id="s-1", signals={"a": 1})
    await nodes.score_seller(tenant_id=TENANT, seller_id="s-1", signals={"a": 1}, force=True)
    assert len(parts["trust"].calls) == 2
    assert [e["event"] for e in parts["audit"].events] == ["seller_confidence_recomputed"]
    event = parts["audit"].events[0]
    assert event["seller_id"] == "s-1" and event["model_version"] == "trust-v3"
    assert "raw_signals" not in event


async def test_an_unforced_recompute_writes_no_audit_event() -> None:
    nodes, parts = _nodes()
    await nodes.score_seller(tenant_id=TENANT, seller_id="s-1", signals={"a": 1})
    assert parts["audit"].events == []


# ----- mission level -----------------------------------------------------------------------------


async def test_analyse_mission_is_idempotent_and_ordered_by_price() -> None:
    store = InMemoryOfferStore()
    for offer in (
        _offer(id="o-2", unit_price_eur_minor=900),
        _offer(id="o-1", unit_price_eur_minor=412),
    ):
        await store.add(offer)
    nodes, parts = _nodes(offers=store)
    first = await nodes.analyse_mission(tenant_id=TENANT, mission_id="m-1")
    second = await nodes.analyse_mission(tenant_id=TENANT, mission_id="m-1")
    assert [a.offer_id for a in first] == ["o-1", "o-2"]
    assert [a.offer_id for a in second] == ["o-1", "o-2"]
    assert len(parts["sanity"].calls) == 2  # not re-run for the second pass


async def test_mission_offers_returns_offers_with_or_without_analysis() -> None:
    store = InMemoryOfferStore()
    await store.add(_offer(id="o-1"))
    nodes, _ = _nodes(offers=store)
    pairs = await nodes.mission_offers(tenant_id=TENANT, mission_id="m-1")
    assert len(pairs) == 1 and pairs[0][1] is None
    await nodes.analyse_offer(tenant_id=TENANT, offer=_offer(id="o-1"))
    pairs = await nodes.mission_offers(tenant_id=TENANT, mission_id="m-1")
    assert pairs[0][1] is not None


async def test_offers_are_tenant_scoped() -> None:
    store = InMemoryOfferStore()
    await store.add(_offer())
    assert await store.list_for_mission("tenant-b", "m-1") == []
    assert await store.get("tenant-b", "o-1") is None


async def test_storing_the_same_offer_twice_is_idempotent_but_a_conflict_is_loud() -> None:
    store = InMemoryOfferStore()
    await store.add(_offer())
    await store.add(_offer())
    with pytest.raises(ValueError, match="different content"):
        await store.add(_offer(unit_price_eur_minor=1))
