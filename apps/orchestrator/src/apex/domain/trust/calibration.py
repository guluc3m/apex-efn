"""Offline per-category calibration of the seller-confidence weights (D3-10, ADR-306).

Pure and deterministic: no randomness, ``now`` injected. It only *proposes*; applying a proposal is a signed
config decision (spec §3.4.3), never done here. Thresholds and bands are not touched.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from apex.contracts.generated.models import SellerSignalSnapshot
from apex.domain.trust import GROUPS, Review, TrustConfig, compute


@dataclass(frozen=True, slots=True)
class LabeledSeller:
    snapshot: SellerSignalSnapshot
    bad: bool
    """Real outcome: fraud, dispute loss or non-delivery."""
    reviews: Sequence[Review] | None = None


@dataclass(frozen=True, slots=True)
class Evaluation:
    n_scored: int
    n_bad: int
    auc: float | None
    """P(a good seller outscores a bad one), ties count 1/2. ``None`` without both classes."""
    bad_rate_by_band: dict[str, float]


@dataclass(frozen=True, slots=True)
class Proposal:
    status: str  # "proposed" | "insufficient_labels" | "no_improvement"
    current: Evaluation
    weights: dict[str, float] | None = None
    proposed: Evaluation | None = None


def _scores(
    samples: Sequence[LabeledSeller], cfg: TrustConfig, now: datetime
) -> Iterator[tuple[bool, int, str]]:
    for s in samples:
        c = compute(s.snapshot, cfg, now=now, reviews=s.reviews)
        if c.score is not None:  # insufficient_data sellers carry no score to calibrate
            yield s.bad, c.score, c.band.value


def evaluate(samples: Sequence[LabeledSeller], cfg: TrustConfig, now: datetime) -> Evaluation:
    scored = list(_scores(samples, cfg, now))
    bad = [sc for b, sc, _ in scored if b]
    good = [sc for b, sc, _ in scored if not b]
    auc = None
    if bad and good:
        wins = sum((g > b) + 0.5 * (g == b) for g in good for b in bad)
        auc = wins / (len(good) * len(bad))
    by_band: dict[str, list[bool]] = {}
    for b, _, band in scored:
        by_band.setdefault(band, []).append(b)
    return Evaluation(
        len(scored), len(bad), auc, {k: sum(v) / len(v) for k, v in sorted(by_band.items())}
    )


def _simplex(step_pct: int) -> Iterator[dict[str, float]]:
    """Every weight vector over GROUPS in multiples of ``step_pct`` percent that sums to 100."""

    def rec(i: int, left: int) -> Iterator[list[int]]:
        if i == len(GROUPS) - 1:
            yield [left]
            return
        for v in range(0, left + 1, step_pct):
            for rest in rec(i + 1, left - v):
                yield [v, *rest]

    for combo in rec(0, 100):
        if 100 % step_pct == 0 and sum(combo) == 100:
            yield {g: v / 100 for g, v in zip(GROUPS, combo, strict=True)}


def propose_weights(
    samples: Sequence[LabeledSeller],
    cfg: TrustConfig,
    now: datetime,
    *,
    step_pct: int,
    min_bad: int,
    min_good: int,
) -> Proposal:
    """Grid search the weights maximising AUC. ADR-304 keeps ``institutional`` the heaviest group.

    Ties resolve to the first candidate in enumeration order, so the result is reproducible.
    """
    current = evaluate(samples, cfg, now)
    n_good = current.n_scored - current.n_bad
    if current.n_bad < min_bad or n_good < min_good:
        return Proposal("insufficient_labels", current)
    best_auc, best_w = current.auc or 0.0, None
    for w in _simplex(step_pct):
        if w["institutional"] < max(w.values()):
            continue
        auc = evaluate(samples, replace(cfg, weights=w), now).auc or 0.0
        if auc > best_auc:
            best_auc, best_w = auc, w
    if best_w is None:
        return Proposal("no_improvement", current)
    return Proposal(
        "proposed", current, best_w, evaluate(samples, replace(cfg, weights=best_w), now)
    )
