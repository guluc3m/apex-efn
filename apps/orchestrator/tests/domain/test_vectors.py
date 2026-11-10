"""Shared vector framework (D3-01, ADR-300). ``packages/money/src/vectors.test.ts`` runs the same files."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from apex.domain.money import Money
from tests.domain.vectors import ROOT, cases, domain_files, load_file, mismatch


def _money(data: dict[str, Any]) -> Money:
    return Money(data["amount_minor"], data["currency"])


def _out(m: Money) -> dict[str, Any]:
    return {"amount_minor": m.amount_minor, "currency": m.currency.value}


def _arithmetic(data: dict[str, Any], _config: Any) -> dict[str, Any]:
    a, b = _money(data["a"]), _money(data["b"])
    return _out(a + b if data["op"] == "add" else a - b)


# Engine ids of packages/test-vectors/money (ADR-301). packages/money/src/vectors.test.ts runs the same files.
ENGINES: dict[str, Callable[[Any, Any], Any]] = {
    "money.new": lambda d, _c: _out(_money(d)),
    "money.parse": lambda d, _c: _out(Money.parse(d["amount"], d["currency"])),
    "money.to_decimal": lambda d, _c: _money(d).to_decimal_string(),
    "money.arithmetic": _arithmetic,
    "money.multiply": lambda d, _c: _money(d).multiply(d["factor"]).amount_minor,
    "money.divide": lambda d, _c: _money(d).divide(d["divisor"]).amount_minor,
    "money.allocate": lambda d, _c: [m.amount_minor for m in _money(d).allocate(d["ratios"])],
}

VECTORS, ERRORS = cases("money")


@pytest.mark.parametrize(("file", "vector"), VECTORS)
def test_vector(file: dict[str, Any], vector: dict[str, Any]) -> None:
    engine = ENGINES[file["engine"]]
    tolerance = vector.get("tolerance", file["tolerance"])
    assert (
        mismatch(engine(vector["input"], vector.get("config")), vector["expected"], tolerance)
        is None
    )


@pytest.mark.parametrize(("file", "vector"), ERRORS)
def test_error_vector(file: dict[str, Any], vector: dict[str, Any]) -> None:
    with pytest.raises(Exception) as raised:  # noqa: PT011 - the code attribute is what is checked
        ENGINES[file["engine"]](vector["input"], vector.get("config"))
    assert getattr(raised.value, "code", None) == vector["expected"]["error"]


def test_every_domain_file_is_valid() -> None:
    """Schema, safe integers and unique names for every file any lane adds, signing/ excluded."""
    files = domain_files()
    assert files, ROOT
    for path in files:
        load_file(path)


def test_comparator() -> None:
    assert mismatch(0.1 + 0.2, 0.3, 1e-12) is None
    assert mismatch(0.1 + 0.2, 0.3) is not None
    assert mismatch({"a": [1, 2]}, {"a": [1, 2]}) is None
    assert mismatch({"a": 1, "b": 2}, {"a": 1}) == "$.b: unexpected"
    assert mismatch("1", 1) is not None
    assert mismatch(True, 1) is not None


def test_signing_is_not_loaded() -> None:
    with pytest.raises(ValueError, match="signing"):
        cases("signing")
