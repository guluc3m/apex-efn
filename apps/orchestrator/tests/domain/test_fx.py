"""Properties of apex.domain.fx.convert (D3-03, ADR-302). The shared vectors are in test_vectors.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from apex.contracts.generated.models import Currency, FxRate
from apex.domain.fx import FxConfig, convert
from apex.domain.money import Money, divide_half_away_from_zero

AS_OF = datetime(2026, 1, 1, 15, tzinfo=UTC)
NOW = AS_OF + timedelta(hours=21)
CFG = FxConfig(max_age_hours=36)
amounts = st.integers(-(10**9), 10**9)  # times a rate up to 1e6 stays below 2**53
rates = st.integers(1, 999_999)  # numerator over 10**4


def _rate(quote: Currency, n: int) -> FxRate:
    text = f"{n // 10**4}.{n % 10**4:04d}"
    return FxRate(base=Currency.EUR, quote=quote, rate=text, as_of=AS_OF, source="ecb")


@given(amounts, rates)
def test_round_trip_within_two_roundings(amount: int, n: int) -> None:
    fx = [_rate(Currency.USD, n)]
    there = convert(Money(amount, Currency.EUR), Currency.USD, fx, NOW, CFG)
    back = convert(Money(there.amount_minor, Currency.USD), Currency.EUR, fx, NOW, CFG)
    assert 2 * abs(back.amount_minor - amount) * n <= n + 10**4


@given(amounts, rates, rates)
def test_triangulation_rounds_once(amount: int, usd: int, cny: int) -> None:
    fx = [_rate(Currency.USD, usd), _rate(Currency.CNY, cny)]
    result = convert(Money(amount, Currency.USD), Currency.CNY, fx, NOW, CFG)
    assert result.amount_minor == divide_half_away_from_zero(amount * cny, usd)
    assert result.fx_as_of == AS_OF and result.fx_source == "ecb"


def test_provisional_only_after_max_age() -> None:
    fx = [_rate(Currency.USD, 11_000)]
    fresh = convert(Money.zero(Currency.EUR), Currency.USD, fx, AS_OF + timedelta(hours=36), CFG)
    stale = convert(
        Money.zero(Currency.EUR), Currency.USD, fx, AS_OF + timedelta(hours=36, seconds=1), CFG
    )
    assert (fresh.fx_provisional, stale.fx_provisional) == (False, True)
