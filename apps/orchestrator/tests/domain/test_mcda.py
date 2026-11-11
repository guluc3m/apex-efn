"""MCDA scoring and ranking (D3-09, spec §3.7).

The invariants the spec names are the tests: hard constraints filter instead of penalising, `w3` uses the
seller confidence score, an out-of-budget offer is never #1 (criterion 15), a low seller is never #1
(criterion 11), and switching profile reorders deterministically with an explanation (criterion 27).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apex.contracts.generated.models import (
    FinancialVerdict,
    ScoreCriterion,
    SellerConfidenceBand,
)
from apex.domain.mcda import (
    Candidate,
    Constraints,
    McdaError,
    Profile,
    exclude,
    rank,
    recommendation,
    to_ranked_offers,
    trade_offs,
)

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)

WEIGHTS = {
    ScoreCriterion.landed_cost: 0.30,
    ScoreCriterion.lead_time: 0.15,
    ScoreCriterion.seller_confidence: 0.25,
    ScoreCriterion.financial_fit: 0.15,
    ScoreCriterion.spec_match: 0.15,
}
PROFILE = Profile(profile_id="balanced", weights=WEIGHTS)


def _candidate(offer_id: str, **kw) -> Candidate:
    base = {
        "offer_id": offer_id,
        "landed_unit_cost_minor": 500,
        "lead_time_days": 10,
        "seller_confidence_score": 80,
        "seller_band": SellerConfidenceBand.high,
        "financial_verdict": FinancialVerdict.within_budget,
        "spec_match": 0.9,
    }
    return Candidate(**{**base, **kw})


# ----- hard constraints filter, never penalise ---------------------------------------------------


@pytest.mark.parametrize(
    ("candidate", "constraints", "fragment"),
    [
        (_candidate("a", platform="bad"), Constraints(banned_platforms=["bad"]), "banned"),
        (_candidate("a", country="XX"), Constraints(banned_countries=["XX"]), "banned"),
        (_candidate("a", certifications=()), Constraints(required_certifications=["CE"]), "CE"),
        (
            _candidate("a", seller_band=SellerConfidenceBand.low),
            Constraints(min_accepted_seller_band=SellerConfidenceBand.medium),
            "below the accepted",
        ),
        (
            _candidate("a", lead_time_days=40),
            Constraints(max_lead_time_days=20),
            "exceeds the accepted",
        ),
        (
            _candidate("a", financial_verdict=FinancialVerdict.out_of_budget),
            Constraints(),
            "out_of_budget",
        ),
    ],
)
def test_a_failed_hard_constraint_excludes_the_offer_with_a_visible_reason(
    candidate, constraints, fragment
) -> None:
    reasons = exclude(candidate, constraints)
    assert reasons and fragment in reasons[0]


def test_an_offer_passing_every_constraint_competes() -> None:
    assert (
        exclude(_candidate("a", certifications=["CE"]), Constraints(required_certifications=["CE"]))
        == []
    )


def test_an_excluded_offer_never_appears_in_the_ranking() -> None:
    ranked, excluded = rank(
        [_candidate("good"), _candidate("bad", country="XX")],
        PROFILE,
        Constraints(banned_countries=["XX"]),
    )
    assert [r.offer_id for r in ranked] == ["good"]
    assert [e.offer_id for e in excluded] == ["bad"]


# ----- the score is explainable ------------------------------------------------------------------


def test_the_breakdown_covers_every_weighted_criterion() -> None:
    ranked, _ = rank(
        [_candidate("a"), _candidate("b", landed_unit_cost_minor=600)], PROFILE, Constraints()
    )
    criteria = {b.criterion for b in ranked[0].breakdown}
    assert criteria == set(WEIGHTS)
    assert sum(b.contribution for b in ranked[0].breakdown) == pytest.approx(ranked[0].score)


def test_a_cheaper_offer_scores_higher_on_cost_all_else_equal() -> None:
    ranked, _ = rank(
        [
            _candidate("cheap", landed_unit_cost_minor=400),
            _candidate("dear", landed_unit_cost_minor=600),
        ],
        PROFILE,
        Constraints(),
    )
    assert ranked[0].offer_id == "cheap"


def test_the_seller_confidence_criterion_uses_the_engine_score() -> None:
    """`w3` uses the confidence score from §3.4, not a free field (spec §3.7)."""
    ranked, _ = rank(
        [
            _candidate("strong", seller_confidence_score=95),
            _candidate("weak", seller_confidence_score=40),
        ],
        PROFILE,
        Constraints(),
    )
    assert ranked[0].offer_id == "strong"
    strong = ranked[0].breakdown
    confidence = next(b for b in strong if b.criterion is ScoreCriterion.seller_confidence)
    assert confidence.normalized_value == pytest.approx(1.0)


def test_an_unknown_criterion_contributes_nothing_instead_of_a_neutral_half() -> None:
    """The scaffold used a neutral 0.5; the spec rejects inventing a value."""
    ranked, _ = rank(
        [_candidate("a", lead_time_days=None), _candidate("b", lead_time_days=20)],
        PROFILE,
        Constraints(),
    )
    a = next(r for r in ranked if r.offer_id == "a")
    lead = next(b for b in a.breakdown if b.criterion is ScoreCriterion.lead_time)
    assert lead.contribution == 0.0
    assert lead.weight > 0  # the weight is still visible, so the dashboard can say "unknown"


# ----- the invariants the spec names -------------------------------------------------------------


def test_an_out_of_budget_offer_is_never_first() -> None:
    """Criterion 15: it is excluded by the pre-filter, so it cannot rank at all."""
    ranked, excluded = rank(
        [
            _candidate(
                "cheap",
                landed_unit_cost_minor=100,
                financial_verdict=FinancialVerdict.out_of_budget,
            ),
            _candidate("fine", landed_unit_cost_minor=600),
        ],
        PROFILE,
        Constraints(),
    )
    assert [r.offer_id for r in ranked] == ["fine"]
    assert [e.offer_id for e in excluded] == ["cheap"]


def test_a_low_confidence_seller_is_never_first() -> None:
    """Criterion 11: with the default profile it is excluded; with a permissive one it still loses on w3."""
    ranked, excluded = rank(
        [
            _candidate("low", seller_band=SellerConfidenceBand.low, seller_confidence_score=10),
            _candidate("high", seller_confidence_score=90),
        ],
        PROFILE,
        Constraints(min_accepted_seller_band=SellerConfidenceBand.medium),
    )
    assert [r.offer_id for r in ranked] == ["high"]
    assert [e.offer_id for e in excluded] == ["low"]


def test_switching_profile_reorders_deterministically() -> None:
    """Criterion 27: a different profile reorders, and the same profile always gives the same order."""
    candidates = [
        _candidate("fast", landed_unit_cost_minor=700, lead_time_days=2),
        _candidate("cheap", landed_unit_cost_minor=400, lead_time_days=30),
    ]
    cost_profile = Profile("cost", {ScoreCriterion.landed_cost: 1.0})
    speed_profile = Profile("speed", {ScoreCriterion.lead_time: 1.0})
    cost_order = [r.offer_id for r in rank(candidates, cost_profile, Constraints())[0]]
    speed_order = [r.offer_id for r in rank(candidates, speed_profile, Constraints())[0]]
    assert cost_order == ["cheap", "fast"]
    assert speed_order == ["fast", "cheap"]
    assert [r.offer_id for r in rank(candidates, cost_profile, Constraints())[0]] == cost_order


def test_a_tie_breaks_on_the_offer_id_so_the_order_is_stable() -> None:
    ranked, _ = rank([_candidate("b"), _candidate("a")], PROFILE, Constraints())
    assert [r.offer_id for r in ranked] == ["a", "b"]


# ----- weights -----------------------------------------------------------------------------------


def test_weights_are_normalised_to_sum_to_one() -> None:
    profile = Profile("p", {ScoreCriterion.landed_cost: 2.0, ScoreCriterion.lead_time: 2.0})
    assert profile.normalised() == {
        ScoreCriterion.landed_cost: 0.5,
        ScoreCriterion.lead_time: 0.5,
    }


def test_negative_weights_are_refused() -> None:
    with pytest.raises(McdaError) as caught:
        Profile("p", {ScoreCriterion.landed_cost: -1.0}).normalised()
    assert caught.value.code == "invalid_weights"


def test_all_zero_weights_are_refused() -> None:
    with pytest.raises(McdaError):
        Profile("p", {ScoreCriterion.landed_cost: 0.0}).normalised()


# ----- the recommendation ------------------------------------------------------------------------


def _recommendation(candidates, profile=PROFILE):
    ranked, excluded = rank(candidates, profile, Constraints())
    return recommendation(
        mission_id="m-1",
        profile_id=profile.profile_id,
        ranked=ranked,
        excluded=excluded,
        candidates=candidates,
        config_version="v7",
        now=NOW,
    )


def test_the_recommendation_carries_the_ranking_and_the_exclusions() -> None:
    rec = _recommendation([_candidate("a"), _candidate("b", country="XX")])
    assert rec.ranking[0].rank == 1
    assert rec.ranking[0].narrative is None  # the LLM narrates, it never ranks
    assert rec.model_version.startswith("mcda@1/")
    assert rec.generated_at == NOW


def test_savings_against_the_list_price_are_computed_not_estimated() -> None:
    rec = _recommendation([_candidate("a", landed_unit_cost_minor=400, list_price_minor=500)])
    assert rec.savings.vs_list_price is not None
    assert rec.savings.vs_list_price.root is not None
    assert rec.savings.vs_list_price.root.amount_minor == 100


def test_no_savings_when_the_landed_cost_is_above_the_list_price() -> None:
    rec = _recommendation([_candidate("a", landed_unit_cost_minor=600, list_price_minor=500)])
    assert rec.savings.vs_list_price is None


def test_trade_offs_explain_why_a_runner_up_is_interesting() -> None:
    """The summary describes the runner-up *relative to the winner*, from the numbers that differ."""
    candidates = [
        _candidate("cheap_slow", landed_unit_cost_minor=380, lead_time_days=25),
        _candidate("dear_fast", landed_unit_cost_minor=400, lead_time_days=10),
    ]
    ranked, _ = rank(candidates, PROFILE, Constraints())
    # Cost carries 0.30 and lead time 0.15, so the cheaper offer wins and the faster one is the runner-up.
    assert ranked[0].offer_id == "cheap_slow"
    offs = trade_offs(ranked, candidates)
    assert offs[0].offer_id == "dear_fast"
    assert offs[0].versus_offer_id == "cheap_slow"
    assert "more expensive" in offs[0].summary
    assert "15 fewer days" in offs[0].summary


def test_ranked_offers_are_numbered_from_one() -> None:
    ranked, _ = rank(
        [_candidate("a"), _candidate("b", landed_unit_cost_minor=900)], PROFILE, Constraints()
    )
    offers = to_ranked_offers(ranked)
    assert [o.rank for o in offers] == [1, 2]
