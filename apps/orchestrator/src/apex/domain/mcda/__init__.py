"""MCDA scoring and ranking (D3-09, spec §3.7).

Every offer — original or negotiated — is scored with a weighted sum of normalised criteria:

``score = Σ wᵢ·fᵢ(xᵢ) − penalties``

Three rules from the spec shape this module:

* **Hard constraints are a pre-filter, not a penalty** (spec §3.7). An offer that fails one is excluded with a
  visible reason; it never competes on points, because a cheap offer from a banned country is not "a bit
  worse", it is not an option.
* **Every ``f()`` is monotone and documented.** Each criterion has one direction and one normalisation, and
  the breakdown carries the normalised value so the dashboard can show why an offer won.
* **The ranking comes from code.** The LLM narrates the numbers; it never produces them (spec §3.7).

Missing inputs are explicit: a criterion with no data contributes nothing and is reported as such, instead of
being scored as a neutral 0.5 — which is what the scaffold did and what the spec rejects.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from apex.contracts.generated.models import (
    Currency,
    ExcludedOffer,
    FinancialVerdict,
    Money,
    NullableMoney,
    RankedOffer,
    Recommendation,
    Savings,
    ScoreBreakdown,
    ScoreCriterion,
    SellerConfidenceBand,
    TradeOff,
)

ENGINE_VERSION = "mcda@1"
"""Bumped when a normalisation changes. It travels in ``model_version`` so a stored ranking is reproducible."""

#: Criteria where a **higher** raw value is better. The rest are minimised.
MAXIMISED: frozenset[ScoreCriterion] = frozenset(
    {
        ScoreCriterion.seller_confidence,
        ScoreCriterion.financial_fit,
        ScoreCriterion.margin_potential,
        ScoreCriterion.spec_match,
        ScoreCriterion.negotiation_gain,
    }
)
"""``compliance_risk``, ``landed_cost`` and ``lead_time`` are minimised: less is better."""


class McdaError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Candidate:
    """One offer as the ranking sees it. ``None`` means the input is **unknown**, not zero."""

    offer_id: str
    landed_unit_cost_minor: int
    lead_time_days: int | None = None
    seller_confidence_score: int | None = None
    seller_band: SellerConfidenceBand = SellerConfidenceBand.insufficient_data
    financial_verdict: FinancialVerdict = FinancialVerdict.within_budget
    margin_potential: float | None = None
    spec_match: float | None = None
    compliance_risk: float | None = None
    negotiation_gain: float | None = None
    country: str | None = None
    platform: str | None = None
    certifications: Sequence[str] = ()
    list_price_minor: int | None = None


@dataclass(frozen=True, slots=True)
class Constraints:
    """The profile's hard constraints (spec §3.7). Applied before scoring, never as a penalty."""

    banned_platforms: Sequence[str] = ()
    banned_countries: Sequence[str] = ()
    required_certifications: Sequence[str] = ()
    min_accepted_seller_band: SellerConfidenceBand = SellerConfidenceBand.insufficient_data
    max_lead_time_days: int | None = None


@dataclass(frozen=True, slots=True)
class Profile:
    """Weights per criterion. They must be non-negative; they are normalised to sum to 1."""

    profile_id: str
    weights: Mapping[ScoreCriterion, float]

    def normalised(self) -> dict[ScoreCriterion, float]:
        total = sum(self.weights.values())
        if total <= 0:
            raise McdaError("invalid_weights", "profile weights must sum to a positive number")
        if any(w < 0 for w in self.weights.values()):
            raise McdaError("invalid_weights", "profile weights must be non-negative")
        return {criterion: w / total for criterion, w in self.weights.items()}


#: Band ordering, worst to best, for the minimum-accepted-band constraint.
_BAND_ORDER: dict[SellerConfidenceBand, int] = {
    SellerConfidenceBand.untrusted: 0,
    SellerConfidenceBand.insufficient_data: 1,
    SellerConfidenceBand.low: 2,
    SellerConfidenceBand.medium: 3,
    SellerConfidenceBand.high: 4,
}


def exclude(candidate: Candidate, constraints: Constraints) -> list[str]:
    """Every hard constraint the candidate fails, as visible reasons. Empty means it competes."""
    reasons: list[str] = []
    if candidate.platform and candidate.platform in set(constraints.banned_platforms):
        reasons.append(f"platform {candidate.platform} is banned by the profile")
    if candidate.country and candidate.country in set(constraints.banned_countries):
        reasons.append(f"country {candidate.country} is banned by the profile")
    missing = set(constraints.required_certifications) - set(candidate.certifications)
    if missing:
        reasons.append(f"missing required certifications: {', '.join(sorted(missing))}")
    if _BAND_ORDER[candidate.seller_band] < _BAND_ORDER[constraints.min_accepted_seller_band]:
        reasons.append(
            f"seller band {candidate.seller_band.value} is below the accepted "
            f"{constraints.min_accepted_seller_band.value}"
        )
    if (
        constraints.max_lead_time_days is not None
        and candidate.lead_time_days is not None
        and candidate.lead_time_days > constraints.max_lead_time_days
    ):
        reasons.append(
            f"lead time {candidate.lead_time_days}d exceeds the accepted "
            f"{constraints.max_lead_time_days}d"
        )
    if candidate.financial_verdict is FinancialVerdict.out_of_budget:
        reasons.append("the financial fit is out_of_budget")
    return reasons


def _normalise(candidate: Candidate, peers: Sequence[Candidate]) -> dict[ScoreCriterion, float]:
    """Min-max within the candidate set, per criterion. Unknown inputs are omitted, never defaulted."""
    values: dict[ScoreCriterion, float] = {}

    def spread(extract: Callable[[Candidate], float | None]) -> tuple[float, float] | None:
        raw = [extract(c) for c in peers]
        known = [v for v in raw if v is not None]
        if len(known) < 2:
            return None
        low, high = min(known), max(known)
        if high == low:
            return None
        return low, high

    def score(
        criterion: ScoreCriterion,
        raw: float | None,
        extract: Callable[[Candidate], float | None],
    ) -> None:
        if raw is None:
            return
        bounds = spread(extract)
        if bounds is None:
            # A single value (or all equal) carries no information about relative merit: it scores 1.0
            # because nothing in the set is better on that criterion, and the breakdown shows the weight.
            values[criterion] = 1.0
            return
        low, high = bounds
        ratio = (raw - low) / (high - low)
        values[criterion] = ratio if criterion in MAXIMISED else 1.0 - ratio

    score(
        ScoreCriterion.landed_cost,
        float(candidate.landed_unit_cost_minor),
        lambda c: float(c.landed_unit_cost_minor),
    )
    score(
        ScoreCriterion.lead_time,
        None if candidate.lead_time_days is None else float(candidate.lead_time_days),
        lambda c: None if c.lead_time_days is None else float(c.lead_time_days),
    )
    score(
        ScoreCriterion.seller_confidence,
        None
        if candidate.seller_confidence_score is None
        else float(candidate.seller_confidence_score),
        lambda c: None if c.seller_confidence_score is None else float(c.seller_confidence_score),
    )
    score(
        ScoreCriterion.financial_fit,
        _VERDICT_VALUE[candidate.financial_verdict],
        lambda c: _VERDICT_VALUE[c.financial_verdict],
    )
    score(ScoreCriterion.margin_potential, candidate.margin_potential, lambda c: c.margin_potential)
    score(ScoreCriterion.spec_match, candidate.spec_match, lambda c: c.spec_match)
    score(ScoreCriterion.compliance_risk, candidate.compliance_risk, lambda c: c.compliance_risk)
    score(
        ScoreCriterion.negotiation_gain,
        candidate.negotiation_gain,
        lambda c: c.negotiation_gain,
    )
    return values


_VERDICT_VALUE: dict[FinancialVerdict, float] = {
    FinancialVerdict.out_of_budget: 0.0,
    FinancialVerdict.stretch: 0.5,
    FinancialVerdict.within_budget: 1.0,
}


@dataclass(frozen=True, slots=True)
class Ranked:
    offer_id: str
    score: float
    breakdown: tuple[ScoreBreakdown, ...]


def rank(
    candidates: Sequence[Candidate], profile: Profile, constraints: Constraints
) -> tuple[list[Ranked], list[ExcludedOffer]]:
    """Score and rank the candidates that pass the hard constraints.

    Ties break on ``offer_id`` so the same inputs always produce the same order (criterion 27).
    """
    weights = profile.normalised()
    eligible: list[Candidate] = []
    excluded: list[ExcludedOffer] = []
    for candidate in candidates:
        reasons = exclude(candidate, constraints)
        if reasons:
            excluded.append(ExcludedOffer(offer_id=candidate.offer_id, reasons=reasons))
        else:
            eligible.append(candidate)
    if not eligible:
        return [], excluded

    ranked: list[Ranked] = []
    for candidate in eligible:
        normalised = _normalise(candidate, eligible)
        breakdown: list[ScoreBreakdown] = []
        total = 0.0
        for criterion, weight in weights.items():
            value = normalised.get(criterion)
            contribution = weight * value if value is not None else 0.0
            total += contribution
            breakdown.append(
                ScoreBreakdown(
                    criterion=criterion,
                    weight=weight,
                    # An unknown criterion contributes 0 and says so with a 0 value; the weight is visible.
                    normalized_value=value if value is not None else 0.0,
                    contribution=contribution,
                )
            )
        ranked.append(
            Ranked(
                offer_id=candidate.offer_id,
                score=min(1.0, max(0.0, total)),
                breakdown=tuple(breakdown),
            )
        )
    ranked.sort(key=lambda r: (-r.score, r.offer_id))
    return ranked, excluded


def to_ranked_offers(ranked: Sequence[Ranked]) -> list[RankedOffer]:
    """The contract's ``RankedOffer`` list. ``narrative`` stays ``None``: the LLM fills it, never the score."""
    return [
        RankedOffer(
            rank=index, offer_id=item.offer_id, score=item.score, breakdown=list(item.breakdown)
        )
        for index, item in enumerate(ranked, start=1)
    ]


def recommendation(
    *,
    mission_id: str,
    profile_id: str,
    ranked: Sequence[Ranked],
    excluded: Sequence[ExcludedOffer],
    candidates: Sequence[Candidate],
    config_version: str,
    now: datetime,
) -> Recommendation:
    """Assemble the contract's ``Recommendation``. Savings are computed from the numbers, never estimated."""
    by_id = {c.offer_id: c for c in candidates}
    list_prices = [c.list_price_minor for c in candidates if c.list_price_minor is not None]
    best = ranked[0] if ranked else None
    savings = Savings(
        vs_list_price=None,
        vs_market_median=None,
    )
    if best is not None and list_prices:
        winner = by_id[best.offer_id]
        reference = winner.list_price_minor
        if reference is not None and reference > winner.landed_unit_cost_minor:
            savings = Savings(
                vs_list_price=NullableMoney(_money(reference - winner.landed_unit_cost_minor)),
                vs_market_median=None,
            )
    return Recommendation(
        mission_id=mission_id,
        profile_id=profile_id,
        ranking=to_ranked_offers(ranked),
        excluded=list(excluded),
        alternatives=None,
        savings=savings,
        config_version=config_version,
        model_version=f"{ENGINE_VERSION}/{config_version}",
        generated_at=now,
    )


def _money(amount_minor: int) -> Money:
    return Money(amount_minor=amount_minor, currency=Currency.EUR)


def trade_offs(ranked: Sequence[Ranked], candidates: Sequence[Candidate]) -> list[TradeOff]:
    """Explicit trade-offs between the winner and each runner-up, from the numbers that differ most."""
    if len(ranked) < 2:
        return []
    by_id = {c.offer_id: c for c in candidates}
    winner = by_id[ranked[0].offer_id]
    out: list[TradeOff] = []
    for item in ranked[1:]:
        other = by_id[item.offer_id]
        parts: list[str] = []
        if other.landed_unit_cost_minor < winner.landed_unit_cost_minor:
            parts.append("cheaper")
        elif other.landed_unit_cost_minor > winner.landed_unit_cost_minor:
            parts.append("more expensive")
        if (
            other.lead_time_days is not None
            and winner.lead_time_days is not None
            and other.lead_time_days != winner.lead_time_days
        ):
            days = other.lead_time_days - winner.lead_time_days
            parts.append(f"{abs(days)} more days" if days > 0 else f"{abs(days)} fewer days")
        if other.seller_band is not winner.seller_band:
            parts.append(f"{other.seller_band.value} confidence")
        out.append(
            TradeOff(
                offer_id=item.offer_id,
                versus_offer_id=winner.offer_id,
                summary=", ".join(parts) or "no material difference",
            )
        )
    return out


__all__ = [
    "Candidate",
    "Constraints",
    "ENGINE_VERSION",
    "MAXIMISED",
    "McdaError",
    "Profile",
    "Ranked",
    "exclude",
    "rank",
    "recommendation",
    "to_ranked_offers",
    "trade_offs",
]
