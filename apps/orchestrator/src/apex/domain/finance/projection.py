"""Multi-period treasury projection from the imported CSV rows (D3-10, ADR-306). Pure, integer minor units."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from apex.domain.finance.csv_import import ImportRow

INFLOWS = ("revenue",)
# tax_reserve is a stock (already subtracted from the buying capacity), not a monthly flow.
OUTFLOWS = ("cogs", "fixed_costs", "payroll", "debt_service", "capex")


class ProjectionError(ValueError):
    """Not enough history to project (fewer periods than the configured minimum)."""


@dataclass(frozen=True, slots=True)
class TreasuryProjection:
    base_minor: int
    """Latest ``cash_balance``."""
    expected_minor: int
    """``base + mean(net) * months``."""
    pessimistic_minor: int
    """``base + min(net) * months``."""
    months: int
    periods_used: list[str]
    mean_net_minor: int
    min_net_minor: int


def _months_between(reference: date, pay: date) -> int:
    return max(0, (pay.year - reference.year) * 12 + pay.month - reference.month)


def project_treasury(
    rows: Sequence[ImportRow], pay_date: date, *, window: int, min_periods: int
) -> TreasuryProjection:
    """Project the cash at ``pay_date``. ``window`` and ``min_periods`` come from config (never defaulted here)."""
    if window < 1 or min_periods < 1:
        raise ValueError("window and min_periods must be >= 1")

    def amount(period: str, metric: str) -> int:
        return sum(
            r.amount.amount_minor
            for r in rows
            if r.period == period and r.metric == metric and r.amount
        )

    cash = {
        r.period: r.amount.amount_minor for r in rows if r.metric == "cash_balance" and r.amount
    }
    periods = sorted(cash)[-window:]
    if len(periods) < min_periods:
        raise ProjectionError(f"{len(periods)} periods with cash_balance, {min_periods} needed")
    nets = [
        sum(amount(p, m) for m in INFLOWS) - sum(amount(p, m) for m in OUTFLOWS) for p in periods
    ]
    last = periods[-1]
    months = _months_between(date(int(last[:4]), int(last[5:]), 1), pay_date)
    mean = sum(nets) // len(nets)  # floor: the conservative side for a signed integer mean
    return TreasuryProjection(
        base_minor=cash[last],
        expected_minor=cash[last] + mean * months,
        pessimistic_minor=cash[last] + min(nets) * months,
        months=months,
        periods_used=periods,
        mean_net_minor=mean,
        min_net_minor=min(nets),
    )
