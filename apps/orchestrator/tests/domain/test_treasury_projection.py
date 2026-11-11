"""D3-10: multi-period treasury projection (ADR-306)."""

from __future__ import annotations

from datetime import date

import pytest

from apex.contracts.generated.models import ConvertedMoney, Currency
from apex.domain.finance.csv_import import ImportRow
from apex.domain.finance.projection import ProjectionError, project_treasury


def _rows(data: dict[str, dict[str, int]]) -> list[ImportRow]:
    return [
        ImportRow(
            1,
            p,
            m,
            amount=ConvertedMoney(
                amount_minor=v, currency=Currency.EUR, converted=False, fx_provisional=False
            ),
        )
        for p, metrics in data.items()
        for m, v in metrics.items()
    ]


ROWS = _rows(
    {
        "2026-08": {"cash_balance": 900, "revenue": 1000, "payroll": 400},  # net +600
        "2026-09": {"cash_balance": 1000, "revenue": 1000, "payroll": 500, "capex": 100},  # +400
        "2026-10": {"cash_balance": 1200, "revenue": 800, "cogs": 300, "tax_reserve": 999},  # +500
    }
)


def test_expected_and_pessimistic_over_the_window() -> None:
    p = project_treasury(ROWS, date(2026, 12, 15), window=3, min_periods=3)
    assert (p.base_minor, p.months, p.mean_net_minor, p.min_net_minor) == (1200, 2, 500, 400)
    assert (p.expected_minor, p.pessimistic_minor) == (2200, 2000)  # tax_reserve is not a flow


def test_window_limits_history_and_payment_in_the_past_adds_nothing() -> None:
    p = project_treasury(ROWS, date(2026, 9, 1), window=2, min_periods=2)
    assert p.periods_used == ["2026-09", "2026-10"] and p.months == 0
    assert p.expected_minor == p.pessimistic_minor == 1200


def test_negative_mean_floors_down() -> None:
    rows = _rows(
        {
            "2026-09": {"cash_balance": 100, "payroll": 1},
            "2026-10": {"cash_balance": 100, "payroll": 2},
        }
    )
    assert project_treasury(rows, date(2026, 11, 1), window=2, min_periods=2).mean_net_minor == -2


def test_too_few_periods_refuses() -> None:
    with pytest.raises(ProjectionError):
        project_treasury(ROWS, date(2026, 12, 1), window=3, min_periods=4)
