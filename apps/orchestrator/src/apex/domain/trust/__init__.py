"""Seller confidence (D3-06, spec §3.4.2, ADR-303, ADR-304). ``@apex/scoring`` ``computeSellerConfidence`` mirrors it.

Four deterministic steps: saturated normalisation, Bayesian rating shrinkage plus the Wilson lower bound,
structural review-manipulation flags (any flag caps the band at ``low``) and a proportional dispute
penalty, then the weighted score and its band. Same snapshot + reviews + config + ``now`` gives the same
output. Statistics are IEEE doubles evaluated in the same order as the TS mirror (ADR-300 epsilon); the
score is rounded half-up and compared exactly.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from statistics import NormalDist
from typing import Any, Literal

from apex.contracts.generated.models import (
    Currency,
    NullableMoney,
    ReviewAnomaly,
    ReviewAnomalySeverity,
    ReviewAnomalyType,
    SellerConfidence,
    SellerConfidenceBand,
    SellerSignalSnapshot,
)

ENGINE_VERSION = "seller-confidence@1"
GROUPS = ("age", "sales", "catalog", "reviews", "institutional")
COUNT_SIGNALS = (
    "lifetime_transactions",
    "transactions_12m",
    "gmv_12m",
    "published_products_count",
    "reviews_total",
    "reviews_12m",
)
# The 21 raw signals of spec §3.4.1. ``seller.min_signals`` counts the present ones (ADR-303).
RAW_SIGNALS = (
    "account_age_days",
    "first_sale_date",
    "months_active_last_12",
    "lifetime_transactions",
    "transactions_12m",
    "gmv_12m",
    "repeat_buyer_share",
    "published_products_count",
    "catalog_churn_30d",
    "spec_completeness_avg",
    "reviews_total",
    "reviews_12m",
    "rating_avg",
    "rating_count",
    "verified_review_share",
    "response_rate",
    "identity_verified",
    "trade_assurance",
    "escrow_available",
    "dispute_rate",
    "refund_rate",
)
# Scored signals per group (ADR-304). An absent signal scores 0: missing data never helps.
GROUP_SIGNALS: dict[str, tuple[str, ...]] = {
    "age": ("account_age_days", "first_sale_date", "months_active_last_12"),
    "sales": ("lifetime_transactions", "transactions_12m", "gmv_12m", "repeat_buyer_share"),
    "catalog": ("published_products_count", "catalog_churn_30d", "spec_completeness_avg"),
    "reviews": (
        "rating_adjusted",
        "positive_share_wilson",
        "reviews_total",
        "reviews_12m",
        "verified_review_share",
        "response_rate",
    ),
    "institutional": ("identity_verified", "trade_assurance", "escrow_available"),
}
BUCKET_DAYS = (
    30  # review-velocity bucket (ADR-303): an algorithm definition, not a business threshold
)
BURST_BUCKETS = 12

TrustErrorCode = Literal["config_unset", "config_invalid", "gmv_not_eur"]


class TrustError(ValueError):
    def __init__(self, code: TrustErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Review:
    """One review as the adapter saw it. The engine reads structure (rating, date, verified, exact text), never meaning."""

    rating: int
    date: date
    verified: bool
    text: str = ""


@dataclass(frozen=True, slots=True)
class TrustConfig:
    """The ``seller.*`` slice of the effective tenant/category config (spec §7, ADR-304)."""

    config_version: str
    weights: Mapping[str, float]
    x_sat: Mapping[str, float]
    rating_prior_weight: float
    category_rating_mean: float
    wilson_confidence: float
    age_saturation_days: float
    min_signals: int
    band_high: int
    band_medium: int
    band_low: int
    hard_block_below: int
    review_burst_z: float
    category_five_star_share: float
    min_verified_share: float
    max_duplicate_text_share: float
    max_dispute_rate: float

    @classmethod
    def from_mapping(cls, seller: Mapping[str, Any], config_version: str) -> TrustConfig:
        """Build from the config slice. Unset (null or missing) refuses to run: no default is invented."""

        def need(key: str) -> Any:
            value = seller.get(key)
            if value is None:
                raise TrustError("config_unset", f"seller.{key} is unset")
            return value

        def num(key: str) -> float:
            try:
                return float(Decimal(str(need(key))))
            except InvalidOperation as e:
                raise TrustError("config_invalid", f"seller.{key} is not a number") from e

        def table(key: str, keys: Sequence[str]) -> dict[str, float]:
            raw = need(key)
            if not isinstance(raw, Mapping) or set(raw) != set(keys):
                raise TrustError("config_invalid", f"seller.{key} must have exactly {sorted(keys)}")
            out = {}
            for k in keys:
                if raw[k] is None:
                    raise TrustError("config_unset", f"seller.{key}.{k} is unset")
                out[k] = Decimal(str(raw[k]))
            if any(v < 0 for v in out.values()):
                raise TrustError("config_invalid", f"seller.{key} values must be non-negative")
            return {k: float(v) for k, v in out.items()} if key != "weights" else _weights(out)

        cfg = cls(
            config_version=config_version,
            weights=table("weights", GROUPS),
            x_sat=table("x_sat", COUNT_SIGNALS),
            rating_prior_weight=num("rating_prior_weight"),
            category_rating_mean=num("category_rating_mean"),
            wilson_confidence=num("wilson_confidence"),
            age_saturation_days=num("age_saturation_days"),
            min_signals=int(num("min_signals")),
            band_high=int(num("band_high")),
            band_medium=int(num("band_medium")),
            band_low=int(num("band_low")),
            hard_block_below=int(num("hard_block_below")),
            review_burst_z=num("review_burst_z"),
            category_five_star_share=num("category_five_star_share"),
            min_verified_share=num("min_verified_share"),
            max_duplicate_text_share=num("max_duplicate_text_share"),
            max_dispute_rate=num("max_dispute_rate"),
        )
        if any(v <= 0 for v in cfg.x_sat.values()) or cfg.age_saturation_days <= 0:
            raise TrustError("config_invalid", "saturation points must be positive")
        if not 0 < cfg.wilson_confidence < 1 or not 0 < cfg.category_five_star_share < 1:
            raise TrustError(
                "config_invalid", "wilson_confidence and category_five_star_share are in (0, 1)"
            )
        if not 1 <= cfg.category_rating_mean <= 5 or cfg.max_dispute_rate <= 0:
            raise TrustError(
                "config_invalid", "category_rating_mean is in [1, 5], max_dispute_rate > 0"
            )
        if not cfg.band_low <= cfg.band_medium <= cfg.band_high:
            raise TrustError(
                "config_invalid", "bands must satisfy band_low <= band_medium <= band_high"
            )
        return cfg


def _weights(w: dict[str, Decimal]) -> dict[str, float]:
    if sum(w.values()) != 1:
        raise TrustError("config_invalid", "seller.weights must sum to exactly 1")
    return {k: float(v) for k, v in w.items()}


def _log_sat(x: float, x_sat: float) -> float:
    return min(math.log10(1 + x) / math.log10(1 + x_sat), 1.0)


def _lin_sat(x: float, x_sat: float) -> float:
    return min(max(x, 0.0) / x_sat, 1.0)


def _wilson_lower(positive: int, n: int, z: float) -> float:
    p = positive / n
    z2 = z * z
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (centre - margin) / (1 + z2 / n)


def _z_vs_rest(peak: float, rest: Sequence[float]) -> float:
    """z of ``peak`` against the population mean/sd of ``rest``. sd is floored at 1 review (ADR-303)."""
    mean = sum(rest) / len(rest)
    sd = math.sqrt(sum((r - mean) * (r - mean) for r in rest) / len(rest))
    return (peak - mean) / max(sd, 1.0)


def _signal(s: SellerSignalSnapshot, name: str) -> Any:
    value = getattr(s, name)
    return value.root if isinstance(value, NullableMoney) else value


def _normalise(
    s: SellerSignalSnapshot, reviews: Sequence[Review] | None, cfg: TrustConfig
) -> dict[str, float]:
    out: dict[str, float] = {}
    captured = s.captured_at.date()
    if s.account_age_days is not None:
        out["account_age_days"] = _lin_sat(s.account_age_days, cfg.age_saturation_days)
    if s.first_sale_date is not None:
        days = (captured - s.first_sale_date).days
        out["first_sale_date"] = _lin_sat(days, cfg.age_saturation_days)
    if s.months_active_last_12 is not None:
        out["months_active_last_12"] = s.months_active_last_12 / 12
    for name in COUNT_SIGNALS:
        value = _signal(s, name)
        if value is None:
            continue
        if name == "gmv_12m":
            if value.currency != Currency.EUR:
                raise TrustError("gmv_not_eur", "gmv_12m must be converted to EUR before scoring")
            value = value.amount_minor / 100  # x_sat.gmv_12m is in EUR (ADR-304)
        out[name] = _log_sat(value, cfg.x_sat[name])
    for name in (
        "repeat_buyer_share",
        "spec_completeness_avg",
        "verified_review_share",
        "response_rate",
    ):
        value = getattr(s, name)
        if value is not None:
            out[name] = value
    if s.catalog_churn_30d is not None:
        out["catalog_churn_30d"] = 1 - s.catalog_churn_30d
    if s.rating_avg is not None:
        n = s.rating_count or 0
        c, m = cfg.rating_prior_weight, cfg.category_rating_mean
        adjusted = (c * m + s.rating_avg * n) / (c + n)
        out["rating_adjusted"] = (adjusted - 1) / 4
    if reviews:
        z = NormalDist().inv_cdf(1 - (1 - cfg.wilson_confidence) / 2)
        positive = sum(1 for r in reviews if r.rating >= 4)
        out["positive_share_wilson"] = _wilson_lower(positive, len(reviews), z)
    for name in ("identity_verified", "trade_assurance", "escrow_available"):
        value = getattr(s, name)
        if value is not None:
            out[name] = 1.0 if value else 0.0
    return out


def _anomaly(
    s: SellerSignalSnapshot, kind: ReviewAnomalyType, now: datetime, **evidence: Any
) -> ReviewAnomaly:
    # Every flag caps the band, so every flag is critical (ADR-303).
    return ReviewAnomaly(
        seller_id=s.seller_id,
        type=kind,
        severity=ReviewAnomalySeverity.critical,
        evidence=evidence,
        detected_at=now,
    )


def _flags(
    s: SellerSignalSnapshot, reviews: Sequence[Review] | None, cfg: TrustConfig, now: datetime
) -> list[ReviewAnomaly]:
    flags: list[ReviewAnomaly] = []
    if s.verified_review_share is not None and s.verified_review_share < cfg.min_verified_share:
        flags.append(
            _anomaly(
                s,
                ReviewAnomalyType.low_verified_share,
                now,
                verified_review_share=s.verified_review_share,
                threshold=cfg.min_verified_share,
            )
        )
    if not reviews:
        return flags
    captured = s.captured_at.date()
    ages = [(captured - r.date).days for r in reviews]

    buckets = [0.0] * BURST_BUCKETS
    for age in ages:
        if 0 <= age < BUCKET_DAYS * BURST_BUCKETS:
            buckets[age // BUCKET_DAYS] += 1
    peak = max(buckets)
    rest = list(buckets)
    rest.remove(peak)
    z = _z_vs_rest(peak, rest)
    if z > cfg.review_burst_z:
        flags.append(
            _anomaly(s, ReviewAnomalyType.burst_velocity, now, peak_bucket_reviews=peak, z=z)
        )

    n = len(reviews)
    p0 = cfg.category_five_star_share
    five = sum(1 for r in reviews if r.rating == 5)
    z = (five / n - p0) / math.sqrt(p0 * (1 - p0) / n)
    if z > cfg.review_burst_z:
        flags.append(
            _anomaly(s, ReviewAnomalyType.five_star_anomaly, now, five_star_share=five / n, z=z)
        )

    texts = [" ".join(r.text.lower().split()) for r in reviews]
    texts = [t for t in texts if t]
    if texts:
        counts = Counter(texts)
        share = sum(1 for t in texts if counts[t] > 1) / len(texts)
        if share > cfg.max_duplicate_text_share:
            flags.append(_anomaly(s, ReviewAnomalyType.duplicate_text, now, duplicate_share=share))

    if s.account_age_days is not None and s.account_age_days // BUCKET_DAYS >= 3:
        created = captured - timedelta(days=s.account_age_days)
        life = [0.0] * (s.account_age_days // BUCKET_DAYS)
        for r in reviews:
            k = (r.date - created).days // BUCKET_DAYS
            if 0 <= k < len(life):
                life[k] += 1
        z = _z_vs_rest(life[0], life[1:])
        if z > cfg.review_burst_z:
            flags.append(
                _anomaly(
                    s,
                    ReviewAnomalyType.creation_correlation,
                    now,
                    first_bucket_reviews=life[0],
                    z=z,
                )
            )
    return flags


def _band(score: int, cfg: TrustConfig) -> SellerConfidenceBand:
    if score < cfg.band_low or score < cfg.hard_block_below:
        return SellerConfidenceBand.untrusted
    if score >= cfg.band_high:
        return SellerConfidenceBand.high
    if score >= cfg.band_medium:
        return SellerConfidenceBand.medium
    return SellerConfidenceBand.low


def compute(
    snapshot: SellerSignalSnapshot,
    cfg: TrustConfig,
    *,
    now: datetime,
    reviews: Sequence[Review] | None = None,
) -> SellerConfidence:
    """Seller confidence from one immutable snapshot (spec §3.4.2). ``now`` only stamps ``computed_at``."""
    model_version = f"{ENGINE_VERSION}/{cfg.config_version}"
    present = sum(1 for name in RAW_SIGNALS if _signal(snapshot, name) is not None)
    if present < cfg.min_signals:
        return SellerConfidence(
            seller_id=snapshot.seller_id,
            score=None,
            band=SellerConfidenceBand.insufficient_data,
            signals_normalized={},
            penalties=[],
            flags=[],
            model_version=model_version,
            snapshot_id=snapshot.id,
            computed_at=now,
        )

    normalized = _normalise(snapshot, reviews, cfg)
    total = 0.0
    for group in GROUPS:
        signals = GROUP_SIGNALS[group]
        total += cfg.weights[group] * (sum(normalized.get(n, 0.0) for n in signals) / len(signals))

    penalties = [] if reviews else ["reviews_unavailable"]
    worst = 0.0
    for name in ("dispute_rate", "refund_rate"):
        rate = getattr(snapshot, name)
        if rate is not None and rate > cfg.max_dispute_rate:
            penalties.append(f"{name}_above_max")
            worst = max(worst, rate)
    if worst:
        total *= cfg.max_dispute_rate / worst  # proportional penalty (ADR-304)

    score = math.floor(100 * total + 0.5)
    band = _band(score, cfg)
    flags = _flags(snapshot, reviews, cfg, now)
    if flags and band in (SellerConfidenceBand.high, SellerConfidenceBand.medium):
        band = SellerConfidenceBand.low
    return SellerConfidence(
        seller_id=snapshot.seller_id,
        score=score,
        band=band,
        signals_normalized=normalized,
        penalties=penalties,
        flags=flags,
        model_version=model_version,
        snapshot_id=snapshot.id,
        computed_at=now,
    )
