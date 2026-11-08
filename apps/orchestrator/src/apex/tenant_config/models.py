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

from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUPPORTED_CURRENCIES: Final[tuple[str, ...]] = ("EUR", "USD", "CNY")
"""Closed enum (ADR-400 §5). Not configurable. Mirrors DB enum ``Currency`` (D2-03)."""


class Band(StrEnum):
    """Seller confidence bands (spec §3.4). ``insufficient_data`` is a status, not a band."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNTRUSTED = "untrusted"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MoneySection(_Section):
    supported_currencies: tuple[str, ...] = SUPPORTED_CURRENCIES

    @model_validator(mode="after")
    def _closed_enum(self) -> MoneySection:
        if self.supported_currencies != SUPPORTED_CURRENCIES:
            raise ValueError(
                "money.supported_currencies is a closed, non-configurable enum "
                f"{SUPPORTED_CURRENCIES}; got {self.supported_currencies}"
            )
        return self


class FxSection(_Section):
    pivot: Literal["EUR"] = "EUR"
    max_age_hours: int = Field(ge=1)


class SanitySection(_Section):
    min_sample: int = Field(ge=1)
    z_ok: float = Field(gt=0)
    z_gate: float = Field(gt=0)
    low_side_factor: float = Field(gt=0, le=1)
    max_relative_rise: float = Field(gt=0)
    max_relative_drop: float = Field(gt=0)
    floor_per_unit: float | None = Field(default=None, ge=0)
    ceiling_per_unit: float | None = Field(default=None, ge=0)
    on_insufficient_reference: Literal["gate", "negotiate"] = "gate"

    @model_validator(mode="after")
    def _bands_ordered(self) -> SanitySection:
        if not self.z_ok < self.z_gate:
            raise ValueError(f"sanity.z_ok ({self.z_ok}) must be < sanity.z_gate ({self.z_gate})")
        if (
            self.floor_per_unit is not None
            and self.ceiling_per_unit is not None
            and self.floor_per_unit > self.ceiling_per_unit
        ):
            raise ValueError("sanity.floor_per_unit must be <= sanity.ceiling_per_unit")
        return self


class SellerSection(_Section):
    weights: dict[str, float] | None = None
    """Unset ("ver ADR-304"). Keys are signal-group names; values must sum to 1 when set."""
    rating_prior_weight: float = Field(ge=0)
    age_saturation_days: int = Field(ge=1)
    min_signals: int = Field(ge=1)
    band_high: float = Field(ge=0, le=100)
    band_medium: float = Field(ge=0, le=100)
    band_low: float = Field(ge=0, le=100)
    hard_block_below: float = Field(ge=0, le=100)
    min_accepted_band: Band = Band.MEDIUM
    review_burst_z: float = Field(gt=0)
    max_dispute_rate: float = Field(ge=0, le=1)
    snapshot_max_age_days: int = Field(ge=1)
    escalate_cheap_low_confidence: bool = True

    @model_validator(mode="after")
    def _ordering(self) -> SellerSection:
        if not (self.band_low < self.band_medium < self.band_high):
            raise ValueError(
                "seller bands must satisfy band_low < band_medium < band_high "
                f"(got {self.band_low}, {self.band_medium}, {self.band_high})"
            )
        if not self.hard_block_below <= self.band_low:
            raise ValueError("seller.hard_block_below must be <= seller.band_low")
        if self.weights is not None:
            total = sum(self.weights.values())
            if any(w < 0 for w in self.weights.values()) or abs(total - 1.0) > 1e-9:
                raise ValueError("seller.weights must be non-negative and sum to 1")
        return self


class FinanceSection(_Section):
    safety_buffer_pct: float = Field(ge=0, le=100)
    stale_after_days: int = Field(ge=1)


class NegSection(_Section):
    """Per-category, "sin definir" (unset) until the tenant supplies them."""

    target_discount: float | None = Field(default=None, ge=0, le=1)
    max_discount: float | None = Field(default=None, ge=0, le=1)
    max_rounds: int = Field(ge=1)

    @model_validator(mode="after")
    def _discount_order(self) -> NegSection:
        if (
            self.target_discount is not None
            and self.max_discount is not None
            and self.target_discount > self.max_discount
        ):
            raise ValueError("neg.target_discount must be <= neg.max_discount")
        return self


class GateSection(_Section):
    sla_hours: int = Field(ge=1)
    max_renegotiations: int = Field(ge=0)


class ApprovalSection(_Section):
    threshold: float | None = Field(default=None, ge=0)
    dual_control_above: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _dual_above_threshold(self) -> ApprovalSection:
        if (
            self.threshold is not None
            and self.dual_control_above is not None
            and self.dual_control_above < self.threshold
        ):
            raise ValueError("approval.dual_control_above must be >= approval.threshold")
        return self


class SigningSection(_Section):
    session_minutes: int = Field(ge=1)
    max_decisions_per_session: int = Field(ge=1)
    high_value_reauth_above: float | None = Field(default=None, ge=0)


class LlmRole(_Section):
    base_url: str
    model: str
    capabilities: tuple[str, ...] = ()


class LlmSection(_Section):
    roles: dict[str, LlmRole] | None = None


class TenantConfig(_Section):
    """Full typed configuration (all sections). Built from a resolved, validated mapping."""

    money: MoneySection = Field(default_factory=MoneySection)
    fx: FxSection
    sanity: SanitySection
    seller: SellerSection
    finance: FinanceSection
    neg: NegSection
    gate: GateSection
    approval: ApprovalSection
    signing: SigningSection
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
        "approval.threshold",
        "approval.dual_control_above",
        "signing.high_value_reauth_above",
        "llm.roles",
    }
)
"""Dotted paths that §7 marks as "sin definir" / "ver ADR". Used by tests and the resolver."""
