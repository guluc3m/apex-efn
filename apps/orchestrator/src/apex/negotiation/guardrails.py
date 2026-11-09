"""Deterministic negotiation guardrails (D5-07, spec 3.6 "Guardarraíles duros").

Every message the agent drafts goes through :func:`check_outgoing` **before** it is sent, and every
seller message goes through :func:`check_incoming` before the agent drafts a reply. Both are pure
functions: limits come from :class:`GuardrailLimits` (built from tenant config and the buyer profile by
the caller), runtime counters from :class:`ConversationState`, and time from the caller. The LLM never
decides a price or a limit; this module decides whether its draft may leave the building.

A blocked outgoing draft is never "fixed" here. The engine either redrafts, falls back to a templated
message, or escalates to a human.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from apex.negotiation.text import (
    Counterpart,
    TextPrice,
    asks_for_sensitive_data,
    find_counterparts,
    find_percentages,
    find_prices,
    find_quantities,
    has_binding_commitment,
    has_closing_pressure,
    has_off_platform_contact,
    has_off_platform_payment,
    has_sensitive_data,
)

__all__ = [
    "BP_DENOMINATOR",
    "ConversationState",
    "Counterpart",
    "GuardrailLimits",
    "GuardrailVerdict",
    "Hit",
    "HitCode",
    "IncomingVerdict",
    "Severity",
    "check_incoming",
    "check_outgoing",
    "discount_bp",
    "fraction_to_bp",
    "price_ceiling_minor",
    "price_floor_minor",
]

BP_DENOMINATOR = 10_000


class Severity(StrEnum):
    BLOCK = "block"
    """The draft must not be sent; the engine may redraft."""
    ESCALATE = "escalate"
    """Stop the agent and hand the conversation to a human (gate queue)."""
    NOTICE = "notice"
    """Does not stop the agent but changes what it must do next (recorded on the negotiation)."""


class HitCode(StrEnum):
    # Outgoing (drafts)
    OFFER_BELOW_FLOOR = "offer_below_floor"
    OFFER_ABOVE_CEILING = "offer_above_ceiling"
    MAX_DISCOUNT_EXCEEDED = "max_discount_exceeded"
    PERCENT_DISCOUNT_EXCEEDED = "percent_discount_exceeded"
    WRONG_CURRENCY = "wrong_currency"
    VOLUME_EXCEEDED = "volume_exceeded"
    UNAUTHORIZED_COUNTERPART = "unauthorized_counterpart"
    BINDING_COMMITMENT = "binding_commitment"
    SENSITIVE_DATA_IN_DRAFT = "sensitive_data_in_draft"
    OFF_PLATFORM_CONTACT_IN_DRAFT = "off_platform_contact_in_draft"
    MESSAGE_TOO_LONG = "message_too_long"
    EMPTY_MESSAGE = "empty_message"
    MAX_ROUNDS_REACHED = "max_rounds_reached"
    TOKEN_BUDGET_EXHAUSTED = "token_budget_exhausted"
    ACCOUNT_RATE_LIMITED = "account_rate_limited"
    SELLER_RATE_LIMITED = "seller_rate_limited"
    HUMAN_IN_CONTROL = "human_in_control"
    # Incoming (seller messages)
    SELLER_ASKS_SENSITIVE_DATA = "seller_asks_sensitive_data"
    SELLER_OFF_PLATFORM_PAYMENT = "seller_off_platform_payment"
    SELLER_OFF_PLATFORM_CONTACT = "seller_off_platform_contact"
    SELLER_CLOSING_PRESSURE = "seller_closing_pressure"
    SELLER_UNSUPPORTED_CURRENCY = "seller_unsupported_currency"


@dataclass(frozen=True, slots=True)
class Hit:
    code: HitCode
    severity: Severity
    detail: str


@dataclass(frozen=True, slots=True)
class GuardrailLimits:
    """Hard limits for one conversation. Built by the caller from tenant config and the buyer profile.

    Discounts are basis points of the reference price (``1000`` = 10%). No field has a default: a
    business limit that is not configured must stop the negotiation upstream (AGENTS.md rule 0.6).
    """

    reference_price_minor: int
    """Unit price the discount is measured against: the listed unit price in ``currency``."""
    currency: str
    max_discount_bp: int
    """``neg.max_discount``: the buyer never asks for more than this discount."""
    max_quantity: int
    """Requested volume: the agent never commits to more units than the buyer asked for."""
    allowed_counterparts: frozenset[Counterpart]
    """Counterparts the buyer profile authorises (spec 3.1). Empty means none."""
    supported_currencies: frozenset[str]
    max_rounds: int
    """``neg.max_rounds``: agent messages per conversation."""
    max_tokens: int
    """LLM tokens per conversation."""
    max_messages_per_hour: int
    """Agent messages per platform account in any rolling hour.

    D5-08 applies the same configured number to one more scope: the agent never sends more than this many
    messages **to the same seller account** in any rolling hour, across missions. Same key, stricter scope:
    no new business number is introduced (AGENTS.md rule 0.6).
    """
    max_message_chars: int

    def __post_init__(self) -> None:
        if self.reference_price_minor <= 0:
            raise ValueError("reference_price_minor must be positive")
        if not 0 <= self.max_discount_bp < BP_DENOMINATOR:
            raise ValueError("max_discount_bp must be in [0, 10000)")
        for name in (
            "max_quantity",
            "max_rounds",
            "max_tokens",
            "max_messages_per_hour",
            "max_message_chars",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.currency not in self.supported_currencies:
            raise ValueError(f"negotiation currency {self.currency} is not supported")


@dataclass(frozen=True, slots=True)
class ConversationState:
    """Runtime counters, owned by the engine and persisted with the negotiation."""

    rounds_sent: int = 0
    tokens_used: int = 0
    human_in_control: bool = False
    account_sends: Sequence[datetime] = field(default_factory=tuple)
    """Timestamps of agent messages sent from this platform account (all conversations)."""
    seller_sends: Sequence[datetime] = field(default_factory=tuple)
    """Timestamps of agent messages sent to this seller account (all missions, D5-08 anti-abuse)."""


@dataclass(frozen=True, slots=True)
class GuardrailVerdict:
    hits: tuple[Hit, ...]
    prices: tuple[TextPrice, ...]
    quantities: tuple[int, ...]
    counterparts: frozenset[Counterpart]

    @property
    def allowed(self) -> bool:
        return not self.hits

    @property
    def escalate(self) -> bool:
        return any(h.severity is Severity.ESCALATE for h in self.hits)

    @property
    def codes(self) -> frozenset[HitCode]:
        return frozenset(h.code for h in self.hits)


@dataclass(frozen=True, slots=True)
class IncomingVerdict:
    hits: tuple[Hit, ...]
    prices: tuple[TextPrice, ...]

    @property
    def escalate(self) -> bool:
        return any(h.severity is Severity.ESCALATE for h in self.hits)

    @property
    def codes(self) -> frozenset[HitCode]:
        return frozenset(h.code for h in self.hits)


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def price_floor_minor(limits: GuardrailLimits) -> int:
    """Lowest unit price the agent may propose: reference minus ``max_discount``, rounded up (safe side)."""
    keep = BP_DENOMINATOR - limits.max_discount_bp
    return _ceil_div(limits.reference_price_minor * keep, BP_DENOMINATOR)


def price_ceiling_minor(limits: GuardrailLimits) -> int:
    """Highest unit price the agent may propose: the reference itself. Proposing more is never useful."""
    return limits.reference_price_minor


def discount_bp(reference_minor: int, price_minor: int) -> int:
    """Discount of ``price`` against ``reference`` in basis points, rounded up (conservative)."""
    if reference_minor <= 0:
        raise ValueError("reference must be positive")
    return _ceil_div((reference_minor - price_minor) * BP_DENOMINATOR, reference_minor)


def fraction_to_bp(value: float | str | Decimal) -> int:
    """Converts a config fraction (``neg.max_discount`` = ``0.12``) to basis points, rounding down.

    Rounding down makes the guardrail stricter, never looser, than the configured limit.
    """
    bp = Decimal(str(value)) * BP_DENOMINATOR
    if not Decimal(0) <= bp < BP_DENOMINATOR:
        raise ValueError("fraction must be in [0, 1)")
    return int(bp.to_integral_value(rounding=ROUND_FLOOR))


def _sends_in_last_hour(sends: Sequence[datetime], now: datetime) -> int:
    window_start = now - timedelta(hours=1)
    return sum(1 for t in sends if window_start < t <= now)


def check_outgoing(
    text: str,
    limits: GuardrailLimits,
    state: ConversationState,
    *,
    now: datetime,
    draft_tokens: int = 0,
) -> GuardrailVerdict:
    """Checks a drafted message before it is sent. ``allowed`` must be true to send it.

    ``draft_tokens`` is the LLM usage that produced this draft (counted against the conversation budget).
    """
    hits: list[Hit] = []

    def hit(code: HitCode, severity: Severity, detail: str) -> None:
        hits.append(Hit(code, severity, detail))

    # Conversation-level limits first: when one is hit, nothing else matters.
    if state.human_in_control:
        hit(HitCode.HUMAN_IN_CONTROL, Severity.BLOCK, "a human holds the conversation")
    if state.rounds_sent >= limits.max_rounds:
        hit(
            HitCode.MAX_ROUNDS_REACHED,
            Severity.ESCALATE,
            f"{state.rounds_sent}/{limits.max_rounds} rounds",
        )
    if state.tokens_used + draft_tokens > limits.max_tokens:
        hit(
            HitCode.TOKEN_BUDGET_EXHAUSTED,
            Severity.ESCALATE,
            f"{state.tokens_used + draft_tokens}/{limits.max_tokens} tokens",
        )
    recent = _sends_in_last_hour(state.account_sends, now)
    if recent >= limits.max_messages_per_hour:
        hit(
            HitCode.ACCOUNT_RATE_LIMITED,
            Severity.BLOCK,
            f"{recent}/{limits.max_messages_per_hour} messages in the last hour",
        )
    to_seller = _sends_in_last_hour(state.seller_sends, now)
    if to_seller >= limits.max_messages_per_hour:
        hit(
            HitCode.SELLER_RATE_LIMITED,
            Severity.BLOCK,
            f"{to_seller}/{limits.max_messages_per_hour} messages to this seller in the last hour",
        )

    stripped = text.strip()
    if not stripped:
        hit(HitCode.EMPTY_MESSAGE, Severity.BLOCK, "empty draft")
    if len(text) > limits.max_message_chars:
        hit(
            HitCode.MESSAGE_TOO_LONG,
            Severity.BLOCK,
            f"{len(text)}/{limits.max_message_chars} chars",
        )

    prices = tuple(find_prices(text))
    floor = price_floor_minor(limits)
    ceiling = price_ceiling_minor(limits)
    for p in prices:
        if p.currency != limits.currency:
            hit(
                HitCode.WRONG_CURRENCY,
                Severity.BLOCK,
                f"{p.raw}: negotiation runs in {limits.currency}",
            )
            continue
        if p.minor < floor:
            hit(
                HitCode.OFFER_BELOW_FLOOR,
                Severity.BLOCK,
                f"{p.raw} is below the floor {floor} ({limits.max_discount_bp} bp max discount)",
            )
            hit(
                HitCode.MAX_DISCOUNT_EXCEEDED,
                Severity.BLOCK,
                f"asks {discount_bp(limits.reference_price_minor, p.minor)} bp > {limits.max_discount_bp} bp",
            )
        elif p.minor > ceiling:
            hit(
                HitCode.OFFER_ABOVE_CEILING,
                Severity.BLOCK,
                f"{p.raw} is above the reference {ceiling}",
            )

    for bp in find_percentages(text):
        if bp > limits.max_discount_bp:
            hit(
                HitCode.PERCENT_DISCOUNT_EXCEEDED,
                Severity.BLOCK,
                f"{bp} bp mentioned > {limits.max_discount_bp} bp max discount",
            )

    quantities = tuple(find_quantities(text))
    for q in quantities:
        if q > limits.max_quantity:
            hit(
                HitCode.VOLUME_EXCEEDED,
                Severity.BLOCK,
                f"{q} units > requested {limits.max_quantity}",
            )

    counterparts = find_counterparts(text)
    if any(q > limits.max_quantity for q in quantities):
        counterparts = counterparts | {Counterpart.HIGHER_VOLUME}
    for c in sorted(counterparts - limits.allowed_counterparts):
        hit(
            HitCode.UNAUTHORIZED_COUNTERPART,
            Severity.BLOCK,
            f"{c.value} is not authorised by the profile",
        )

    if has_binding_commitment(text):
        hit(
            HitCode.BINDING_COMMITMENT,
            Severity.BLOCK,
            "the agent negotiates, it never accepts or orders",
        )
    if has_sensitive_data(text):
        hit(
            HitCode.SENSITIVE_DATA_IN_DRAFT,
            Severity.ESCALATE,
            "draft contains bank, card or tax data",
        )
    if has_off_platform_contact(text) or has_off_platform_payment(text):
        hit(
            HitCode.OFF_PLATFORM_CONTACT_IN_DRAFT,
            Severity.BLOCK,
            "draft moves contact or payment off the platform",
        )

    return GuardrailVerdict(tuple(hits), prices, quantities, counterparts)


def check_incoming(text: str, *, supported_currencies: frozenset[str]) -> IncomingVerdict:
    """Classifies a seller message. Escalations stop the agent before it drafts a reply.

    Prices in the message are returned so the engine can re-check them with the sanity engine; this
    module does not judge whether a price is anomalous (that is DEV-3's ``sanity.check``).
    """
    hits: list[Hit] = []
    if asks_for_sensitive_data(text):
        hits.append(
            Hit(
                HitCode.SELLER_ASKS_SENSITIVE_DATA,
                Severity.ESCALATE,
                "seller asks for sensitive data",
            )
        )
    if has_off_platform_payment(text):
        hits.append(
            Hit(
                HitCode.SELLER_OFF_PLATFORM_PAYMENT,
                Severity.ESCALATE,
                "seller asks for off-platform payment",
            )
        )
    if has_off_platform_contact(text):
        hits.append(
            Hit(
                HitCode.SELLER_OFF_PLATFORM_CONTACT,
                Severity.ESCALATE,
                "seller moves contact off the platform",
            )
        )
    if has_closing_pressure(text):
        hits.append(
            Hit(
                HitCode.SELLER_CLOSING_PRESSURE,
                Severity.NOTICE,
                "closing signal: never accept, summarise and leave the decision to a human",
            )
        )
    prices = tuple(find_prices(text))
    unsupported = sorted({p.currency for p in prices} - supported_currencies)
    if unsupported:
        hits.append(
            Hit(
                HitCode.SELLER_UNSUPPORTED_CURRENCY,
                Severity.NOTICE,
                f"quoted in {', '.join(unsupported)}: ask for a quote in a supported currency",
            )
        )
    return IncomingVerdict(tuple(hits), prices)
