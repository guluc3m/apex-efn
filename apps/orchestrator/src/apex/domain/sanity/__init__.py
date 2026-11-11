"""Price sanity engine (D3-07, spec §3.3).

Deterministic and configurable: the same offer, reference set and config always produce the same band. The
engine answers one question — *is this price believable for this product?* — and it answers it before any
negotiation budget is spent (spec §3.3: "no se negocia a ciegas").

Three rules shape the implementation:

* **Robust statistics, not mean and standard deviation.** A single outlier must not move the reference, so the
  centre is the median and the dispersion is MAD, falling back to IQR and then to the relative deviation.
* **The cheap side is more dangerous.** Fraud, counterfeits and hook prices live below the median, so the
  low-side threshold is multiplied by ``sanity.low_side_factor`` (spec §3.3.3).
* **A legitimate cause is a closed enum, never prose.** A price can stay ``normal`` when the difference is
  explained by a volume tier, a MOQ, an incoterm, a quality grade or a specification, and the explanation is
  a ``PriceExplanationCode`` the dashboard can render and the signed payload can carry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import median
from typing import Any

from apex.contracts.generated.models import (
    Currency,
    DispersionMeasure,
    Money,
    PriceExplanation,
    PriceExplanationCode,
    PriceSanityBand,
    PriceSanityCheck,
    SanityDecision,
)

ENGINE_VERSION = "price-sanity@1"
"""Bumped when the arithmetic changes. It travels in ``config_version`` so a stored check is reproducible."""

Z_SCALE = 0.6745
"""The constant that turns a MAD into a z-score for a normal distribution (spec §3.3.2)."""

DEEP_DISCOUNT = 0.60
"""More than 60% below the median is at least ``atypical`` whatever the index says (spec §3.3.3)."""


class SanityError(ValueError):
    """The engine cannot run. ``code`` is closed so the caller can react without parsing prose."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SanityConfig:
    """The ``sanity.*`` slice of the effective tenant/category config (spec §7).

    Every threshold comes from here. The engine has no defaults of its own: a missing value is a loud error,
    not a guess (ADR-900 Q7).
    """

    config_version: str
    min_sample: int
    z_ok: float
    z_gate: float
    low_side_factor: float
    max_relative_rise: float
    max_relative_drop: float
    floor_per_unit_minor: int | None = None
    ceiling_per_unit_minor: int | None = None

    @classmethod
    def from_mapping(cls, sanity: Mapping[str, Any], config_version: str) -> SanityConfig:
        def need(key: str) -> object:
            value = sanity.get(key)
            if value is None:
                raise SanityError("config_unset", f"sanity.{key} is unset")
            return value

        def num(key: str) -> float:
            value = need(key)  # raises config_unset outside the try: unset is not "not a number"
            try:
                return float(Decimal(str(value)))
            except (ArithmeticError, ValueError) as exc:
                raise SanityError("config_invalid", f"sanity.{key} is not a number") from exc

        def bound(key: str) -> int | None:
            value = sanity.get(key)
            if value is None:
                return None
            if isinstance(value, dict):
                return int(value["amount_minor"])
            return int(value)

        return cls(
            config_version=config_version,
            min_sample=int(num("min_sample")),
            z_ok=num("z_ok"),
            z_gate=num("z_gate"),
            low_side_factor=num("low_side_factor"),
            max_relative_rise=num("max_relative_rise"),
            max_relative_drop=num("max_relative_drop"),
            floor_per_unit_minor=bound("floor_per_unit"),
            ceiling_per_unit_minor=bound("ceiling_per_unit"),
        )


@dataclass(frozen=True, slots=True)
class ReferenceSet:
    """The comparison universe (spec §3.3.1). Amounts are landed cost per unit in EUR minor units."""

    mission: Sequence[int] = ()
    history: Sequence[int] = ()
    benchmark: Sequence[int] = ()

    def all_prices(self) -> list[int]:
        return [*self.mission, *self.history, *self.benchmark]


@dataclass(frozen=True, slots=True)
class Dispersion:
    measure: DispersionMeasure
    value: float
    median: float


def _dispersion(prices: Sequence[int], centre: float) -> Dispersion:
    """MAD first, then IQR, then the relative deviation (spec §3.3.2)."""
    deviations = [abs(p - centre) for p in prices]
    mad = float(median(deviations))
    if mad > 0:
        return Dispersion(DispersionMeasure.mad, mad, centre)
    ordered = sorted(prices)
    iqr = float(_quantile(ordered, 0.75) - _quantile(ordered, 0.25))
    if iqr > 0:
        return Dispersion(DispersionMeasure.iqr, iqr, centre)
    return Dispersion(DispersionMeasure.relative, 0.0, centre)


def _quantile(ordered: Sequence[int], q: float) -> float:
    """Linear-interpolation quantile. Small and explicit: the reference set is tiny and must be reproducible."""
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower]) * (1 - weight) + float(ordered[upper]) * weight


def _index_score(price: float, disp: Dispersion) -> float | None:
    if disp.measure is DispersionMeasure.mad and disp.value > 0:
        return Z_SCALE * (price - disp.median) / disp.value
    if disp.measure is DispersionMeasure.iqr and disp.value > 0:
        return (price - disp.median) / disp.value
    return None


def check(
    *,
    offer_id: str,
    unit_price_eur_minor: int,
    reference: ReferenceSet,
    cfg: SanityConfig,
    now: datetime,
    causes: Sequence[PriceExplanationCode] = (),
) -> PriceSanityCheck:
    """Classify one offer's unit price against its reference set.

    ``causes`` are legitimate explanations the caller has already established from structured data (volume
    tier, MOQ, incoterm, quality, specification). They can keep an otherwise ``atypical`` low price in
    ``normal``; they never rescue an ``implausible`` one.
    """
    if unit_price_eur_minor <= 0:
        raise SanityError("invalid_price", "unit price must be positive")
    prices = reference.all_prices()
    sample_size = len(prices)
    explanations: list[PriceExplanation] = [
        PriceExplanation(code=code) for code in causes if code is not PriceExplanationCode.none
    ]
    money = Money(amount_minor=unit_price_eur_minor, currency=Currency.EUR)

    if sample_size < cfg.min_sample:
        # Not enough to judge: the offer goes to a human instead of being negotiated blindly (spec §3.3.1).
        return PriceSanityCheck(
            offer_id=offer_id,
            reference_price_eur=money,
            median=money,
            dispersion_measure=DispersionMeasure.relative,
            dispersion_value=0.0,
            sample_size=sample_size,
            index_score=None,
            relative_deviation=0.0,
            band=PriceSanityBand.insufficient_reference,
            decision=SanityDecision.human_gate,
            explanations=explanations,
            config_version=f"{ENGINE_VERSION}/{cfg.config_version}",
            checked_at=now,
        )

    centre = float(median(prices))
    disp = _dispersion(prices, centre)
    price = float(unit_price_eur_minor)
    index = _index_score(price, disp)
    relative = (price - centre) / centre if centre else 0.0

    band = _classify(
        price=price,
        centre=centre,
        index=index,
        relative=relative,
        cfg=cfg,
    )
    if band is PriceSanityBand.atypical and causes:
        # Explained by a structured cause: the price is unusual but understood, so it may stay normal.
        band = PriceSanityBand.normal
        explanations.append(PriceExplanation(code=PriceExplanationCode.none))

    return PriceSanityCheck(
        offer_id=offer_id,
        reference_price_eur=money,
        median=Money(amount_minor=int(round(centre)), currency=Currency.EUR),
        dispersion_measure=disp.measure,
        dispersion_value=disp.value,
        sample_size=sample_size,
        index_score=index,
        relative_deviation=relative,
        band=band,
        decision=_decision(band),
        explanations=explanations,
        config_version=f"{ENGINE_VERSION}/{cfg.config_version}",
        checked_at=now,
    )


def _classify(
    *,
    price: float,
    centre: float,
    index: float | None,
    relative: float,
    cfg: SanityConfig,
) -> PriceSanityBand:
    """Absolute bounds first, then the statistical bands, then the deep-discount floor (spec §3.3.3)."""
    if cfg.floor_per_unit_minor is not None and price < cfg.floor_per_unit_minor:
        return PriceSanityBand.implausible
    if cfg.ceiling_per_unit_minor is not None and price > cfg.ceiling_per_unit_minor:
        return PriceSanityBand.implausible
    if index is not None:
        high_gate = cfg.z_gate
        low_gate = -cfg.z_gate * cfg.low_side_factor
        high_ok = cfg.z_ok
        low_ok = -cfg.z_ok * cfg.low_side_factor
        if index > high_gate or index < low_gate:
            return PriceSanityBand.implausible
        if index > high_ok or index < low_ok:
            return PriceSanityBand.atypical
    # The relative bounds catch a price that the index misses when dispersion is large.
    if relative > cfg.max_relative_rise or relative < -cfg.max_relative_drop:
        return PriceSanityBand.atypical
    # A price far below the median is at least atypical even when the spread hides it.
    if centre > 0 and (centre - price) / centre > DEEP_DISCOUNT:
        return PriceSanityBand.atypical
    return PriceSanityBand.normal


def _decision(band: PriceSanityBand) -> SanityDecision:
    """The system's response to each band (spec §3.3.3). ``insufficient_reference`` always gates."""
    if band is PriceSanityBand.normal:
        return SanityDecision.negotiate
    if band is PriceSanityBand.implausible:
        return SanityDecision.discard
    return SanityDecision.human_gate


__all__ = [
    "DEEP_DISCOUNT",
    "Dispersion",
    "ENGINE_VERSION",
    "ReferenceSet",
    "SanityConfig",
    "SanityError",
    "Z_SCALE",
    "check",
]
