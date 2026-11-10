"""Typed tenant configuration models (PROMPT-IMPLEMENTACION.md §7).

Each section mirrors a block of ``config/defaults/tenant-config.v1.json``. A field typed
``X | None`` with a ``None`` default is a "sin definir" key: it is unset until the tenant supplies it,
and reading it through the typed accessors raises ``ConfigKeyUnset`` (see ``errors.py``). No value in
this module is a business default invented by the engine; the defaults come from the versioned JSON.

Business defaults are NOT duplicated here: a model is only ever built from a fully resolved mapping
produced by ``resolver.py``. The field defaults below exist only to make a partial mapping validate
during resolution and are always overridden by the global layer.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    model_validator,
)

SUPPORTED_CURRENCIES: Final[tuple[str, ...]] = ("EUR", "USD", "CNY")
"""Closed enum (ADR-400 §5). Not configurable. Mirrors DB enum ``Currency`` (D2-03)."""


class Band(StrEnum):
    """Seller confidence bands (spec §3.4). ``insufficient_data`` is a status, not a band."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNTRUSTED = "untrusted"


def _to_decimal(value: Any) -> Decimal:
    """Parse a rate or percentage as ``Decimal``. Floats are refused: they are how money bugs start."""
    if isinstance(value, (bool, float)):
        raise ValueError("use a decimal string or an integer, never a float")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except Exception as exc:
            raise ValueError(f"not a decimal: {value!r}") from exc
        if not result.is_finite():
            raise ValueError("decimal must be finite")
        return result
    raise ValueError(f"cannot parse {type(value).__name__} as a decimal")


Rate = Annotated[
    Decimal,
    BeforeValidator(_to_decimal),
    PlainSerializer(lambda d: format(d, "f"), return_type=str, when_used="json"),
]
"""A decimal fraction or ratio (0.08 means 8%). Stored and hashed as a decimal string, never a float."""


class Money(BaseModel):
    """``{amount_minor, currency}``: integer minor units and a closed currency (ADR-900)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    amount_minor: int = Field(ge=0)
    currency: Literal["EUR", "USD", "CNY"]

    @model_validator(mode="before")
    @classmethod
    def _no_floats(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("amount_minor"), float | bool):
            raise ValueError("amount_minor must be an integer, never a float")
        return data


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MoneySection(_Section):
    supported_currencies: tuple[str, ...]

    @model_validator(mode="after")
    def _closed_enum(self) -> MoneySection:
        if self.supported_currencies != SUPPORTED_CURRENCIES:
            raise ValueError(
                "money.supported_currencies is a closed, non-configurable enum "
                f"{SUPPORTED_CURRENCIES}; got {self.supported_currencies}"
            )
        return self


class FxSection(_Section):
    pivot: Literal["EUR"]
    max_age_hours: int = Field(ge=1)


class ReferenceWeights(_Section):
    """Weights of the reference sources (spec 3.3.1); renormalised over the sources that have data."""

    mission: Rate
    history: Rate
    benchmark: Rate

    @model_validator(mode="after")
    def _sum_to_one(self) -> ReferenceWeights:
        if any(w < 0 for w in (self.mission, self.history, self.benchmark)):
            raise ValueError("sanity.reference_weights must be non-negative")
        if self.mission + self.history + self.benchmark != Decimal(1):
            raise ValueError("sanity.reference_weights must sum to 1")
        return self


class SanitySection(_Section):
    min_sample: int = Field(ge=1)
    z_ok: Rate
    z_gate: Rate
    low_side_factor: Rate
    max_relative_rise: Rate
    max_relative_drop: Rate
    floor_per_unit: Money | None = None
    ceiling_per_unit: Money | None = None
    on_insufficient_reference: Literal["gate"]
    """ADR-900 Q12: ``insufficient_reference`` always goes to the gate; ``negotiate`` was removed."""
    reference_weights: ReferenceWeights

    @model_validator(mode="after")
    def _bands_ordered(self) -> SanitySection:
        if not (0 < self.low_side_factor <= 1):
            raise ValueError("sanity.low_side_factor must be in (0, 1]")
        if self.max_relative_rise <= 0 or self.max_relative_drop <= 0:
            raise ValueError("sanity.max_relative_rise/drop must be positive")
        if self.z_ok <= 0 or not self.z_ok < self.z_gate:
            raise ValueError(
                f"sanity.z_ok ({self.z_ok}) must be > 0 and < sanity.z_gate ({self.z_gate})"
            )
        floor, ceiling = self.floor_per_unit, self.ceiling_per_unit
        if floor is not None and ceiling is not None:
            if floor.currency != ceiling.currency:
                raise ValueError("sanity.floor_per_unit and ceiling_per_unit must share a currency")
            if floor.amount_minor > ceiling.amount_minor:
                raise ValueError("sanity.floor_per_unit must be <= sanity.ceiling_per_unit")
        for bound in (floor, ceiling):
            if bound is not None and bound.currency != "EUR":
                raise ValueError("sanity floor/ceiling are in EUR (spec 3.3)")
        return self


class SellerSection(_Section):
    weights: dict[str, Rate] | None = None
    """Signal-group weights (ADR-304). Unset in the shipped defaults; the engine refuses to run until a
    tenant sets them (ADR-900 Q3)."""
    x_sat: dict[str, Rate] | None = None
    """Saturation point per countable signal (ADR-304). Optional in the model so a tenant can set it; the
    engine raises ``config_unset`` while it is missing."""
    category_rating_mean: Rate | None = None
    category_five_star_share: Rate | None = None
    wilson_confidence: Rate | None = None
    min_verified_share: Rate | None = None
    max_duplicate_text_share: Rate | None = None
    rating_prior_weight: int = Field(ge=0)
    age_saturation_days: int = Field(ge=1)
    min_signals: int = Field(ge=1)
    band_high: Rate
    band_medium: Rate
    band_low: Rate
    hard_block_below: Rate
    min_accepted_band: Band
    review_burst_z: Rate
    max_dispute_rate: Rate
    snapshot_max_age_days: int = Field(ge=1)
    escalate_cheap_low_confidence: bool

    @model_validator(mode="after")
    def _ordering(self) -> SellerSection:
        bands = (self.band_low, self.band_medium, self.band_high, self.hard_block_below)
        if any(b < 0 or b > 100 for b in bands):
            raise ValueError("seller bands must be within 0..100")
        if not (self.band_low < self.band_medium < self.band_high):
            raise ValueError(
                "seller bands must satisfy band_low < band_medium < band_high "
                f"(got {self.band_low}, {self.band_medium}, {self.band_high})"
            )
        if not self.hard_block_below <= self.band_low:
            raise ValueError("seller.hard_block_below must be <= seller.band_low")
        if not (0 <= self.max_dispute_rate <= 1):
            raise ValueError("seller.max_dispute_rate must be within 0..1")
        if self.review_burst_z <= 0:
            raise ValueError("seller.review_burst_z must be positive")
        if self.min_accepted_band is Band.UNTRUSTED:
            raise ValueError("seller.min_accepted_band cannot be 'untrusted'")
        weights = self.weights
        if weights is not None and (
            any(w < 0 for w in weights.values()) or sum(weights.values()) != Decimal(1)
        ):
            raise ValueError("seller.weights must be non-negative and sum to 1")
        return self


class FinanceSection(_Section):
    safety_buffer_pct: Rate
    stale_after_days: int = Field(ge=1)
    cost_of_capital_rate: Rate | None = None
    """Unset (Q5). A landed-cost line that needs it is ``unknown`` with ``landed_cost_incomplete``."""

    @model_validator(mode="after")
    def _ranges(self) -> FinanceSection:
        if not (0 <= self.safety_buffer_pct <= 100):
            raise ValueError("finance.safety_buffer_pct must be within 0..100")
        if self.cost_of_capital_rate is not None and self.cost_of_capital_rate < 0:
            raise ValueError("finance.cost_of_capital_rate must be non-negative")
        return self


class LandedSection(_Section):
    """Landed-cost inputs (Q5). No external duty/VAT source in Phase 1: the tenant supplies them."""

    duty_rate: dict[str, Rate] | None = None
    """Per category. Unset means unknown, never 0."""
    import_vat_rate: dict[str, Rate] | None = None
    """Per destination country. Unset means unknown, never 0."""

    @model_validator(mode="after")
    def _non_negative(self) -> LandedSection:
        for table in (self.duty_rate, self.import_vat_rate):
            if table is not None and any(v < 0 for v in table.values()):
                raise ValueError("landed rates must be non-negative")
        return self


class ConstraintsSection(_Section):
    require_escrow: bool
    """Q14: an optional hard constraint, off by default."""


class Counterpart(StrEnum):
    HIGHER_VOLUME = "higher_volume"
    PREPAYMENT = "prepayment"
    FRAMEWORK_CONTRACT = "framework_contract"
    PAYMENT_TERMS = "payment_terms"
    GUARANTEE = "guarantee"
    PENALTY = "penalty"


PHASE1_COUNTERPARTS: Final[frozenset[Counterpart]] = frozenset(
    {Counterpart.HIGHER_VOLUME, Counterpart.FRAMEWORK_CONTRACT}
)
"""ADR-900 Q15: in Phase 1 a profile may enable only these, whatever it says."""


class NegSection(_Section):
    """Per-category, "sin definir" (unset) until the tenant supplies them."""

    target_discount: Rate | None = None
    max_discount: Rate | None = None
    max_rounds: int = Field(ge=1)
    max_tokens_per_conversation: int = Field(ge=1)
    max_messages_per_hour_per_account: int = Field(ge=1)
    max_message_chars: int = Field(ge=1)
    allowed_counterparts: tuple[Counterpart, ...]

    @model_validator(mode="after")
    def _rules(self) -> NegSection:
        for name, value in (
            ("target_discount", self.target_discount),
            ("max_discount", self.max_discount),
        ):
            if value is not None and not (0 <= value <= 1):
                raise ValueError(f"neg.{name} must be a fraction within 0..1")
        if (
            self.target_discount is not None
            and self.max_discount is not None
            and self.target_discount > self.max_discount
        ):
            raise ValueError("neg.target_discount must be <= neg.max_discount")
        forbidden = set(self.allowed_counterparts) - PHASE1_COUNTERPARTS
        if forbidden:
            raise ValueError(
                "counterparts not allowed before Phase 2 (ADR-900 Q15): "
                + ", ".join(sorted(c.value for c in forbidden))
            )
        if len(set(self.allowed_counterparts)) != len(self.allowed_counterparts):
            raise ValueError("neg.allowed_counterparts must not repeat a value")
        return self


class GateSection(_Section):
    sla_hours: int = Field(ge=1)
    max_renegotiations: int = Field(ge=0)


class ApprovalSection(_Section):
    threshold: Money | None = None
    dual_control_above: Money | None = None

    @model_validator(mode="after")
    def _dual_above_threshold(self) -> ApprovalSection:
        t, d = self.threshold, self.dual_control_above
        if t is not None and d is not None:
            if t.currency != d.currency:
                raise ValueError("approval.threshold and dual_control_above must share a currency")
            if d.amount_minor < t.amount_minor:
                raise ValueError("approval.dual_control_above must be >= approval.threshold")
        return self


class SigningSection(_Section):
    session_minutes: int = Field(ge=1)
    max_decisions_per_session: int = Field(ge=1)
    high_value_reauth_above: Money | None = None


class SupervisorSection(_Section):
    """ADR-900 (issue #99)."""

    stuck_after_minutes: int = Field(ge=1)
    degrade_on_budget_exhausted: bool


class LlmRole(_Section):
    base_url: str
    model: str
    capabilities: tuple[str, ...] = ()


class LlmSection(_Section):
    roles: dict[str, LlmRole] | None = None


class TenantConfig(_Section):
    """Full typed configuration (all sections). Built from a resolved, validated mapping."""

    money: MoneySection
    fx: FxSection
    sanity: SanitySection
    seller: SellerSection
    finance: FinanceSection
    landed: LandedSection
    constraints: ConstraintsSection
    neg: NegSection
    gate: GateSection
    approval: ApprovalSection
    signing: SigningSection
    supervisor: SupervisorSection
    llm: LlmSection

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> TenantConfig:
        return cls.model_validate(data)


UNSET_LEAF_PATHS: Final[frozenset[str]] = frozenset(
    {
        "sanity.floor_per_unit",
        "sanity.ceiling_per_unit",
        "seller.weights",
        "neg.target_discount",
        "neg.max_discount",
        "finance.cost_of_capital_rate",
        "landed.duty_rate",
        "landed.import_vat_rate",
        "approval.threshold",
        "approval.dual_control_above",
        "signing.high_value_reauth_above",
    }
)
"""Dotted paths that §7 marks as "sin definir" / "ver ADR". Used by tests and the resolver."""
