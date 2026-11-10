"""FX conversion with the EUR pivot (D3-03, ADR-302). ``@apex/money`` ``convert`` mirrors it.

Rates are decimal strings applied as exact rationals. A stale rate still converts, flagged
``fx_provisional``. Triangulated legs share one source and one ``as_of``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction
from typing import Literal

from apex.contracts.generated.models import ConvertedMoney, Currency, FxRate
from apex.domain.money import (
    MINOR_UNITS,
    Money,
    MoneyError,
    divide_half_away_from_zero,
    parse_decimal,
)

PIVOT = Currency.EUR  # fx.pivot is global and closed (ADR-900 Q13)
RATE_DECIMALS = 12  # fx_rates.rate is Decimal(24, 12)

FxErrorCode = Literal["rate_unavailable", "invalid_rate"]


class FxError(ValueError):
    def __init__(self, code: FxErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class FxConfig:
    """``fx.max_age_hours`` from the effective tenant config."""

    max_age_hours: int


@dataclass(frozen=True, slots=True)
class _Path:
    rate: Fraction
    as_of: datetime
    kind: int  # 0 direct, 1 inverse, 2 triangulated: the tie-break order
    source: str


def _value(rate: FxRate) -> Fraction:
    try:
        num, den = parse_decimal(rate.rate)
    except MoneyError:
        num, den = 0, 1
    if num <= 0:
        raise FxError("invalid_rate", f"Rate must be a positive decimal string: {rate.rate!r}")
    return Fraction(num, den)


def _legs(
    rates: list[FxRate], src: Currency, dst: Currency
) -> dict[tuple[datetime, str], tuple[Fraction, int]]:
    """Every ``src→dst`` rate keyed by (as_of, source), direct preferred over inverse."""
    found: dict[tuple[datetime, str], tuple[Fraction, int]] = {}
    for r in rates:
        if (r.base, r.quote) == (dst, src):
            found[(r.as_of, r.source)] = (1 / _value(r), 1)
    for r in rates:
        if (r.base, r.quote) == (src, dst):
            found[(r.as_of, r.source)] = (_value(r), 0)
    return found


def _paths(rates: list[FxRate], src: Currency, dst: Currency) -> list[_Path]:
    paths = [_Path(q, a, k, s) for (a, s), (q, k) in _legs(rates, src, dst).items()]
    if PIVOT not in (src, dst):
        first, second = _legs(rates, src, PIVOT), _legs(rates, PIVOT, dst)
        for key in first.keys() & second.keys():
            paths.append(_Path(first[key][0] * second[key][0], key[0], 2, key[1]))
    return paths


def _rate_string(rate: Fraction) -> str:
    scaled = divide_half_away_from_zero(rate.numerator * 10**RATE_DECIMALS, rate.denominator)
    whole, fraction = divmod(scaled, 10**RATE_DECIMALS)
    return f"{whole}.{fraction:0{RATE_DECIMALS}d}".rstrip("0").rstrip(".")


def convert(
    money: Money, to: Currency | str, rates: Iterable[FxRate], now: datetime, cfg: FxConfig
) -> ConvertedMoney:
    """Convert with the freshest usable path (ADR-302 §2); stale paths are flagged, never dropped."""
    target = Money.zero(to).currency
    if target == money.currency:
        return ConvertedMoney(
            amount_minor=money.amount_minor, currency=target, converted=False, fx_provisional=False
        )
    usable = [r for r in rates if r.as_of <= now]
    paths = _paths(usable, money.currency, target)
    if not paths:
        raise FxError(
            "rate_unavailable", f"No usable {money.currency}->{target} rate at {now.isoformat()}"
        )
    best = min(paths, key=lambda p: (-p.as_of.timestamp(), p.kind, p.source))
    factor = best.rate * MINOR_UNITS[target] / MINOR_UNITS[money.currency]
    amount = Money(
        divide_half_away_from_zero(money.amount_minor * factor.numerator, factor.denominator),
        target,
    )
    return ConvertedMoney(
        amount_minor=amount.amount_minor,
        currency=target,
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        fx_rate=_rate_string(best.rate),
        fx_as_of=best.as_of,
        fx_source=best.source,
        converted=True,
        fx_provisional=now - best.as_of > timedelta(hours=cfg.max_age_hours),
    )
