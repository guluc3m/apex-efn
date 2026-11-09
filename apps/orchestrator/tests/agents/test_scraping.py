"""Scraping orchestration (D4-09): normalise, deduplicate, convert to EUR, persist — and criterion 3."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from apex.agents.missions import MissionEventBus
from apex.agents.offers import InMemoryOfferStore
from apex.agents.scraping import (
    RawOffer,
    ScrapingDeps,
    ScrapingService,
    WorkerSearchResult,
    offers_from_fixture,
)
from apex.agents.sourcing import PlanStep, SourcingPlan
from apex.common.clock import FixedClock

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
MISSION = "m-1"
FIXTURES = Path(__file__).resolve().parents[4] / "apps/mock-marketplace/fixtures"


class _Worker:
    """Plays D5-01: returns the offers registered per platform."""

    def __init__(self, by_platform: dict[str, list[RawOffer]]) -> None:
        self.by_platform = by_platform
        self.calls: list[dict[str, Any]] = []

    async def search(
        self, *, tenant_id: str, mission_id: str, step: PlanStep, quantity: int
    ) -> WorkerSearchResult:
        self.calls.append({"platform": step.platform_id, "query": step.query, "quantity": quantity})
        return WorkerSearchResult(
            platform_id=step.platform_id, offers=list(self.by_platform.get(step.platform_id, []))
        )


class _Fx:
    """Fixed rates: USD 2:1, CNY 10:1. Records every conversion."""

    def __init__(self, rates: dict[str, int] | None = None, provisional: bool = False) -> None:
        self.rates = rates or {"EUR": 1, "USD": 2, "CNY": 10}
        self.provisional = provisional
        self.calls: list[tuple[int, str]] = []

    async def to_eur_unit(
        self, *, amount_minor: int, currency: str, tenant_id: str
    ) -> tuple[int, bool]:
        self.calls.append((amount_minor, currency))
        return amount_minor // self.rates[currency], self.provisional


def _raw(**overrides: Any) -> RawOffer:
    base: dict[str, Any] = {
        "platform_id": "mock-a",
        "platform_offer_id": "a-1",
        "seller_id": "s-1",
        "product_id": "p-1",
        "title": "Nitrile gloves",
        "unit_price_minor": 445,
        "list_price_minor": None,
        "currency": "EUR",
        "quantity_available": 500,
        "moq": 500,
        "raw_signals": {"rating": 4.8},
    }
    return RawOffer(**{**base, **overrides})


def _plan(*platforms: str) -> SourcingPlan:
    return SourcingPlan(
        steps=[PlanStep(platform_id=p, transport="http", query="gloves") for p in platforms],
        rationale="test",
        config_version="cfg-7",
    )


def _service(
    worker: _Worker, fx: _Fx | None = None, store: InMemoryOfferStore | None = None
) -> tuple[ScrapingService, InMemoryOfferStore, _Fx]:
    offers = store or InMemoryOfferStore()
    rate = fx or _Fx()
    service = ScrapingService(
        ScrapingDeps(
            worker=worker,
            fx=rate,
            offers=offers,
            bus=MissionEventBus(),
            clock=FixedClock(NOW),
        )
    )
    return service, offers, rate


# ----- dispatch ----------------------------------------------------------------------------------


async def test_every_plan_step_is_dispatched_with_its_query_and_quantity() -> None:
    worker = _Worker(
        {"mock-a": [_raw()], "mock-b": [_raw(platform_id="mock-b", platform_offer_id="b-1")]}
    )
    service, _, _ = _service(worker)
    result = await service.scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a", "mock-b"), quantity=500
    )
    assert [c["platform"] for c in worker.calls] == ["mock-a", "mock-b"]
    assert all(c["quantity"] == 500 for c in worker.calls)
    assert result.platforms == ["mock-a", "mock-b"]


# ----- normalisation and FX ----------------------------------------------------------------------


async def test_prices_are_converted_to_eur_at_ingestion() -> None:
    worker = _Worker({"mock-a": [_raw(unit_price_minor=1000, currency="USD")]})
    service, offers, fx = _service(worker)
    await service.scrape(tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500)
    stored = await offers.list_for_mission(TENANT, MISSION)
    assert stored[0].unit_price_eur_minor == 500  # 1000 USD at 2:1
    assert stored[0].currency == "EUR"
    assert fx.calls == [(1000, "USD")]


async def test_the_list_price_is_converted_too() -> None:
    worker = _Worker(
        {"mock-a": [_raw(unit_price_minor=800, list_price_minor=1000, currency="CNY")]}
    )
    service, offers, _ = _service(worker)
    await service.scrape(tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500)
    stored = await offers.list_for_mission(TENANT, MISSION)
    assert stored[0].unit_price_eur_minor == 80
    assert stored[0].list_price_eur_minor == 100


async def test_a_provisional_rate_is_reported_on_the_result() -> None:
    worker = _Worker({"mock-a": [_raw()]})
    service, _, _ = _service(worker, fx=_Fx(provisional=True))
    result = await service.scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500
    )
    assert result.fx_provisional is True


async def test_raw_signals_are_carried_through_untouched() -> None:
    worker = _Worker({"mock-a": [_raw(raw_signals={"reviewsTotal": 500, "disputeRate": 0.01})]})
    service, offers, _ = _service(worker)
    await service.scrape(tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500)
    stored = await offers.list_for_mission(TENANT, MISSION)
    assert stored[0].raw_signals == {"reviewsTotal": 500, "disputeRate": 0.01}


# ----- dedupe ------------------------------------------------------------------------------------


async def test_the_same_seller_and_product_on_two_platforms_keeps_the_cheapest() -> None:
    worker = _Worker(
        {
            "mock-a": [_raw(platform_id="mock-a", platform_offer_id="a-1", unit_price_minor=900)],
            "mock-b": [_raw(platform_id="mock-b", platform_offer_id="b-1", unit_price_minor=700)],
        }
    )
    service, offers, _ = _service(worker)
    result = await service.scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a", "mock-b"), quantity=500
    )
    stored = await offers.list_for_mission(TENANT, MISSION)
    assert len(stored) == 1 and stored[0].unit_price_eur_minor == 700
    assert result.collected == 2 and result.kept == 1
    assert result.duplicates[0].platform_id == "mock-a"
    assert result.duplicates[0].kept_platform_id == "mock-b"


async def test_different_products_or_sellers_are_not_deduplicated() -> None:
    worker = _Worker(
        {
            "mock-a": [
                _raw(platform_offer_id="a-1", seller_id="s-1", product_id="p-1"),
                _raw(platform_offer_id="a-2", seller_id="s-1", product_id="p-2"),
                _raw(platform_offer_id="a-3", seller_id="s-2", product_id="p-1"),
            ]
        }
    )
    service, offers, _ = _service(worker)
    result = await service.scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500
    )
    assert result.kept == 3 and result.duplicates == []
    assert len(await offers.list_for_mission(TENANT, MISSION)) == 3


async def test_dedupe_is_independent_of_arrival_order() -> None:
    cheap = _raw(platform_id="mock-b", platform_offer_id="b-1", unit_price_minor=700)
    dear = _raw(platform_id="mock-a", platform_offer_id="a-1", unit_price_minor=900)
    first, _, _ = _service(_Worker({"mock-a": [dear], "mock-b": [cheap]}))
    second, _, _ = _service(_Worker({"mock-a": [dear], "mock-b": [cheap]}))
    r1 = await first.scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a", "mock-b"), quantity=1
    )
    r2 = await second.scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-b", "mock-a"), quantity=1
    )
    assert r1.kept == r2.kept == 1
    assert r1.duplicates[0].kept_platform_id == r2.duplicates[0].kept_platform_id == "mock-b"


# ----- criterion 3: >= 3 offers from >= 2 platforms, in mock mode, fast ---------------------------


@pytest.mark.skipif(
    not (FIXTURES / "products.json").exists(), reason="mock marketplace fixtures missing"
)
async def test_criterion_3_three_offers_from_two_platforms_in_mock_mode() -> None:
    """The mock marketplace's own fixtures, through a worker stand-in for D5-01. No network."""
    products = json.loads((FIXTURES / "products.json").read_text(encoding="utf-8"))
    worker = _Worker(
        {
            "mock-a": offers_from_fixture(products, platform_id="mock-a"),
            "mock-b": offers_from_fixture(products, platform_id="mock-b"),
        }
    )
    service, offers, _ = _service(worker)
    started = time.monotonic()
    result = await service.scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a", "mock-b"), quantity=500
    )
    elapsed = time.monotonic() - started

    assert len(result.platforms) >= 2, result.platforms
    stored = await offers.list_for_mission(TENANT, MISSION)
    assert len(stored) >= 3, f"only {len(stored)} offers after dedupe"
    assert len({o.platform_id for o in stored}) >= 2
    assert elapsed < 30, f"took {elapsed:.1f}s"
    assert all(o.currency == "EUR" for o in stored)


def test_offers_from_fixture_filters_by_platform() -> None:
    products = {
        "products": [
            {"id": "a-1", "platform": "mock-a", "sellerId": "s", "productKey": "p",
             "unitPriceMinor": 100, "currency": "EUR", "moq": 10},
            {"id": "b-1", "platform": "mock-b", "sellerId": "s", "productKey": "p",
             "unitPriceMinor": 200, "currency": "EUR", "moq": 10},
        ]
    }  # fmt: skip
    only_b = offers_from_fixture(products, platform_id="mock-b")
    assert [o.platform_offer_id for o in only_b] == ["b-1"]
    assert only_b[0].unit_price_minor == 200


def test_offers_quoted_in_an_unsupported_currency_are_not_collected() -> None:
    products = {
        "products": [
            {"id": "a-1", "platform": "mock-a", "sellerId": "s", "productKey": "p",
             "unitPriceMinor": 100, "currency": "EUR", "moq": 10},
            {"id": "a-2", "platform": "mock-a", "sellerId": "s", "productKey": "p2",
             "unitPriceMinor": 100, "currency": "GBP", "moq": 10},
        ]
    }  # fmt: skip
    assert [o.platform_offer_id for o in offers_from_fixture(products, platform_id="mock-a")] == [
        "a-1"
    ]


# ----- skipped listings are visible, never silently dropped ---------------------------------------


async def test_listings_the_adapter_refused_are_reported_with_their_reason() -> None:
    """The contract's ``SkippedListing``: an offer that vanishes must say why."""
    from apex.agents.scraping import SkippedListing

    class _WorkerWithSkips(_Worker):
        async def search(self, *, tenant_id, mission_id, step, quantity):  # type: ignore[no-untyped-def]
            self.calls.append(
                {"platform": step.platform_id, "query": step.query, "quantity": quantity}
            )
            return WorkerSearchResult(
                platform_id=step.platform_id,
                offers=[_raw()],
                skipped=[
                    SkippedListing(
                        platform_id=step.platform_id,
                        platform_offer_id="a-gbp-1",
                        reason="unsupported_currency",
                        currency_raw="GBP",
                    )
                ],
            )

    service, _, _ = _service(_WorkerWithSkips({}))
    result = await service.scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500
    )
    assert result.kept == 1
    assert [(s.platform_offer_id, s.reason, s.currency_raw) for s in result.skipped] == [
        ("a-gbp-1", "unsupported_currency", "GBP")
    ]


async def test_no_skips_is_the_normal_case() -> None:
    service, _, _ = _service(_Worker({"mock-a": [_raw()]}))
    result = await service.scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500
    )
    assert result.skipped == []


# ----- a retryable worker failure is retried, a permanent one is not ------------------------------


class _FlakyWorker(_Worker):
    """Fails the first N calls with the given error, then behaves."""

    def __init__(self, failures: int, *, retryable: bool) -> None:
        super().__init__({"mock-a": [_raw()]})
        self.failures = failures
        self.retryable = retryable
        self.attempts = 0

    async def search(self, *, tenant_id, mission_id, step, quantity):  # type: ignore[no-untyped-def]
        self.attempts += 1
        if self.attempts <= self.failures:
            from apex.agents.scraping import WorkerError

            error = WorkerError("rate_limited" if self.retryable else "dom_changed")
            error.retryable = self.retryable
            raise error
        return await super().search(
            tenant_id=tenant_id, mission_id=mission_id, step=step, quantity=quantity
        )


def _retrying_service(worker: _FlakyWorker, sleeps: list[float]) -> ScrapingService:
    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    clock = FixedClock(NOW)
    return ScrapingService(
        ScrapingDeps(
            worker=worker,
            fx=_Fx(),
            offers=InMemoryOfferStore(),
            bus=MissionEventBus(),
            clock=clock,
            max_attempts=3,
            retry_backoff_s=1.0,
            sleep=_sleep,
        )
    )


async def test_a_rate_limited_step_is_retried_with_backoff() -> None:
    sleeps: list[float] = []
    worker = _FlakyWorker(failures=2, retryable=True)
    result = await _retrying_service(worker, sleeps).scrape(
        tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500
    )
    assert worker.attempts == 3
    assert sleeps == [1.0, 2.0]  # linear backoff, one wait between attempts
    assert result.kept == 1


async def test_a_permanent_failure_is_not_retried() -> None:
    sleeps: list[float] = []
    worker = _FlakyWorker(failures=1, retryable=False)
    from apex.agents.scraping import WorkerError

    with pytest.raises(WorkerError):
        await _retrying_service(worker, sleeps).scrape(
            tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500
        )
    assert worker.attempts == 1
    assert sleeps == []


async def test_retries_stop_at_max_attempts() -> None:
    sleeps: list[float] = []
    worker = _FlakyWorker(failures=99, retryable=True)
    from apex.agents.scraping import WorkerError

    with pytest.raises(WorkerError):
        await _retrying_service(worker, sleeps).scrape(
            tenant_id=TENANT, mission_id=MISSION, plan=_plan("mock-a"), quantity=500
        )
    assert worker.attempts == 3
    assert sleeps == [1.0, 2.0]
