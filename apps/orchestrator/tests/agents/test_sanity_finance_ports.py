"""``DomainSanityPort`` and ``DomainFinancePort`` (D3-07, D3-05) against the real tenant config."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apex.agents.finance_port import DomainFinancePort, FinanceUnavailable
from apex.agents.offers import InMemoryOfferStore, Offer
from apex.agents.onboarding import FinancialSnapshot, OnboardingIncomplete
from apex.agents.ports import PriceBand
from apex.agents.sanity_port import DomainSanityPort
from apex.common.clock import FixedClock
from apex.tenant_config.load_defaults import seed
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.service import TenantConfigService

NOW = datetime(2026, 11, 11, tzinfo=UTC)
T = "tenant-a"


class _D:
    pass


async def _config() -> TenantConfigService:
    svc = TenantConfigService(InMemoryConfigRepository(), _D(), FixedClock(NOW))  # type: ignore[arg-type]
    await seed([T], svc._repo)  # type: ignore[attr-defined]
    return svc


def _offer(i: int, price: int) -> Offer:
    return Offer(
        id=f"o-{i}", tenant_id=T, mission_id="m-1", platform_id="p", seller_id=f"s-{i}",
        product_id="x", unit_price_eur_minor=price, currency="EUR", quantity=10, collected_at=NOW,
    )  # fmt: skip


def _payload(o: Offer) -> dict[str, object]:
    return {"offer_id": o.id, "mission_id": o.mission_id, "unit_price_eur_minor": o.unit_price_eur_minor,
            "quantity": o.quantity}  # fmt: skip


async def test_sanity_uses_the_other_offers_of_the_mission_as_reference() -> None:
    store = InMemoryOfferStore()
    offers = [
        _offer(i, p)
        for i, p in enumerate([1000, 1020, 990, 1010, 1005, 1015, 995, 1000, 1008, 100])
    ]
    for o in offers:
        await store.add(o)
    port = DomainSanityPort(config=await _config(), offers=store, clock=FixedClock(NOW))
    cheap = await port.check(_payload(offers[-1]), tenant_id=T, price_minor=None)
    normal = await port.check(_payload(offers[0]), tenant_id=T, price_minor=None)
    assert cheap.band in (PriceBand.ATYPICAL, PriceBand.IMPLAUSIBLE)
    assert normal.band is PriceBand.NORMAL
    assert cheap.config_version.startswith("price-sanity")


async def test_sanity_without_enough_peers_is_insufficient_reference() -> None:
    store = InMemoryOfferStore()
    only = _offer(0, 1000)
    await store.add(only)
    port = DomainSanityPort(config=await _config(), offers=store, clock=FixedClock(NOW))
    out = await port.check(_payload(only), tenant_id=T, price_minor=None)
    assert out.band is PriceBand.INSUFFICIENT_REFERENCE


class _Onboarding:
    def __init__(self, active: bool, stale: bool = False) -> None:
        self.active, self.stale = active, stale

    async def require_active_snapshot(self, *, tenant_id: str) -> FinancialSnapshot:
        if not self.active:
            raise OnboardingIncomplete(tenant_id)
        return FinancialSnapshot(
            id="s", tenant_id=tenant_id, session_id="x", status="active", stored_object="k",  # type: ignore[arg-type]
            report={"derived": {"envelopes": [], "net_buying_capacity": {"amount_minor": 5_000_000}}},
            config_version="1", imported_at=NOW, activated_at=NOW,
        )  # fmt: skip

    async def is_financials_stale(self, *, tenant_id: str) -> bool:
        return self.stale


async def test_finance_without_envelope_is_out_of_budget_and_reports_staleness() -> None:
    port = DomainFinancePort(
        config=await _config(), onboarding=_Onboarding(True, True), clock=FixedClock(NOW)
    )  # type: ignore[arg-type]
    out = await port.fit(_payload(_offer(0, 1000)), tenant_id=T)
    assert out.verdict == "out_of_budget" and out.financials_stale


async def test_finance_without_active_snapshot_is_loud() -> None:
    port = DomainFinancePort(
        config=await _config(), onboarding=_Onboarding(False), clock=FixedClock(NOW)
    )  # type: ignore[arg-type]
    with pytest.raises(FinanceUnavailable):
        await port.fit(_payload(_offer(0, 1000)), tenant_id=T)
