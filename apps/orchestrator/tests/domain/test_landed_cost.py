"""Landed cost and financial fit (D3-05, spec §3.5).

Criterion 4 is the headline: the lines add up exactly to the total, to the cent. The rest of the file pins the
two things that make a breakdown trustworthy — integer arithmetic everywhere, and "unknown" never becoming
"zero".
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apex.contracts.generated.models import (
    Currency,
    FinancialVerdict,
    LandedCostCode,
)
from apex.domain.finance.landed import (
    FinancialSnapshot,
    LandedCostError,
    LandedCostInputs,
    financial_fit,
    landed_cost,
    missing_inputs,
)

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


def _inputs(**kw) -> LandedCostInputs:
    base = {
        "unit_price_minor": 445,
        "quantity": 500,
        "shipping_minor": 12_000,
        "insurance_minor": 3_000,
        "duty_rate": Decimal("0.12"),
        "import_vat_rate": Decimal("0.21"),
        "cost_of_capital_rate": Decimal("0.06"),
        "payment_fee_rate": Decimal("0.015"),
        "fx_conversion_minor": 2_500,
        "fx_risk_rate": Decimal("0.01"),
        "payment_term_days": 30,
        "source_ids": {LandedCostCode.duties: "duty-table-v3"},
    }
    return LandedCostInputs(**{**base, **kw})


# ----- criterion 4: the lines add up exactly -----------------------------------------------------


def test_the_lines_add_up_exactly_to_the_total() -> None:
    breakdown = landed_cost(_inputs())
    assert sum(line.amount.amount_minor for line in breakdown.lines) == breakdown.total.amount_minor


@given(
    unit_price=st.integers(min_value=1, max_value=10_000_000),
    quantity=st.integers(min_value=1, max_value=10_000),
    shipping=st.integers(min_value=0, max_value=1_000_000),
    duty=st.decimals(min_value=0, max_value=1, places=4),
    vat=st.decimals(min_value=0, max_value=1, places=4),
)
def test_the_sum_is_exact_for_any_inputs(unit_price, quantity, shipping, duty, vat) -> None:
    """Property: no rounding drift can ever make the lines disagree with the total."""
    breakdown = landed_cost(
        LandedCostInputs(
            unit_price_minor=unit_price,
            quantity=quantity,
            shipping_minor=shipping,
            duty_rate=duty,
            import_vat_rate=vat,
        )
    )
    assert sum(line.amount.amount_minor for line in breakdown.lines) == breakdown.total.amount_minor


def test_every_amount_is_an_integer_number_of_minor_units() -> None:
    """Money never becomes a float, not even transiently in the output."""
    breakdown = landed_cost(_inputs())
    for line in breakdown.lines:
        assert isinstance(line.amount.amount_minor, int)
    assert isinstance(breakdown.total.amount_minor, int)
    assert isinstance(breakdown.unit_landed_cost.amount_minor, int)


# ----- the lines ---------------------------------------------------------------------------------


def test_the_goods_line_is_unit_price_times_quantity() -> None:
    breakdown = landed_cost(_inputs())
    goods = next(line for line in breakdown.lines if line.code is LandedCostCode.goods)
    assert goods.amount.amount_minor == 445 * 500


def test_duties_are_a_rate_on_the_goods() -> None:
    breakdown = landed_cost(_inputs())
    duties = next(line for line in breakdown.lines if line.code is LandedCostCode.duties)
    assert duties.amount.amount_minor == int(Decimal(222_500) * Decimal("0.12"))


def test_import_vat_is_charged_on_goods_plus_duties() -> None:
    """That is how a customs declaration computes it; charging VAT on goods alone understates the cost."""
    breakdown = landed_cost(_inputs())
    duties = next(line for line in breakdown.lines if line.code is LandedCostCode.duties)
    vat = next(line for line in breakdown.lines if line.code is LandedCostCode.import_vat)
    base = 222_500 + duties.amount.amount_minor
    assert vat.amount.amount_minor == int(Decimal(base) * Decimal("0.21"))


def test_the_cost_of_capital_is_prorated_over_the_payment_term() -> None:
    short = landed_cost(_inputs(payment_term_days=30))
    long = landed_cost(_inputs(payment_term_days=90))
    short_line = next(x for x in short.lines if x.code is LandedCostCode.capital_cost)
    long_line = next(x for x in long.lines if x.code is LandedCostCode.capital_cost)
    assert long_line.amount.amount_minor > short_line.amount.amount_minor


def test_a_line_carries_the_source_that_produced_it() -> None:
    breakdown = landed_cost(_inputs())
    duties = next(line for line in breakdown.lines if line.code is LandedCostCode.duties)
    assert duties.source == "duty-table-v3"


def test_the_unit_landed_cost_is_the_total_over_the_quantity() -> None:
    breakdown = landed_cost(
        _inputs(
            quantity=4,
            unit_price_minor=100,
            shipping_minor=0,
            insurance_minor=0,
            fx_conversion_minor=0,
        )
    )
    # Half-up is the documented rounding rule; Python's round() is half-to-even and would say 138.
    assert breakdown.unit_landed_cost.amount_minor == 139


# ----- unknown is not zero -----------------------------------------------------------------------


def test_a_missing_duty_rate_is_reported_as_missing_not_as_zero() -> None:
    """Q5: the difference between "no duty" and "we do not know the duty" decides whether a deal is safe."""
    inputs = _inputs(duty_rate=None)
    breakdown = landed_cost(inputs)
    codes = {line.code for line in breakdown.lines}
    assert LandedCostCode.duties not in codes
    assert LandedCostCode.duties in missing_inputs(inputs)


def test_a_complete_breakdown_reports_nothing_missing() -> None:
    assert missing_inputs(_inputs()) == []


def test_the_breakdown_is_in_the_requested_currency() -> None:
    breakdown = landed_cost(_inputs(currency=Currency.USD))
    assert breakdown.total.currency is Currency.USD


# ----- input validation --------------------------------------------------------------------------


@pytest.mark.parametrize("quantity", [0, -1])
def test_a_quantity_below_one_is_refused(quantity) -> None:
    with pytest.raises(LandedCostError) as caught:
        landed_cost(_inputs(quantity=quantity))
    assert caught.value.code == "invalid_quantity"


def test_a_negative_price_is_refused() -> None:
    with pytest.raises(LandedCostError) as caught:
        landed_cost(_inputs(unit_price_minor=-1))
    assert caught.value.code == "invalid_price"


# ----- financial fit -----------------------------------------------------------------------------


def _snapshot(**kw) -> FinancialSnapshot:
    base = {"envelope_minor": 500_000, "treasury_minor": 1_000_000, "credit_line_minor": 0}
    return FinancialSnapshot(**{**base, **kw})


def _fit(snapshot=None, **kw):
    breakdown = landed_cost(_inputs())
    return financial_fit(
        offer_id="o-1",
        breakdown=breakdown,
        snapshot=snapshot or _snapshot(),
        now=NOW,
        **kw,
    )


def test_a_cost_inside_the_envelope_is_within_budget() -> None:
    fit = _fit()
    assert fit.verdict is FinancialVerdict.within_budget
    assert fit.budget_utilization_bp is not None
    assert fit.computed_at == NOW


def test_a_cost_above_the_envelope_is_out_of_budget_with_a_numeric_reason() -> None:
    fit = _fit(_snapshot(envelope_minor=100_000))
    assert fit.verdict is FinancialVerdict.out_of_budget
    assert any("exceeds the envelope" in r for r in fit.reasons)


def test_a_cost_that_eats_the_safety_buffer_is_stretch() -> None:
    total = landed_cost(_inputs()).total.amount_minor
    # Envelope just above the total leaves nothing for the 15% buffer.
    fit = _fit(_snapshot(envelope_minor=int(total * 1.05)))
    assert fit.verdict is FinancialVerdict.stretch
    assert any("safety buffer" in r for r in fit.reasons)


def test_a_cost_the_treasury_cannot_cover_is_out_of_budget() -> None:
    fit = _fit(_snapshot(treasury_minor=1000, credit_line_minor=0))
    assert fit.verdict is FinancialVerdict.out_of_budget
    assert any("does not cover" in r for r in fit.reasons)


def test_the_credit_line_counts_towards_coverage() -> None:
    total = landed_cost(_inputs()).total.amount_minor
    fit = _fit(_snapshot(treasury_minor=0, credit_line_minor=total))
    assert fit.verdict is not FinancialVerdict.out_of_budget


def test_a_stale_snapshot_is_flagged_and_says_so() -> None:
    fit = _fit(_snapshot(stale=True))
    assert fit.financials_stale is True
    assert any("stale" in r for r in fit.reasons)


def test_the_utilization_is_in_basis_points_of_the_envelope() -> None:
    total = landed_cost(_inputs()).total.amount_minor
    fit = _fit(_snapshot(envelope_minor=total * 2))
    assert fit.budget_utilization_bp == 5000  # half the envelope
