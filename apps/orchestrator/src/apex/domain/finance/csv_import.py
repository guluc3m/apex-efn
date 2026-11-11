"""Financial CSV importer (D3-04, spec 3.1.1, criteria 2 and 24).

Pure and deterministic: bytes + rates + clock in, ``ImportResult`` out. It never activates anything and
never calls an LLM. Row problems reject that row only; only a file that cannot be read at all raises.
"""

from __future__ import annotations

import calendar
import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from apex.contracts.generated.models import (
    ConvertedMoney,
    Currency,
    DerivedFinancials,
    FxRate,
    ImportReport,
    RowRejection,
    RowRejectionReason,
)
from apex.contracts.generated.models import Money as MoneyDto
from apex.domain.fx import FxConfig, FxError, convert
from apex.domain.money import Money

METRICS = frozenset(
    [
        "cash_balance",
        "credit_line_available",
        "credit_line_limit",
        "accounts_receivable",
        "accounts_payable",
        "revenue",
        "cogs",
        "fixed_costs",
        "payroll",
        "debt_service",
        "capex",
        "tax_reserve",
        "safety_buffer_pct",
        "payment_term_days",
    ]
)
BP_METRICS = frozenset({"safety_buffer_pct"})  # value_bp
COUNT_METRICS = frozenset({"payment_term_days"})  # plain integer in value_minor, no currency
MIN_PROJECTION_PERIODS = 3
MAX_NOTES = 500
_PERIOD = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
_INT = re.compile(r"-?\d+")
Reason = RowRejectionReason


class CsvImportError(ValueError):
    """The file as a whole cannot be read (not UTF-8, no header, missing columns)."""


@dataclass(frozen=True, slots=True)
class ImportRow:
    row: int
    period: str
    metric: str
    amount: ConvertedMoney | None = None  # money metrics, in the base currency
    value_bp: int | None = None
    value_int: int | None = None  # payment_term_days
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ImportResult:
    report: ImportReport
    rows: list[ImportRow]
    derived: DerivedFinancials
    rows_duplicated: int
    rows_converted: int
    fx_provisional: bool
    warning_codes: list[str] = field(default_factory=list)
    """Deterministic codes (``projection_disabled``, ``fx_provisional``...) the LLM words for the user."""


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError("the file is not UTF-8") from exc


def _delimiter(header: str) -> str:
    return max(",;\t", key=header.count)


def _close(period: str, now: datetime) -> datetime:
    """End of the closing month (UTC), capped at ``now``: the date whose FX applies to that period."""
    year, month = int(period[:4]), int(period[5:])
    end = datetime(year, month, calendar.monthrange(year, month)[1], 23, 59, 59, tzinfo=UTC)
    return min(end, now)


def _month_end(period: str) -> date:
    year, month = int(period[:4]), int(period[5:])
    return date(year, month, calendar.monthrange(year, month)[1])


def parse(
    content: bytes,
    base_currency: Currency | str,
    rates: Iterable[FxRate],
    now: datetime,
    cfg: FxConfig,
) -> ImportResult:
    base = Money.zero(base_currency).currency
    rate_list = list(rates)
    text = _decode(content)
    if not text.strip():
        raise CsvImportError("the file is empty")
    reader = csv.DictReader(io.StringIO(text), delimiter=_delimiter(text.splitlines()[0]))
    fields = [(f or "").strip().lower() for f in reader.fieldnames or []]
    reader.fieldnames = fields
    missing = {"period", "metric"} - set(fields)
    if missing or not {"value_minor", "value_bp"} & set(fields):
        raise CsvImportError(f"missing columns: {sorted(missing) or 'value_minor/value_bp'}")

    rows: list[ImportRow] = []
    rejections: list[RowRejection] = []
    seen: set[tuple[str, str]] = set()
    duplicated = 0
    for n, raw in enumerate(reader, start=1):
        cells = {k: (v or "").strip() for k, v in raw.items() if k}

        def reject(reason: Reason, message: str, column: str | None = None, n: int = n) -> None:
            rejections.append(
                RowRejection(row=n, field=column, reason_code=reason, message=message)
            )

        period, metric = cells.get("period", ""), cells.get("metric", "")
        if not period or not metric:
            reject(Reason.missing_required_field, "period and metric are required")
            continue
        if metric not in METRICS:
            reject(Reason.unknown_metric, f"unknown metric {metric!r}", "metric")
            continue
        if not _PERIOD.fullmatch(period):
            reject(Reason.malformed_period, f"period must be YYYY-MM, got {period!r}", "period")
            continue
        notes = cells.get("notes", "")
        if len(notes) > MAX_NOTES:
            reject(Reason.note_too_long, f"notes exceed {MAX_NOTES} characters", "notes")
            continue
        minor, bp, cur = (
            cells.get("value_minor", ""),
            cells.get("value_bp", ""),
            cells.get("currency", ""),
        )

        if metric in BP_METRICS:
            if not bp:
                reject(Reason.missing_required_field, f"{metric} needs value_bp", "value_bp")
                continue
            if not _INT.fullmatch(bp):
                reject(Reason.non_integer_amount, "value_bp must be an integer", "value_bp")
                continue
            row = ImportRow(n, period, metric, value_bp=int(bp), notes=notes)
        elif metric in COUNT_METRICS:
            if not _INT.fullmatch(minor):
                reject(
                    Reason.non_integer_amount,
                    f"{metric} needs an integer value_minor",
                    "value_minor",
                )
                continue
            row = ImportRow(n, period, metric, value_int=int(minor), notes=notes)
        else:
            if not minor:
                reject(Reason.missing_required_field, f"{metric} needs value_minor", "value_minor")
                continue
            if not _INT.fullmatch(minor):
                reject(
                    Reason.non_integer_amount,
                    "value_minor must be an integer, no decimals",
                    "value_minor",
                )
                continue
            if not cur:
                reject(
                    Reason.missing_required_field,
                    "currency is required with value_minor",
                    "currency",
                )
                continue
            if cur not in Currency.__members__:
                reject(
                    Reason.unsupported_currency,
                    f"currency must be EUR, USD or CNY, got {cur!r}",
                    "currency",
                )
                continue
            try:
                money = Money(int(minor), Currency(cur))
            except ValueError as exc:
                reject(Reason.non_integer_amount, str(exc), "value_minor")
                continue
            try:
                amount = convert(money, base, rate_list, _close(period, now), cfg)
            except FxError as exc:
                reject(Reason.unsupported_currency, str(exc), "currency")
                continue
            row = ImportRow(n, period, metric, amount=amount, notes=notes)

        if (period, metric) in seen:
            duplicated += 1
            reject(Reason.duplicate_period_metric, f"{metric} already given for {period}")
            continue
        seen.add((period, metric))
        rows.append(row)

    return _result(rows, rejections, duplicated, base, now)


def _result(
    rows: list[ImportRow],
    rejections: list[RowRejection],
    duplicated: int,
    base: Currency,
    now: datetime,
) -> ImportResult:
    cash_periods = sorted(r.period for r in rows if r.metric == "cash_balance")
    projection = len(cash_periods) >= MIN_PROJECTION_PERIODS
    latest = cash_periods[-1] if cash_periods else None
    converted = [r for r in rows if r.amount and r.amount.converted]
    provisional = any(r.amount and r.amount.fx_provisional for r in rows)

    codes: list[str] = []
    if not cash_periods:
        codes.append("cash_balance_missing")
    if not projection:
        codes.append("projection_disabled")
    if provisional:
        codes.append("fx_provisional")
    if rejections:
        codes.append("rows_rejected")

    def at_ref(metric: str) -> int:
        return next(
            (
                r.amount.amount_minor
                for r in rows
                if r.period == latest and r.metric == metric and r.amount
            ),
            0,
        )

    def bp_at_ref(metric: str) -> int:
        return next(
            (
                r.value_bp
                for r in rows
                if r.period == latest and r.metric == metric and r.value_bp is not None
            ),
            0,
        )

    # ponytail: ADR-305 proposal, TL approves. cash + available credit - tax reserve - safety buffer (% of cash).
    capacity = 0
    if latest:
        cash = at_ref("cash_balance")
        capacity = (
            cash
            + at_ref("credit_line_available")
            - at_ref("tax_reserve")
            - cash * bp_at_ref("safety_buffer_pct") // 10_000
        )

    derived = DerivedFinancials(
        envelopes=[],  # Q2: envelopes come from budget rows and the closed metric enum has none
        net_buying_capacity=MoneyDto(amount_minor=capacity, currency=base),
        buying_power_score=None,  # informational, formula pending TL approval (Q2)
    )
    report = ImportReport(
        rows_ok=len(rows),
        rows_rejected=len(rejections),
        rejections=rejections,
        warnings=[],  # worded by the LLM from warning_codes, never here
        projection_enabled=projection,
        periods_loaded=len(cash_periods),
        reference_date=_month_end(latest) if latest else now.date(),
        derived=derived,
    )
    return ImportResult(report, rows, derived, duplicated, len(converted), provisional, codes)
