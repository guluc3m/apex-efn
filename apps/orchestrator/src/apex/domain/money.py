"""Money in integer minor units (D3-02, ADR-301). Runtime authority; ``@apex/money`` mirrors it.

No float enters or leaves: parse decimal strings, print with ``to_decimal_string``. Every fractional
result rounds half away from zero (ADR-900 Q1). Amounts stay within +-(2**53 - 1), the same range as TS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from apex.contracts.generated.models import Currency

MAX_AMOUNT = 2**53 - 1
# ISO 4217 minor units of the closed contract enum (spec 3.5.1)
MINOR_UNITS: dict[Currency, int] = {Currency.EUR: 100, Currency.USD: 100, Currency.CNY: 100}

_DECIMAL = re.compile(r"(-?)(\d+)(?:\.(\d+))?")

MoneyErrorCode = Literal[
    "invalid_amount",
    "amount_out_of_range",
    "invalid_decimal",
    "invalid_ratios",
    "invalid_divisor",
    "division_by_zero",
    "currency_mismatch",
    "unsupported_currency",
]


class MoneyError(ValueError):
    """Carries a stable ``code`` shared with the TS mirror (ADR-300)."""

    def __init__(self, code: MoneyErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def divide_half_away_from_zero(n: int, d: int) -> int:
    """``n / d`` rounded half away from zero. ``d`` is never 0."""
    q, r = divmod(abs(n), abs(d))
    if 2 * r >= abs(d):
        q += 1
    return -q if (n < 0) != (d < 0) else q


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_decimal(value: object) -> tuple[int, int]:
    match = _DECIMAL.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise MoneyError("invalid_decimal", f"Not a plain decimal string: {value!r}")
    sign, whole, fraction = match.group(1), match.group(2), match.group(3) or ""
    num = int(whole + fraction)
    return (-num if sign else num), 10 ** len(fraction)


def _currency(value: object) -> Currency:
    try:
        return Currency(str(value))
    except ValueError:
        raise MoneyError("unsupported_currency", f"Unsupported currency: {value!r}") from None


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: Currency

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency))
        if not _is_int(self.amount_minor):
            raise MoneyError(
                "invalid_amount", f"Amount must be integer minor units: {self.amount_minor!r}"
            )
        if abs(self.amount_minor) > MAX_AMOUNT:
            raise MoneyError(
                "amount_out_of_range", f"Amount outside +-(2**53 - 1): {self.amount_minor}"
            )

    @classmethod
    def parse(cls, amount: str, currency: Currency | str) -> Money:
        """``"-12.345"`` in major units to minor units, rounded half away from zero."""
        num, den = parse_decimal(amount)
        cur = _currency(currency)
        return cls(divide_half_away_from_zero(num * MINOR_UNITS[cur], den), cur)

    @classmethod
    def zero(cls, currency: Currency | str) -> Money:
        return cls(0, _currency(currency))

    def to_decimal_string(self) -> str:
        units = MINOR_UNITS[self.currency]
        whole, fraction = divmod(abs(self.amount_minor), units)
        digits = len(str(units)) - 1
        sign = "-" if self.amount_minor < 0 else ""
        return f"{sign}{whole}.{fraction:0{digits}d}" if digits else f"{sign}{whole}"

    def _same(self, other: Money) -> None:
        if self.currency != other.currency:
            raise MoneyError(
                "currency_mismatch", f"Currency mismatch: {self.currency} vs {other.currency}"
            )

    def __add__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount_minor, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.amount_minor), self.currency)

    def __lt__(self, other: Money) -> bool:
        self._same(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: Money) -> bool:
        self._same(other)
        return self.amount_minor <= other.amount_minor

    def multiply(self, factor: int | str) -> Money:
        """Multiply by an integer or a decimal string (``"1.21"``) as an exact rational."""
        num, den = (factor, 1) if _is_int(factor) else parse_decimal(factor)
        return Money(divide_half_away_from_zero(self.amount_minor * int(num), den), self.currency)

    def divide(self, divisor: int) -> Money:
        if not _is_int(divisor):
            raise MoneyError("invalid_divisor", f"Divisor must be an integer: {divisor!r}")
        if divisor == 0:
            raise MoneyError("division_by_zero", "Cannot divide by zero")
        return Money(divide_half_away_from_zero(self.amount_minor, divisor), self.currency)

    def allocate(self, ratios: list[int]) -> list[Money]:
        """Largest remainder on the absolute amount, ties to the lower index, sign last.

        The parts always sum to this amount and a zero ratio always gets zero.
        """
        if not ratios or not all(_is_int(r) and r >= 0 for r in ratios):
            raise MoneyError("invalid_ratios", f"Ratios must be non-negative integers: {ratios!r}")
        total = sum(ratios)
        if total == 0:
            raise MoneyError("invalid_ratios", "Ratios must have a positive sum")
        amount = abs(self.amount_minor)
        shares = [amount * r // total for r in ratios]
        left = amount - sum(shares)
        by_remainder = sorted(range(len(ratios)), key=lambda i: (-(amount * ratios[i] % total), i))
        for i in by_remainder[:left]:
            shares[i] += 1
        sign = -1 if self.amount_minor < 0 else 1
        return [Money(sign * s, self.currency) for s in shares]
