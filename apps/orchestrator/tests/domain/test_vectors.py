"""Shared vector framework (D3-01, ADR-300). ``packages/money/src/vectors.test.ts`` runs the same files."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from statistics import NormalDist
from typing import Any

import pytest

from apex.contracts.generated.models import FxRate, SellerSignalSnapshot
from apex.domain.fx import FxConfig, convert
from apex.domain.money import Money
from apex.domain.trust import Review, TrustConfig, compute
from tests.domain.vectors import ROOT, cases, domain_files, load_file, mismatch


def _money(data: dict[str, Any]) -> Money:
    return Money(data["amount_minor"], data["currency"])


def _out(m: Money) -> dict[str, Any]:
    return {"amount_minor": m.amount_minor, "currency": m.currency.value}


def _arithmetic(data: dict[str, Any], _config: Any) -> dict[str, Any]:
    a, b = _money(data["a"]), _money(data["b"])
    return _out(a + b if data["op"] == "add" else a - b)


def _convert(data: dict[str, Any], config: Any) -> dict[str, Any]:
    # model_construct: the engine, not the contract validator, must reject a bad rate (invalid_rate)
    rates = [
        FxRate.model_construct(**{**r, "as_of": datetime.fromisoformat(r["as_of"])})
        for r in data["rates"]
    ]
    now = datetime.fromisoformat(data["now"])
    result = convert(
        _money(data["money"]), data["to"], rates, now, FxConfig(config["max_age_hours"])
    )
    return result.model_dump(mode="json")


def _trust(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    seller = {k: v for k, v in config.items() if k != "config_version"}
    reviews = data.get("reviews")
    result = compute(
        SellerSignalSnapshot.model_validate(data["snapshot"]),
        TrustConfig.from_mapping(seller, config["config_version"]),
        now=datetime.fromisoformat(data["now"]),
        reviews=None
        if reviews is None
        else [
            Review(r["rating"], date.fromisoformat(r["date"]), r["verified"], r["text"])
            for r in reviews
        ],
    )
    return result.model_dump(mode="json")


# Engine ids of packages/test-vectors/money (ADR-301). packages/money/src/vectors.test.ts runs the same files.
ENGINES: dict[str, Callable[[Any, Any], Any]] = {
    "money.new": lambda d, _c: _out(_money(d)),
    "money.parse": lambda d, _c: _out(Money.parse(d["amount"], d["currency"])),
    "money.to_decimal": lambda d, _c: _money(d).to_decimal_string(),
    "money.arithmetic": _arithmetic,
    "money.multiply": lambda d, _c: _money(d).multiply(d["factor"]).amount_minor,
    "money.divide": lambda d, _c: _money(d).divide(d["divisor"]).amount_minor,
    "money.allocate": lambda d, _c: [m.amount_minor for m in _money(d).allocate(d["ratios"])],
    "fx.convert": _convert,
    "trust.compute": _trust,
    "trust.normal_inv_cdf": lambda d, _c: NormalDist().inv_cdf(d["p"]),
}

_all = [cases(folder) for folder in ("money", "fx", "trust")]
VECTORS, ERRORS = [v for c in _all for v in c[0]], [v for c in _all for v in c[1]]


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
