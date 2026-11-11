"""Gate combination matrix (D3-08, spec §3.4.4).

Confidence is **not** traded against price. The table is a rule, not a weighted average: an anomalously
cheap price and an unreliable seller is the most informative fraud signal the system has, so it escalates
one severity level instead of being diluted.

The matrix is total over the two closed band sets, which is the point: every offer gets exactly one outcome
and a test can enumerate all of them (criterion 10).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from apex.contracts.generated.models import (
    GateReason,
    PriceSanityBand,
    SellerConfidenceBand,
)


class GateOutcome(StrEnum):
    """What the system does with the offer (spec §3.4.4)."""

    negotiate = "negotiate"
    human_gate = "human_gate"
    discard = "discard"


@dataclass(frozen=True, slots=True)
class GateDecision:
    """The outcome plus every cause that produced it, so the dashboard can explain *why* (criterion 16)."""

    outcome: GateOutcome
    reasons: tuple[GateReason, ...] = ()

    @property
    def blocked(self) -> bool:
        """True when the offer cannot proceed without a human. Negotiation is the only unblocked outcome."""
        return self.outcome is not GateOutcome.negotiate


@dataclass(frozen=True, slots=True)
class GateConfig:
    """The ``seller.*`` and ``gate.*`` knobs the matrix reads.

    Only one knob exists today: whether a cheap price from a low-confidence seller escalates to discard
    (spec §3.4.4) or stops at a human gate. It comes from config so a tenant can be more conservative
    without a deploy.
    """

    escalate_cheap_low_confidence: bool = True


#: Bands that make a seller "trustworthy enough" to negotiate without a human on price alone.
_TRUSTED = frozenset({SellerConfidenceBand.high, SellerConfidenceBand.medium})
#: Bands where the seller is unreliable but not known-bad.
_UNRELIABLE = frozenset({SellerConfidenceBand.low, SellerConfidenceBand.insufficient_data})


def combine(
    price: PriceSanityBand,
    confidence: SellerConfidenceBand,
    cfg: GateConfig | None = None,
) -> GateDecision:
    """Apply the spec §3.4.4 table. Total: every pair maps to exactly one outcome."""
    config = cfg or GateConfig()
    reasons: list[GateReason] = []

    if confidence is SellerConfidenceBand.untrusted:
        # An untrusted seller discards whatever the price says: the row is constant.
        reasons.append(GateReason.seller_low)
        return GateDecision(GateOutcome.discard, tuple(reasons))

    if price is PriceSanityBand.implausible:
        reasons.append(GateReason.price_atypical)
        return GateDecision(GateOutcome.discard, tuple(reasons))

    if price is PriceSanityBand.insufficient_reference:
        # ADR-900 Q12: always a human gate, never a silent negotiate.
        reasons.append(GateReason.price_insufficient_reference)
        if confidence in _UNRELIABLE:
            reasons.append(GateReason.seller_insufficient_data)
        return GateDecision(GateOutcome.human_gate, tuple(reasons))

    trusted = confidence in _TRUSTED
    if price is PriceSanityBand.normal:
        if trusted:
            return GateDecision(GateOutcome.negotiate)
        # normal price + low/insufficient confidence: a human decides.
        reasons.append(GateReason.seller_low)
        return GateDecision(GateOutcome.human_gate, tuple(reasons))

    # price is atypical from here on.
    reasons.append(GateReason.price_atypical)
    if trusted:
        return GateDecision(GateOutcome.human_gate, tuple(reasons))
    # atypical + unreliable: the fraud signal. Escalate one level unless the tenant turned it off.
    reasons.append(GateReason.seller_low)
    if config.escalate_cheap_low_confidence:
        return GateDecision(GateOutcome.discard, tuple(reasons))
    return GateDecision(GateOutcome.human_gate, tuple(reasons))


def all_combinations() -> list[tuple[PriceSanityBand, SellerConfidenceBand]]:
    """Every pair the matrix must handle. The test enumerates this, so a new band cannot be forgotten."""
    return [(p, c) for p in PriceSanityBand for c in SellerConfidenceBand]


__all__ = [
    "GateConfig",
    "GateDecision",
    "GateOutcome",
    "all_combinations",
    "combine",
]
