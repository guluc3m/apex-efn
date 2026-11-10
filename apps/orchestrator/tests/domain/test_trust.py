"""Seller confidence (D3-06): spec §9 criteria 6–9 stated explicitly, plus properties. Vectors: test_vectors.py."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from apex.contracts.generated.models import SellerConfidenceBand, SellerSignalSnapshot
from apex.domain.trust import RAW_SIGNALS, Review, TrustConfig, compute
from tests.domain.vectors import ROOT

FILE = json.loads((ROOT / "trust" / "compute.json").read_text(encoding="utf-8"))
CASES = {v["name"]: v for v in FILE["vectors"]}
CONFIG = next(iter(CASES.values()))["config"]
CFG = TrustConfig.from_mapping(
    {k: v for k, v in CONFIG.items() if k != "config_version"}, CONFIG["config_version"]
)
NOW = datetime(2026, 11, 10, tzinfo=UTC)


def _run(name: str) -> Any:
    case = CASES[name]["input"]
    reviews = case.get("reviews")
    return compute(
        SellerSignalSnapshot.model_validate(case["snapshot"]),
        CFG,
        now=NOW,
        reviews=None
        if reviews is None
        else [
            Review(r["rating"], date.fromisoformat(r["date"]), r["verified"], r["text"])
            for r in reviews
        ],
    )


def test_criterion_6_reproducible_with_signals_and_version() -> None:
    a, b = _run("solid_veteran_500_reviews_4_8"), _run("solid_veteran_500_reviews_4_8")
    assert a == b
    assert a.score is not None and a.signals_normalized
    assert a.model_version == f"seller-confidence@1/{CONFIG['config_version']}"


def test_criterion_7_one_perfect_review_does_not_beat_500_at_4_8() -> None:
    single, solid = _run("single_perfect_review_5_0"), _run("solid_veteran_500_reviews_4_8")
    assert (
        single.signals_normalized["rating_adjusted"] < solid.signals_normalized["rating_adjusted"]
    )
    assert single.score is not None and solid.score is not None and single.score < solid.score


def test_criterion_8_burst_caps_band_at_low() -> None:
    steady, burst = _run("solid_with_steady_reviews_no_flag"), _run("review_burst_caps_band_at_low")
    assert steady.band == SellerConfidenceBand.high and not steady.flags
    assert burst.score is not None and burst.score >= CFG.band_high  # excellent otherwise
    assert burst.band == SellerConfidenceBand.low
    assert [f.type.value for f in burst.flags] == ["burst_velocity"]


def test_criterion_9_insufficient_data() -> None:
    result = _run("insufficient_data_two_signals")
    assert result.band == SellerConfidenceBand.insufficient_data and result.score is None


def test_untrusted_below_band_low_not_low() -> None:
    result = _run("score_between_20_and_25_is_untrusted")
    assert result.score is not None and CFG.hard_block_below <= result.score < CFG.band_low
    assert result.band == SellerConfidenceBand.untrusted


_share = st.one_of(st.none(), st.floats(0, 1))
_count = st.one_of(st.none(), st.integers(0, 10**6))
_flag = st.one_of(st.none(), st.booleans())
_snapshots = st.fixed_dictionaries(
    {
        "account_age_days": _count,
        "months_active_last_12": st.one_of(st.none(), st.integers(0, 12)),
        "lifetime_transactions": _count,
        "transactions_12m": _count,
        "repeat_buyer_share": _share,
        "published_products_count": _count,
        "catalog_churn_30d": _share,
        "spec_completeness_avg": _share,
        "reviews_total": _count,
        "reviews_12m": _count,
        "rating_avg": st.one_of(st.none(), st.floats(1, 5)),
        "rating_count": _count,
        "verified_review_share": _share,
        "response_rate": _share,
        "identity_verified": _flag,
        "trade_assurance": _flag,
        "escrow_available": _flag,
        "dispute_rate": _share,
        "refund_rate": _share,
    }
)


def _snap(fields: dict[str, Any]) -> SellerSignalSnapshot:
    return SellerSignalSnapshot(
        id="s", seller_id="x", data_completeness=0, captured_at=NOW, **fields
    )


@given(_snapshots)
def test_score_and_band_are_consistent(fields: dict[str, Any]) -> None:
    result = compute(_snap(fields), CFG, now=NOW)
    present = sum(1 for n in RAW_SIGNALS if fields.get(n) is not None)
    if present < CFG.min_signals:
        assert result.band == SellerConfidenceBand.insufficient_data and result.score is None
        return
    assert result.score is not None and 0 <= result.score <= 100
    assert all(0 <= v <= 1 for v in result.signals_normalized.values())
    if result.flags:
        assert result.band in (SellerConfidenceBand.low, SellerConfidenceBand.untrusted)
    if result.score < CFG.band_low:
        assert result.band == SellerConfidenceBand.untrusted


@given(_snapshots, st.sampled_from(["identity_verified", "trade_assurance", "escrow_available"]))
def test_an_institutional_guarantee_never_lowers_the_score(
    fields: dict[str, Any], key: str
) -> None:
    without = compute(_snap({**fields, key: False}), CFG, now=NOW)
    with_it = compute(_snap({**fields, key: True}), CFG, now=NOW)
    if without.score is not None:
        assert with_it.score is not None and with_it.score >= without.score


@given(st.floats(1, 5), st.integers(0, 10**5))
def test_shrinkage_stays_between_prior_and_observed(rating: float, n: int) -> None:
    adjusted = (
        compute(
            _snap(
                {"rating_avg": rating, "rating_count": n, "account_age_days": 1, "reviews_total": 1}
            ),
            CFG,
            now=NOW,
        ).signals_normalized["rating_adjusted"]
        * 4
        + 1
    )
    lo, hi = sorted((rating, CFG.category_rating_mean))
    assert lo - 1e-9 <= adjusted <= hi + 1e-9
