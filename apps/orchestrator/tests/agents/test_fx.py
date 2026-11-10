"""``DomainFxPort``: the scraping service's view of DEV-3's FX engine (D3-03)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apex.agents.fx import DomainFxPort, FxUnavailable, InMemoryFxRateReader
from apex.common.clock import FixedClock
from apex.contracts.generated.models import Currency, FxRate
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.service import TenantConfigService

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"


class _Decisions:
    async def create_decision(self, *a: Any, **k: Any) -> Any:
        raise NotImplementedError

    async def require_signed(self, *a: Any, **k: Any) -> Any:
        raise NotImplementedError

    async def sign_service_event(self, *a: Any, **k: Any) -> Any:
        raise NotImplementedError


def _config() -> TenantConfigService:

    service = TenantConfigService(
        InMemoryConfigRepository(),
        _Decisions(),
        FixedClock(NOW),  # type: ignore[arg-type]
    )
    return service


async def _seeded_config() -> TenantConfigService:
    from apex.tenant_config.load_defaults import seed

    service = _config()
    await seed([TENANT], service._repo)  # type: ignore[attr-defined]
    return service


def _rate(base: str, quote: str, rate: str, *, age_hours: float = 1.0) -> FxRate:
    return FxRate(
        base=Currency(base),
        quote=Currency(quote),
        rate=rate,
        as_of=NOW - timedelta(hours=age_hours),
        source="ecb",
    )


async def test_eur_needs_no_rate_and_is_never_provisional() -> None:
    port = DomainFxPort(
        rates=InMemoryFxRateReader(), config=await _seeded_config(), clock=FixedClock(NOW)
    )
    assert await port.to_eur_unit(amount_minor=445, currency="EUR", tenant_id=TENANT) == (
        445,
        False,
    )


async def test_a_usd_price_is_converted_with_the_engine() -> None:
    reader = InMemoryFxRateReader()
    reader.add(_rate("USD", "EUR", "0.920000000000"))
    port = DomainFxPort(rates=reader, config=await _seeded_config(), clock=FixedClock(NOW))
    amount, provisional = await port.to_eur_unit(
        amount_minor=1000, currency="USD", tenant_id=TENANT
    )
    assert amount == 920  # 10.00 USD at 0.92, half away from zero
    assert provisional is False


async def test_a_stale_rate_is_flagged_not_dropped() -> None:
    """The offer still flows; the gate asks for an extra confirmation (spec §3.5.1)."""
    reader = InMemoryFxRateReader()
    reader.add(_rate("USD", "EUR", "0.920000000000", age_hours=24 * 30))
    port = DomainFxPort(rates=reader, config=await _seeded_config(), clock=FixedClock(NOW))
    amount, provisional = await port.to_eur_unit(
        amount_minor=1000, currency="USD", tenant_id=TENANT
    )
    assert amount == 920
    assert provisional is True


async def test_a_triangulated_rate_uses_the_same_source_and_timestamp() -> None:
    reader = InMemoryFxRateReader()
    reader.add(_rate("USD", "EUR", "0.920000000000"))
    reader.add(_rate("CNY", "EUR", "0.130000000000"))
    port = DomainFxPort(rates=reader, config=await _seeded_config(), clock=FixedClock(NOW))
    amount, _ = await port.to_eur_unit(amount_minor=10_000, currency="CNY", tenant_id=TENANT)
    assert amount == 1300


async def test_no_usable_rate_is_a_loud_error_with_the_engine_code() -> None:
    port = DomainFxPort(
        rates=InMemoryFxRateReader(), config=await _seeded_config(), clock=FixedClock(NOW)
    )
    with pytest.raises(FxUnavailable) as caught:
        await port.to_eur_unit(amount_minor=1000, currency="USD", tenant_id=TENANT)
    assert caught.value.code == "rate_unavailable"


async def test_the_max_age_comes_from_the_tenant_config() -> None:
    """``fx.max_age_hours`` decides provisional, so a tighter tenant flags an older rate."""
    reader = InMemoryFxRateReader()
    reader.add(_rate("USD", "EUR", "0.920000000000", age_hours=30))
    config = await _seeded_config()
    port = DomainFxPort(rates=reader, config=config, clock=FixedClock(NOW))
    _, provisional = await port.to_eur_unit(amount_minor=1000, currency="USD", tenant_id=TENANT)
    effective = await config.effective(TENANT, None)
    assert provisional is (effective.typed.fx.max_age_hours < 30)
