"""Property tests for apex.domain.money (D3-02, ADR-301). The shared vectors are in test_vectors.py."""

from __future__ import annotations

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from apex.contracts.generated.models import Currency
from apex.domain.money import MAX_AMOUNT, Money, MoneyError

amounts = st.integers(-MAX_AMOUNT, MAX_AMOUNT)
currencies = st.sampled_from(list(Currency))
small = st.integers(-(10**9), 10**9)
divisors = st.integers(1, 10**6)


@given(amounts, currencies)
def test_decimal_round_trip(amount: int, currency: Currency) -> None:
    m = Money(amount, currency)
    assert Money.parse(m.to_decimal_string(), currency) == m


@given(small, divisors)
def test_rounding_is_symmetric_and_within_half(amount: int, d: int) -> None:
    m = Money(amount, Currency.EUR)
    q = m.divide(d).amount_minor
    assert (-m).divide(d).amount_minor == -q
    assert (-m).multiply(f"0.{d}") == -m.multiply(f"0.{d}")
    assert abs(2 * (q * d - amount)) <= d


@given(amounts, st.lists(st.integers(0, 10**6), min_size=1, max_size=12))
def test_allocation_sums_exactly(amount: int, ratios: list[int]) -> None:
    assume(any(ratios))
    parts = [p.amount_minor for p in Money(amount, Currency.EUR).allocate(ratios)]
    assert sum(parts) == amount
    total = sum(ratios)
    for part, ratio in zip(parts, ratios, strict=True):
        assert abs(part * total - amount * ratio) < total
        assert ratio or part == 0


def test_comparisons_and_sign() -> None:
    a, b = Money(-1234, Currency.EUR), Money.zero(Currency.EUR)
    assert a < b and a <= a and abs(a) == -a
    with pytest.raises(MoneyError) as raised:
        _ = a < Money(1, Currency.USD)
    assert raised.value.code == "currency_mismatch"
    with pytest.raises(MoneyError):
        _ = a <= Money(1, Currency.CNY)
