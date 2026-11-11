"""D3-10: offline calibration proposes weights, never applies them (ADR-306)."""

from __future__ import annotations

from datetime import UTC, datetime

from apex.contracts.generated.models import SellerSignalSnapshot
from apex.domain.trust import TrustConfig
from apex.domain.trust.calibration import LabeledSeller, evaluate, propose_weights
from tests.domain.test_trust import CASES, CFG

NOW = datetime(2026, 11, 10, tzinfo=UTC)


def _snap(name: str) -> SellerSignalSnapshot:
    return SellerSignalSnapshot.model_validate(CASES[name]["input"]["snapshot"])


def _samples() -> list[LabeledSeller]:
    good = ["solid_veteran_500_reviews_4_8", "solid_with_steady_reviews_no_flag"]
    bad = ["single_perfect_review_5_0", "low_verified_share", "duplicate_texts"]
    return [LabeledSeller(_snap(n), False) for n in good] + [
        LabeledSeller(_snap(n), True) for n in bad
    ]


def test_evaluate_is_reproducible_and_reports_auc() -> None:
    a, b = evaluate(_samples(), CFG, NOW), evaluate(_samples(), CFG, NOW)
    assert a == b and a.n_bad == 3 and a.auc is not None and 0 <= a.auc <= 1


def test_insufficient_labels_proposes_nothing() -> None:
    p = propose_weights(_samples(), CFG, NOW, step_pct=25, min_bad=10, min_good=10)
    assert p.status == "insufficient_labels" and p.weights is None


def test_proposal_is_deterministic_valid_and_never_worse() -> None:
    kw = {"step_pct": 25, "min_bad": 1, "min_good": 1}
    a, b = propose_weights(_samples(), CFG, NOW, **kw), propose_weights(_samples(), CFG, NOW, **kw)
    assert a == b
    if a.status == "proposed":
        assert a.weights is not None and a.proposed is not None and a.current.auc is not None
        assert abs(sum(a.weights.values()) - 1) < 1e-9
        assert a.weights["institutional"] == max(a.weights.values())
        assert (a.proposed.auc or 0) > a.current.auc
    else:
        assert a.status == "no_improvement"
    assert isinstance(CFG, TrustConfig)  # the input config is never mutated
