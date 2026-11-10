"""Shared vector framework (D3-01, ADR-300). ``packages/money/src/vectors.test.ts`` runs the same files."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from tests.domain.vectors import ROOT, cases, domain_files, load_file, mismatch


class CodedError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# D3-01 framework sample. D3-02 replaces these adapters with the real money engine.
def _half_away_division(data: dict[str, Any], _config: Any) -> int | str:
    n, d = int(data["numerator"]), int(data["denominator"])
    if d == 0:
        raise CodedError("division_by_zero")
    q, r = divmod(abs(n), abs(d))
    if 2 * r >= abs(d):
        q += 1
    q = -q if (n < 0) != (d < 0) else q
    return str(q) if isinstance(data["numerator"], str) else q


def _mean(xs: list[float], _config: Any) -> float:
    if not xs:
        raise CodedError("empty_sample")
    return sum(xs) / len(xs)


ENGINES: dict[str, Callable[[Any, Any], Any]] = {
    "sample.half_away_division": _half_away_division,
    "sample.mean": _mean,
}

VECTORS, ERRORS = cases("sample")


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
