"""Recommendation export (issue #379): CSV, JSON and PDF built from the recommendation numbers only.

Nothing is computed here: every figure comes from the ``Recommendation`` the MCDA engine produced. The PDF reuses
the deterministic text writer in ``apex.documents.pdf`` (Latin-1 only).
"""

from __future__ import annotations

import csv
import io
from typing import Literal, Protocol

from apex.contracts.generated.models import NullableMoney, Recommendation
from apex.documents.pdf import text_pdf

ExportFormat = Literal["pdf", "csv", "json"]

MEDIA_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
}


class RecommendationProvider(Protocol):
    """Builds the recommendation of a mission for a profile. Raises ``LookupError`` when the mission is unknown."""

    async def recommendation(
        self, *, tenant_id: str, mission_id: str, profile_id: str
    ) -> Recommendation: ...


def _money(value: NullableMoney | None) -> str:
    money = value.root if value is not None else None
    return "" if money is None else f"{money.amount_minor} {money.currency.value}"


def to_csv(rec: Recommendation) -> bytes:
    """One row per ranked offer and criterion, so the contributions stay readable in a spreadsheet."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(
        [
            "rank",
            "offer_id",
            "score",
            "criterion",
            "weight",
            "normalized_value",
            "contribution",
            "penalty",
        ]
    )
    for item in rec.ranking:
        for b in item.breakdown:
            w.writerow(
                [
                    item.rank,
                    item.offer_id,
                    item.score,
                    b.criterion.value,
                    b.weight,
                    b.normalized_value,
                    b.contribution,
                    b.penalty if b.penalty is not None else "",
                ]
            )
    return out.getvalue().encode("utf-8")


def to_pdf(rec: Recommendation) -> bytes:
    lines = [
        f"Mission {rec.mission_id} - profile {rec.profile_id}",
        f"config_version {rec.config_version} - model_version {rec.model_version}",
        f"generated_at {rec.generated_at.isoformat()}",
        "",
        "Ranking",
    ]
    for item in rec.ranking:
        lines.append(f"{item.rank}. {item.offer_id} - score {item.score}")
        lines += [
            f"    {b.criterion.value}: weight {b.weight}, value {b.normalized_value}, contribution {b.contribution}"
            for b in item.breakdown
        ]
    if rec.excluded:
        lines += ["", "Excluded by hard constraints"]
        lines += [f"{e.offer_id}: {', '.join(e.reasons)}" for e in rec.excluded]
    if rec.alternatives:
        lines += ["", "Trade-offs"]
        lines += [f"{a.offer_id} vs {a.versus_offer_id}: {a.summary}" for a in rec.alternatives]
    s = rec.savings
    lines += [
        "",
        "Savings (minor units)",
        f"vs list price: {_money(s.vs_list_price)}",
        f"vs market median: {_money(s.vs_market_median)}",
    ]
    return text_pdf(f"Recommendation {rec.mission_id}", lines)


def render(rec: Recommendation, fmt: ExportFormat) -> bytes:
    if fmt == "csv":
        return to_csv(rec)
    if fmt == "pdf":
        return to_pdf(rec)
    return rec.model_dump_json(exclude_none=True).encode("utf-8")
