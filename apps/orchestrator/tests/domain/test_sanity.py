"""Price sanity engine (D3-07, spec §3.3).

The cases that matter are the ones the spec calls out: a −90% and a +200% outlier (criterion 5), the
`insufficient_reference` gate, the asymmetric low side, the absolute floor/ceiling prevailing over the
statistics, and the structured-cause escape hatch.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from apex.contracts.generated.models import (
    DispersionMeasure,
    PriceExplanationCode,
    PriceSanityBand,
    SanityDecision,
)
from apex.domain.sanity import ReferenceSet, SanityConfig, SanityError, check

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)

CFG = SanityConfig(
    config_version="v7",
    min_sample=5,
    z_ok=3.5,
    z_gate=6.0,
    low_side_factor=0.8,
    max_relative_rise=0.6,
    max_relative_drop=0.5,
)

# A tight, believable universe around 400 cents.
REFERENCE = ReferenceSet(mission=[395, 400, 405, 410, 415])


def _check(price: int, reference: ReferenceSet = REFERENCE, cfg: SanityConfig = CFG, **kw):
    return check(
        offer_id="o-1",
        unit_price_eur_minor=price,
        reference=reference,
        cfg=cfg,
        now=NOW,
        **kw,
    )


# ----- the normal case ----------------------------------------------------------------------------


def test_a_price_inside_the_band_is_negotiated() -> None:
    result = _check(405)
    assert result.band is PriceSanityBand.normal
    assert result.decision is SanityDecision.negotiate
    assert result.sample_size == 5
    assert result.median.amount_minor == 405
    assert result.dispersion_measure is DispersionMeasure.mad
    assert result.config_version == "price-sanity@1/v7"


def test_the_output_carries_everything_the_dashboard_and_the_signed_payload_need() -> None:
    result = _check(405)
    assert result.offer_id == "o-1"
    assert result.reference_price_eur.amount_minor == 405
    assert result.checked_at == NOW
    assert result.relative_deviation == pytest.approx(0.0)
    assert result.explanations == []


# ----- criterion 5: the two outliers --------------------------------------------------------------


def test_a_price_ninety_percent_below_the_median_is_implausible() -> None:
    result = _check(40)
    assert result.band is PriceSanityBand.implausible
    assert result.decision is SanityDecision.discard


def test_a_price_two_hundred_percent_above_the_median_is_implausible() -> None:
    result = _check(1215)
    assert result.band is PriceSanityBand.implausible
    assert result.decision is SanityDecision.discard


def test_a_moderately_high_price_is_atypical_and_goes_to_the_gate() -> None:
    # median 405, MAD 5: an index between z_ok (3.5) and z_gate (6.0) is 431..449 cents.
    result = _check(440)
    assert result.band is PriceSanityBand.atypical
    assert result.decision is SanityDecision.human_gate


# ----- insufficient reference ---------------------------------------------------------------------


def test_too_few_references_goes_to_a_human_not_to_negotiation() -> None:
    """ADR-900 Q12: `insufficient_reference` always gates; it never negotiates blindly."""
    result = _check(405, reference=ReferenceSet(mission=[400, 410]))
    assert result.band is PriceSanityBand.insufficient_reference
    assert result.decision is SanityDecision.human_gate
    assert result.sample_size == 2
    assert result.index_score is None


# ----- the asymmetric low side --------------------------------------------------------------------


def test_the_low_side_is_stricter_than_the_high_side() -> None:
    """`low_side_factor` multiplies the low thresholds, so a symmetric z is not symmetric in outcome."""
    # median 400, MAD 50. The low gate is -6.0 * 0.8 = -4.8 and the high gate is +6.0, so a z of -5.0 is
    # implausible while the same +5.0 is only atypical.
    wide = ReferenceSet(mission=[300, 350, 400, 450, 500])
    low = _check(30, reference=wide)
    high = _check(770, reference=wide)
    assert low.band is PriceSanityBand.implausible
    assert high.band is PriceSanityBand.atypical


# ----- absolute bounds prevail --------------------------------------------------------------------


def test_an_absolute_floor_prevails_over_the_statistics() -> None:
    cfg = replace(CFG, floor_per_unit_minor=390)
    result = _check(300, cfg=cfg)
    assert result.band is PriceSanityBand.implausible
    assert result.decision is SanityDecision.discard


def test_an_absolute_ceiling_prevails_over_the_statistics() -> None:
    cfg = replace(CFG, ceiling_per_unit_minor=420)
    result = _check(500, cfg=cfg)
    assert result.band is PriceSanityBand.implausible


def test_a_price_inside_the_absolute_bounds_is_not_rescued_by_them() -> None:
    cfg = replace(CFG, floor_per_unit_minor=100)
    assert _check(405, cfg=cfg).band is PriceSanityBand.normal


# ----- dispersion fallbacks -----------------------------------------------------------------------


def test_identical_prices_fall_back_to_the_relative_deviation() -> None:
    """MAD is 0 when every reference is the same, and so is the IQR: the index is undefined."""
    result = _check(420, reference=ReferenceSet(mission=[400, 400, 400, 400, 400]))
    assert result.dispersion_measure is DispersionMeasure.relative
    assert result.index_score is None
    assert result.band is PriceSanityBand.normal  # 5% above, inside max_relative_rise


def test_a_relative_drop_beyond_the_limit_is_atypical() -> None:
    result = _check(180, reference=ReferenceSet(mission=[400, 400, 400, 400, 400]))
    assert result.band is PriceSanityBand.atypical


def test_the_iqr_is_used_when_the_mad_is_zero_but_the_spread_is_not() -> None:
    # Three values equal the median (MAD 0) but the quartiles differ, so the IQR is the fallback.
    result = _check(405, reference=ReferenceSet(mission=[400, 400, 400, 500, 600]))
    assert result.dispersion_measure is DispersionMeasure.iqr


# ----- deep discount ------------------------------------------------------------------------------


def test_more_than_sixty_percent_below_the_median_is_at_least_atypical() -> None:
    """Even with a wide spread that hides it from the index (spec §3.3.3)."""
    wide = ReferenceSet(mission=[100, 400, 400, 400, 1000])
    result = _check(120, reference=wide)
    assert result.band in {PriceSanityBand.atypical, PriceSanityBand.implausible}
    assert result.decision is not SanityDecision.negotiate


# ----- structured causes --------------------------------------------------------------------------


def test_a_structured_cause_can_keep_an_atypical_low_price_normal() -> None:
    """A volume tier or a MOQ difference is a closed enum, never prose (spec §3.3.3)."""
    result = _check(440, causes=[PriceExplanationCode.volume_tier_difference])
    assert result.band is PriceSanityBand.normal
    codes = {e.code for e in result.explanations}
    assert PriceExplanationCode.volume_tier_difference in codes


def test_a_cause_never_rescues_an_implausible_price() -> None:
    result = _check(40, causes=[PriceExplanationCode.volume_tier_difference])
    assert result.band is PriceSanityBand.implausible
    assert result.decision is SanityDecision.discard


def test_the_none_cause_is_not_recorded_as_an_explanation() -> None:
    result = _check(405, causes=[PriceExplanationCode.none])
    assert result.explanations == []


# ----- configuration is not optional --------------------------------------------------------------


def test_an_unset_threshold_is_a_loud_error() -> None:
    with pytest.raises(SanityError) as caught:
        SanityConfig.from_mapping({"min_sample": 5}, "v1")
    assert caught.value.code == "config_unset"


def test_the_config_slice_builds_the_config() -> None:
    cfg = SanityConfig.from_mapping(
        {
            "min_sample": 5,
            "z_ok": "3.5",
            "z_gate": "6.0",
            "low_side_factor": "0.8",
            "max_relative_rise": "0.6",
            "max_relative_drop": "0.5",
            "floor_per_unit": {"amount_minor": 100, "currency": "EUR"},
            "ceiling_per_unit": None,
        },
        "v7",
    )
    assert cfg.min_sample == 5
    assert cfg.floor_per_unit_minor == 100
    assert cfg.ceiling_per_unit_minor is None


def test_a_non_positive_price_is_refused() -> None:
    with pytest.raises(SanityError) as caught:
        _check(0)
    assert caught.value.code == "invalid_price"


# ----- determinism --------------------------------------------------------------------------------


def test_the_same_inputs_always_produce_the_same_check() -> None:
    """Criterion 6 in spirit: a stored check must be reproducible from the same inputs."""
    first = _check(440)
    second = _check(440)
    assert first.model_dump() == second.model_dump()
