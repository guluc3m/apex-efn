"""Gate combination matrix (D3-08, spec §3.4.4).

Criterion 10: the table is exhaustive. The parametrised test below walks every pair of bands, so a band added
to the contract without a decision here fails the suite instead of silently falling through.
"""

from __future__ import annotations

import pytest

from apex.contracts.generated.models import (
    GateReason,
    PriceSanityBand,
    SellerConfidenceBand,
)
from apex.domain.gate_matrix import (
    GateConfig,
    GateOutcome,
    all_combinations,
    combine,
)

HIGH = SellerConfidenceBand.high
MEDIUM = SellerConfidenceBand.medium
LOW = SellerConfidenceBand.low
INSUFFICIENT = SellerConfidenceBand.insufficient_data
UNTRUSTED = SellerConfidenceBand.untrusted

NORMAL = PriceSanityBand.normal
ATYPICAL = PriceSanityBand.atypical
IMPLAUSIBLE = PriceSanityBand.implausible
NO_REFERENCE = PriceSanityBand.insufficient_reference


# ----- the table, cell by cell -------------------------------------------------------------------


@pytest.mark.parametrize("confidence", [HIGH, MEDIUM])
def test_a_normal_price_from_a_trusted_seller_negotiates(confidence) -> None:
    decision = combine(NORMAL, confidence)
    assert decision.outcome is GateOutcome.negotiate
    assert decision.reasons == ()
    assert decision.blocked is False


@pytest.mark.parametrize("confidence", [LOW, INSUFFICIENT])
def test_a_normal_price_from_an_unreliable_seller_goes_to_a_human(confidence) -> None:
    decision = combine(NORMAL, confidence)
    assert decision.outcome is GateOutcome.human_gate
    assert GateReason.seller_low in decision.reasons


@pytest.mark.parametrize("price", [NORMAL, ATYPICAL, IMPLAUSIBLE, NO_REFERENCE])
def test_an_untrusted_seller_always_discards(price) -> None:
    """The `untrusted` column is constant: a known-bad seller is never rescued by a good price."""
    decision = combine(price, UNTRUSTED)
    assert decision.outcome is GateOutcome.discard
    assert GateReason.seller_low in decision.reasons


@pytest.mark.parametrize("confidence", [HIGH, MEDIUM])
def test_an_atypical_price_from_a_trusted_seller_goes_to_a_human(confidence) -> None:
    decision = combine(ATYPICAL, confidence)
    assert decision.outcome is GateOutcome.human_gate
    assert GateReason.price_atypical in decision.reasons


@pytest.mark.parametrize("confidence", [LOW, INSUFFICIENT])
def test_atypical_price_plus_unreliable_seller_escalates_to_discard(confidence) -> None:
    """The most informative fraud signal: it escalates a level instead of being averaged away."""
    decision = combine(ATYPICAL, confidence)
    assert decision.outcome is GateOutcome.discard
    assert GateReason.price_atypical in decision.reasons
    assert GateReason.seller_low in decision.reasons


@pytest.mark.parametrize("confidence", list(SellerConfidenceBand))
def test_an_implausible_price_always_discards(confidence) -> None:
    assert combine(IMPLAUSIBLE, confidence).outcome is GateOutcome.discard


@pytest.mark.parametrize("confidence", [HIGH, MEDIUM, LOW, INSUFFICIENT])
def test_insufficient_reference_always_gates(confidence) -> None:
    """ADR-900 Q12: never negotiate on a price we cannot judge."""
    assert combine(NO_REFERENCE, confidence).outcome is GateOutcome.human_gate


# ----- the tenant knob ---------------------------------------------------------------------------


@pytest.mark.parametrize("confidence", [LOW, INSUFFICIENT])
def test_a_tenant_can_stop_the_escalation_at_a_human_gate(confidence) -> None:
    decision = combine(ATYPICAL, confidence, GateConfig(escalate_cheap_low_confidence=False))
    assert decision.outcome is GateOutcome.human_gate
    assert decision.blocked is True


def test_the_knob_never_softens_an_implausible_price() -> None:
    decision = combine(IMPLAUSIBLE, LOW, GateConfig(escalate_cheap_low_confidence=False))
    assert decision.outcome is GateOutcome.discard


# ----- totality ----------------------------------------------------------------------------------


def test_every_pair_of_bands_has_exactly_one_outcome() -> None:
    """Criterion 10: the matrix is total, so no offer can fall through it."""
    pairs = all_combinations()
    assert len(pairs) == len(PriceSanityBand) * len(SellerConfidenceBand)
    for price, confidence in pairs:
        decision = combine(price, confidence)
        assert isinstance(decision.outcome, GateOutcome)
        if decision.outcome is GateOutcome.negotiate:
            assert decision.reasons == ()
        else:
            assert decision.reasons, "a blocked offer must say why (criterion 16)"


def test_the_matrix_never_negotiates_without_a_trusted_seller() -> None:
    for price, confidence in all_combinations():
        if combine(price, confidence).outcome is GateOutcome.negotiate:
            assert confidence in {HIGH, MEDIUM}
            assert price is NORMAL


def test_the_cheap_unreliable_cell_is_the_strictest() -> None:
    """Spec §3.4.4: cheap + unreliable is a discard, not a gate — the escalation rule."""
    assert combine(ATYPICAL, LOW).outcome is GateOutcome.discard
    assert combine(ATYPICAL, HIGH).outcome is GateOutcome.human_gate
