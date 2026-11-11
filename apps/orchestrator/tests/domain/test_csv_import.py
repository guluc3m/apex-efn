"""D3-04: criteria 2 and 24 at the engine level."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from apex.contracts.generated.models import Currency, FxRate
from apex.contracts.generated.models import RowRejectionReason as R
from apex.domain.finance.csv_import import CsvImportError, parse
from apex.domain.fx import FxConfig

FIXTURES = Path(__file__).resolve().parents[4] / "packages" / "test-vectors" / "finance"
NOW = datetime(2026, 11, 5, tzinfo=UTC)
CFG = FxConfig(max_age_hours=48)
RATES = [
    FxRate(
        base=Currency.EUR,
        quote=Currency.USD,
        rate="1.25",
        as_of=datetime(2026, 10, 31, tzinfo=UTC),
        source="ecb",
    )
]


def _parse(name: str, base: str = "EUR", rates: list[FxRate] | None = None):
    return parse((FIXTURES / name).read_bytes(), base, RATES if rates is None else rates, NOW, CFG)


def test_valid_file_enables_projection_and_derives_capacity() -> None:
    r = _parse("valid.csv")
    assert (r.report.rows_ok, r.report.rows_rejected) == (7, 0)
    assert r.report.projection_enabled and r.report.periods_loaded == 3
    assert str(r.report.reference_date) == "2026-10-31"
    # 5_400_000 + 1_000_000 - 200_000 - 15% of cash (810_000)
    assert r.derived.net_buying_capacity.amount_minor == 5_390_000
    assert r.derived.buying_power_score is None and r.derived.envelopes == []


def test_invalid_rows_are_rejected_one_by_one() -> None:  # criterion 2
    r = _parse("invalid_rows.csv")
    reasons = {x.row: x.reason_code for x in r.report.rejections}
    assert reasons == {
        2: R.non_integer_amount,
        3: R.malformed_period,
        4: R.unknown_metric,
        5: R.unsupported_currency,
        6: R.duplicate_period_metric,
        7: R.missing_required_field,
    }
    assert (
        r.report.rows_ok == 1 and r.rows_duplicated == 1
    )  # the later duplicate goes, not the file
    assert not r.report.projection_enabled and "projection_disabled" in r.warning_codes


def test_foreign_currency_is_converted_with_fx_recorded() -> None:  # criterion 24
    r = _parse("usd_tab.csv")
    amount = r.rows[0].amount
    assert amount and amount.converted and amount.amount_minor == 800_000  # 1_000_000 USD / 1.25
    assert (amount.original_currency, amount.fx_rate, amount.fx_source) == (
        Currency.USD,
        "0.8",  # applied USD->EUR rate
        "ecb",
    )
    assert not amount.fx_provisional and r.rows_converted == 1


def test_stale_fx_is_provisional_and_missing_fx_rejects() -> None:
    old = [RATES[0].model_copy(update={"as_of": datetime(2026, 9, 1, tzinfo=UTC)})]
    assert _parse("usd_tab.csv", rates=old).fx_provisional
    r = _parse("usd_tab.csv", rates=[])
    assert r.report.rows_ok == 0 and r.report.rejections[0].reason_code is R.unsupported_currency


def test_unreadable_files_raise() -> None:
    for bad in (b"\xff\xfe\x00", b"", b"a,b\n1,2\n"):
        with pytest.raises(CsvImportError):
            parse(bad, "EUR", [], NOW, CFG)


def test_is_deterministic() -> None:
    assert _parse("valid.csv") == _parse("valid.csv")
