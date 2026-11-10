"""``FxPort`` over DEV-3's FX engine (D3-03).

The scraping service converts every offer to EUR at ingestion (spec §3.5.1). The conversion itself is
``apex.domain.fx.convert``: EUR-pivot, freshest usable path, triangulation from the same source and
timestamp, and a ``fx_provisional`` flag when the rate is older than ``fx.max_age_hours``. This module only
supplies the two things the engine does not own — the rate history and the tenant's config slice.

A stale rate is **flagged, never dropped**: the offer still flows and the gate sees ``fx_provisional``
(criterion: the dashboard asks for an extra confirmation instead of hiding the offer).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from apex.common.clock import Clock
from apex.contracts.generated.models import Currency, FxRate
from apex.domain.fx import FxConfig, FxError, convert
from apex.domain.money import Money
from apex.tenant_config.service import TenantConfigService

BASE_CURRENCY = "EUR"


class FxRateReader(Protocol):
    """The insert-only ``fx_rates`` history, read side. Global: rates are not tenant-scoped."""

    async def rates(self) -> list[FxRate]: ...


@dataclass
class InMemoryFxRateReader:
    """Test and bootstrap reader. The real one reads ``fx_rates`` once D3-03's ingestion persists."""

    _rates: list[FxRate] = field(default_factory=list)

    async def rates(self) -> list[FxRate]:
        return list(self._rates)

    def add(self, rate: FxRate) -> None:
        self._rates.append(rate)


class FxUnavailable(Exception):
    """No usable rate. The message carries DEV-3's closed ``FxErrorCode``."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class DomainFxPort:
    """``FxPort``: one unit price, converted to EUR, with the provisional flag the gate needs."""

    rates: FxRateReader
    config: TenantConfigService
    clock: Clock

    async def to_eur_unit(
        self, *, amount_minor: int, currency: str, tenant_id: str
    ) -> tuple[int, bool]:
        if currency == BASE_CURRENCY:
            # No rate needed and nothing provisional: the common case must not touch the rate table.
            return amount_minor, False
        effective = await self.config.effective(tenant_id, None)
        cfg = FxConfig(max_age_hours=effective.typed.fx.max_age_hours)
        try:
            converted = convert(
                Money(amount_minor, Currency(currency)),
                BASE_CURRENCY,
                await self.rates.rates(),
                self.clock.now(),
                cfg,
            )
        except FxError as exc:
            raise FxUnavailable(exc.code, str(exc)) from exc
        return converted.amount_minor, converted.fx_provisional


__all__ = [
    "BASE_CURRENCY",
    "DomainFxPort",
    "FxRateReader",
    "FxUnavailable",
    "InMemoryFxRateReader",
]
