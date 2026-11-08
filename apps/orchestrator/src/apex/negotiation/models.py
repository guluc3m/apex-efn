"""Negotiation domain types (D5-07b). Money is integer minor units; discounts are basis points."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apex.negotiation.guardrails import BP_DENOMINATOR, Counterpart, GuardrailLimits


class NegotiationOutcome(StrEnum):
    """Status of a negotiation as seen by the mission graph (ADR-900, ADR-403 item 4)."""

    AGREED = "agreed"
    NO_AGREEMENT = "no_agreement"
    ESCALATED = "escalated"
    STOPPED_ANOMALOUS_PRICE = "stopped_anomalous_price"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    AWAITING_SELLER = "awaiting_seller"
    ABORTED = "aborted"
    IN_PROGRESS = "in_progress"


PHASE1_COUNTERPARTS = frozenset({Counterpart.HIGHER_VOLUME, Counterpart.FRAMEWORK_CONTRACT})
"""Counterparts a profile may enable in Phase 1 (ADR-900, Q15). The rest wait for Phase 2."""

TERMINAL_OUTCOMES = frozenset(
    {
        NegotiationOutcome.AGREED,
        NegotiationOutcome.NO_AGREEMENT,
        NegotiationOutcome.ESCALATED,
        NegotiationOutcome.STOPPED_ANOMALOUS_PRICE,
        NegotiationOutcome.ABORTED,
    }
)


class SanityBand(StrEnum):
    """Price band returned by DEV-3's sanity engine (spec 3.3)."""

    NORMAL = "normal"
    ATYPICAL = "atypical"
    IMPLAUSIBLE = "implausible"
    INSUFFICIENT_REFERENCE = "insufficient_reference"


class Intent(StrEnum):
    """What the next agent message must do. Chosen by the playbook, never by the LLM (spec 3.6)."""

    OPEN = "open"
    """Steps 1 and 3: professional context and a request for volume tiers before any discount."""
    REQUEST_PRICE = "request_price"
    ANCHOR = "anchor"
    """Step 2: a low but justified anchor."""
    COUNTER = "counter"
    """Step 4: the next rung of the decreasing counter-offer ladder."""
    REQUEST_CURRENCY = "request_currency"
    """Step 8: ask for a quote in the negotiation currency."""
    SUMMARY = "summary"
    """Step 7: written summary, ask the seller to confirm in writing. Never an acceptance."""


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: Intent
    price_minor: int | None = None
    """The only price the message may contain. Decided in code."""


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    unit_price_minor: int = Field(ge=0)
    currency: str
    at_round: int


class NegotiationContext(BaseModel):
    """Professional context for the opening message (spec 3.6 step 1). Free of financial data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product_title: str
    deadline: str | None = None
    destination: str | None = None
    recurring: bool = False


class NegotiationParams(BaseModel):
    """Everything the engine needs, resolved by the caller from tenant config and the buyer profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str
    reference_price_minor: int = Field(gt=0)
    """Listed unit price in ``currency``: the base for discounts and the guardrail ceiling."""
    quantity: int = Field(gt=0)
    target_discount_bp: int = Field(ge=0, lt=BP_DENOMINATOR)
    max_discount_bp: int = Field(ge=0, lt=BP_DENOMINATOR)
    max_rounds: int = Field(ge=2)
    max_tokens: int = Field(gt=0)
    max_messages_per_hour: int = Field(gt=0)
    max_message_chars: int = Field(gt=0)
    allowed_counterparts: frozenset[Counterpart] = frozenset()
    supported_currencies: frozenset[str]
    language: Literal["en", "es"] = "en"
    semi_automatic: bool = True
    """Phase 1 (spec 10): every drafted message waits for a human approval."""
    max_drafts: int = Field(default=2, ge=1)
    """LLM drafts tried per message before falling back to the deterministic template."""
    context: NegotiationContext

    @model_validator(mode="after")
    def _check(self) -> NegotiationParams:
        if self.target_discount_bp > self.max_discount_bp:
            raise ValueError("target_discount must not exceed max_discount")
        if self.currency not in self.supported_currencies:
            raise ValueError(f"negotiation currency {self.currency} is not supported")
        forbidden = self.allowed_counterparts - PHASE1_COUNTERPARTS
        if forbidden:
            names = ", ".join(sorted(c.value for c in forbidden))
            raise ValueError(f"counterparts not allowed in Phase 1 (ADR-900 Q15): {names}")
        return self

    def limits(self) -> GuardrailLimits:
        return GuardrailLimits(
            reference_price_minor=self.reference_price_minor,
            currency=self.currency,
            max_discount_bp=self.max_discount_bp,
            max_quantity=self.quantity,
            allowed_counterparts=self.allowed_counterparts,
            supported_currencies=self.supported_currencies,
            max_rounds=self.max_rounds,
            max_tokens=self.max_tokens,
            max_messages_per_hour=self.max_messages_per_hour,
            max_message_chars=self.max_message_chars,
        )


class TranscriptMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    role: Literal["agent", "seller", "human"]
    text: str
    at: datetime
    intent: Intent | None = None
    approved_by: str | None = None


class PendingDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    plan: Plan
    text: str
    tokens: int
    created_at: datetime
    source: Literal["llm", "template"]


class NegotiationSession(BaseModel):
    """Full, serialisable state of one negotiation. Persisted after every step."""

    id: str
    tenant_id: str
    platform: str
    seller_id: str
    product_id: str
    account_id: str
    config_version: str
    params: NegotiationParams
    status: NegotiationOutcome = NegotiationOutcome.IN_PROGRESS
    chat_id: str | None = None
    last_seller_seq: int = 0
    ladder: list[int] = Field(default_factory=list)
    next_rung: int = 0
    rounds_sent: int = 0
    tokens_used: int = 0
    asked_for_price: bool = False
    quotes: list[Quote] = Field(default_factory=list)
    agreed: Quote | None = None
    summary_sent: bool = False
    pending: PendingDraft | None = None
    human_in_control: bool = False
    transcript: list[TranscriptMessage] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
    guardrail_hits: list[str] = Field(default_factory=list)
    stop_reason: str | None = None

    @property
    def best_quote(self) -> Quote | None:
        same = [q for q in self.quotes if q.currency == self.params.currency]
        return min(same, key=lambda q: q.unit_price_minor) if same else None

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_OUTCOMES
