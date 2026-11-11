"""Landed cost and financial fit (D3-05, spec §3.5).

A price is not a cost. Two offers at the same unit price are not comparable when one ships from the other
side of the world with duties and import VAT on top and the other does not, so the comparison magnitude is
the **landed cost per unit in EUR** (spec §3.3.1).

Two invariants this module keeps:

* **The lines add up exactly to the total, to the cent** (criterion 4). Every line is integer minor units and
  the total is the integer sum: no floating point ever touches a money amount.
* **An unknown input is unknown, not zero.** A missing duty rate or cost of capital does not silently become
  0% — it makes the breakdown incomplete and says which line is missing (spec §3.5, ADR-900 Q5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from apex.contracts.generated.models import (
    Currency,
    FinancialFit,
    FinancialVerdict,
    LandedCostBreakdown,
    LandedCostCode,
    LandedCostLine,
    Money,
)

BASIS_POINTS = Decimal(10_000)
"""Rates are fractions (0.21 = 21%); money is multiplied by the fraction, never by a float."""


class LandedCostError(ValueError):
    """The breakdown cannot be computed. ``code`` is closed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class LandedCostInputs:
    """Everything the breakdown needs. Amounts are minor units in ``currency``.

    ``None`` means **unknown**, and an unknown input produces an ``unknown`` line rather than a zero: the
    difference between "no duty" and "we do not know the duty" decides whether a deal is safe (Q5).
    """

    unit_price_minor: int
    quantity: int
    currency: Currency = Currency.EUR
    shipping_minor: int | None = 0
    insurance_minor: int | None = 0
    duty_rate: Decimal | None = None
    import_vat_rate: Decimal | None = None
    cost_of_capital_rate: Decimal | None = None
    payment_fee_rate: Decimal | None = None
    fx_conversion_minor: int | None = 0
    fx_risk_rate: Decimal | None = None
    payment_term_days: int = 0
    source_ids: dict[LandedCostCode, str] = field(default_factory=dict)


def _apply(amount_minor: int, rate: Decimal) -> int:
    """``amount * rate`` in minor units, rounded half-up once, in integer arithmetic."""
    scaled = (Decimal(amount_minor) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(scaled)


def landed_cost(inputs: LandedCostInputs) -> LandedCostBreakdown:
    """Build the line-by-line breakdown. The total is the integer sum of the lines (criterion 4)."""
    if inputs.quantity < 1:
        raise LandedCostError("invalid_quantity", "quantity must be at least 1")
    if inputs.unit_price_minor < 0:
        raise LandedCostError("invalid_price", "unit price must not be negative")
    goods = inputs.unit_price_minor * inputs.quantity
    lines: list[LandedCostLine] = [
        _line(LandedCostCode.goods, goods, inputs),
    ]

    if inputs.shipping_minor is not None:
        lines.append(_line(LandedCostCode.shipping, inputs.shipping_minor, inputs))
    if inputs.insurance_minor is not None:
        lines.append(_line(LandedCostCode.insurance, inputs.insurance_minor, inputs))
    if inputs.duty_rate is not None:
        lines.append(_line(LandedCostCode.duties, _apply(goods, inputs.duty_rate), inputs))
    if inputs.import_vat_rate is not None:
        # Import VAT is charged on goods + duties, which is how a customs declaration computes it.
        duties = _apply(goods, inputs.duty_rate) if inputs.duty_rate is not None else 0
        lines.append(
            _line(LandedCostCode.import_vat, _apply(goods + duties, inputs.import_vat_rate), inputs)
        )
    if inputs.cost_of_capital_rate is not None and inputs.payment_term_days > 0:
        # Simple interest over the payment term: the cost of paying before the buyer is paid.
        rate = inputs.cost_of_capital_rate * Decimal(inputs.payment_term_days) / Decimal(365)
        lines.append(_line(LandedCostCode.capital_cost, _apply(goods, rate), inputs))
    if inputs.payment_fee_rate is not None:
        lines.append(
            _line(LandedCostCode.payment_fees, _apply(goods, inputs.payment_fee_rate), inputs)
        )
    if inputs.fx_conversion_minor is not None:
        lines.append(_line(LandedCostCode.fx_conversion, inputs.fx_conversion_minor, inputs))
    if inputs.fx_risk_rate is not None:
        lines.append(_line(LandedCostCode.fx_risk, _apply(goods, inputs.fx_risk_rate), inputs))

    total = sum(line.amount.amount_minor for line in lines)
    return LandedCostBreakdown(
        unit_price=Money(amount_minor=inputs.unit_price_minor, currency=inputs.currency),
        quantity=inputs.quantity,
        lines=lines,
        total=Money(amount_minor=total, currency=inputs.currency),
        unit_landed_cost=Money(
            amount_minor=_unit(total, inputs.quantity), currency=inputs.currency
        ),
    )


def _unit(total_minor: int, quantity: int) -> int:
    """Per-unit cost, rounded half-up once. ``quantity`` is at least 1."""
    return int(
        (Decimal(total_minor) / Decimal(quantity)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    )


def _line(code: LandedCostCode, amount_minor: int, inputs: LandedCostInputs) -> LandedCostLine:
    return LandedCostLine(
        code=code,
        amount=Money(amount_minor=amount_minor, currency=inputs.currency),
        source=inputs.source_ids.get(code),
    )


def missing_inputs(inputs: LandedCostInputs) -> list[LandedCostCode]:
    """Which lines could not be computed because an input is unknown. Empty means the breakdown is complete."""
    missing: list[LandedCostCode] = []
    if inputs.duty_rate is None:
        missing.append(LandedCostCode.duties)
    if inputs.import_vat_rate is None:
        missing.append(LandedCostCode.import_vat)
    if inputs.cost_of_capital_rate is None and inputs.payment_term_days > 0:
        missing.append(LandedCostCode.capital_cost)
    if inputs.payment_fee_rate is None:
        missing.append(LandedCostCode.payment_fees)
    if inputs.fx_risk_rate is None:
        missing.append(LandedCostCode.fx_risk)
    return missing


# ----- financial fit ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FinancialSnapshot:
    """The slice of the tenant's financial position the fit needs (D3-04 produces it from the CSV)."""

    envelope_minor: int
    """Budget available for the category, in EUR minor units."""
    treasury_minor: int
    """Projected treasury at the payment date."""
    credit_line_minor: int = 0
    safety_buffer_pct: Decimal = Decimal(15)
    as_of: datetime | None = None
    stale: bool = False


def financial_fit(
    *,
    offer_id: str,
    breakdown: LandedCostBreakdown,
    snapshot: FinancialSnapshot,
    now: datetime,
    stretch_threshold_pct: Decimal = Decimal(0),
) -> FinancialFit:
    """Compare the landed cost with the envelope, the treasury and the credit line (spec §3.5).

    ``stretch`` means it fits, but only by eating into the safety buffer or the credit line. The reasons are
    numeric strings the dashboard shows verbatim, so the verdict is never a bare label.
    """
    total = breakdown.total.amount_minor
    reasons: list[str] = []
    verdict = FinancialVerdict.within_budget
    utilization_bp = (
        int(Decimal(total) * BASIS_POINTS / Decimal(snapshot.envelope_minor))
        if snapshot.envelope_minor > 0
        else None
    )
    if snapshot.envelope_minor <= 0:
        reasons.append("the category envelope is 0: nothing can be bought against it")
        verdict = FinancialVerdict.out_of_budget
    elif total > snapshot.envelope_minor:
        over = Decimal(total - snapshot.envelope_minor) * 100 / Decimal(snapshot.envelope_minor)
        reasons.append(
            f"landed cost {total} exceeds the envelope {snapshot.envelope_minor} "
            f"by {over.quantize(Decimal('0.1'))}%"
        )
        verdict = FinancialVerdict.out_of_budget
    else:
        buffer_minor = _apply(snapshot.envelope_minor, snapshot.safety_buffer_pct / Decimal(100))
        spendable = snapshot.envelope_minor - buffer_minor
        if total > spendable:
            reasons.append(
                f"landed cost {total} fits the envelope but eats into the "
                f"{snapshot.safety_buffer_pct}% safety buffer ({buffer_minor})"
            )
            verdict = FinancialVerdict.stretch
        if stretch_threshold_pct > 0 and utilization_bp is not None:
            threshold_bp = int(stretch_threshold_pct * 100)
            if utilization_bp > threshold_bp and verdict is FinancialVerdict.within_budget:
                reasons.append(
                    f"landed cost uses {utilization_bp / 100:.1f}% of the envelope, above the "
                    f"{stretch_threshold_pct}% threshold"
                )
                verdict = FinancialVerdict.stretch

    treasury_impact: Money | None = None
    if snapshot.treasury_minor >= 0:
        treasury_impact = Money(amount_minor=total, currency=breakdown.total.currency)
        if total > snapshot.treasury_minor + snapshot.credit_line_minor:
            reasons.append(
                f"projected treasury {snapshot.treasury_minor} plus credit line "
                f"{snapshot.credit_line_minor} does not cover {total}"
            )
            verdict = FinancialVerdict.out_of_budget
    if snapshot.stale:
        reasons.append("the financial snapshot is stale: refresh it before committing")

    return FinancialFit(
        offer_id=offer_id,
        landed_cost=breakdown,
        verdict=verdict,
        reasons=reasons,
        budget_utilization_bp=utilization_bp,
        treasury_impact=treasury_impact,
        financials_stale=snapshot.stale,
        computed_at=now,
    )


__all__ = [
    "BASIS_POINTS",
    "FinancialSnapshot",
    "LandedCostError",
    "LandedCostInputs",
    "financial_fit",
    "landed_cost",
    "missing_inputs",
]
