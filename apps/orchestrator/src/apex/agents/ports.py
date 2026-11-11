"""Ports the per-offer graph depends on (D4-06).

Every collaborator owned by another lane (DEV-2 signing/audit, DEV-3 engines, DEV-5 negotiation) or by a
later DEV-4 task (enrichment, finance nodes) is reached through a ``Protocol`` here. The graph never imports
those modules, so it can be built and tested before they exist and swapped to the real functions later.

Shapes follow issue #92 (signing/audit interface) and AGENTS.md section 4. The band enums mirror spec 3.3,
3.4 and 3.4.4; they are replaced by the DEV-3 domain types when those land. The graph never computes a
price, band, score or verdict: it only routes on what a port returns.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class PriceBand(StrEnum):
    NORMAL = "normal"
    ATYPICAL = "atypical"
    IMPLAUSIBLE = "implausible"
    INSUFFICIENT_REFERENCE = "insufficient_reference"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNTRUSTED = "untrusted"
    INSUFFICIENT_DATA = "insufficient_data"


class GateRoute(StrEnum):
    """Result of combining price and confidence (spec 3.4.4)."""

    NEGOTIATE = "negotiate"
    GATE = "gate"
    DISCARD = "discard"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TrustOutcome(_Frozen):
    band: ConfidenceBand
    score: int | None
    model_version: str
    detail: Any | None = None
    """The engine's full ``SellerConfidence`` (normalized signals, penalties, flags). Kept so the UI can
    answer "why this score?" with the engine's own numbers instead of an empty panel."""


class SanityOutcome(_Frozen):
    band: PriceBand
    config_version: str
    detail: Any | None = None
    """The engine's full ``PriceSanityCheck``: reference price, median, sample size, dispersion, band limits.
    Without it the sanity block has a band and no numbers behind it."""


class FitOutcome(_Frozen):
    verdict: Literal["within_budget", "stretch", "out_of_budget"]
    financials_stale: bool = False
    fx_provisional: bool = False
    landed_cost_total_minor: int | None = None
    """The engine's landed cost for the whole order, EUR minor units. ``None`` when it did not compute one.
    Kept so the dashboard can show the amount next to the verdict instead of recomputing it."""
    landed_cost: Any | None = None
    """The full ``LandedCostBreakdown`` (every line plus the total). The UI expands it line by line."""
    detail: Any | None = None
    """The engine's full ``FinancialFit`` (verdict plus its numeric reasons), ready for the contract."""


class GateOutcome(_Frozen):
    route: GateRoute
    reasons: list[str] = Field(default_factory=list)


class NegotiationOutcomeKind(StrEnum):
    """Closed set from ADR-900 (ADR-403 item 4), identical to DEV-5's ``NegotiationOutcome``.

    ``awaiting_human_approval``, ``awaiting_seller`` and ``in_progress`` are non-terminal: the graph pauses and
    calls again with the same idempotency key, and the effect ledger never caches them.
    """

    AGREED = "agreed"
    NO_AGREEMENT = "no_agreement"
    ESCALATED = "escalated"
    STOPPED_ANOMALOUS_PRICE = "stopped_anomalous_price"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    AWAITING_SELLER = "awaiting_seller"
    ABORTED = "aborted"
    IN_PROGRESS = "in_progress"


TERMINAL_OUTCOMES = frozenset(
    {
        NegotiationOutcomeKind.AGREED,
        NegotiationOutcomeKind.NO_AGREEMENT,
        NegotiationOutcomeKind.ESCALATED,
        NegotiationOutcomeKind.STOPPED_ANOMALOUS_PRICE,
        NegotiationOutcomeKind.ABORTED,
    }
)
GATE_OUTCOMES = frozenset(
    {NegotiationOutcomeKind.ESCALATED, NegotiationOutcomeKind.STOPPED_ANOMALOUS_PRICE}
)
REJECT_OUTCOMES = frozenset({NegotiationOutcomeKind.NO_AGREEMENT, NegotiationOutcomeKind.ABORTED})


GATE_QUOTE_REASON = "best_quote_above_target"
"""#241: the seller holds above the target; the engine escalates and reports the best quote."""


class NegotiationResult(_Frozen):
    """Result of one ``negotiate`` call. ``price_minor`` is the **unit** price.

    It is set for ``agreed`` and for the one escalation that shows the gate a number (#241:
    ``escalated`` with reason ``best_quote_above_target``). Every other outcome carries no price.
    """

    outcome: NegotiationOutcomeKind
    negotiation_id: str
    price_minor: int | None = None
    currency: str | None = None
    quantity: int | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _agreed_is_complete_and_only_agreed_has_a_price(self) -> NegotiationResult:
        # Compare by value: DEV-5's negotiator may return its own enum class with the same values.
        agreed = NegotiationOutcomeKind(self.outcome) is NegotiationOutcomeKind.AGREED
        complete = None not in (self.price_minor, self.currency, self.quantity)
        if agreed and not complete:
            raise ValueError("an agreed negotiation needs price_minor, currency and quantity")
        gate_quote = (
            NegotiationOutcomeKind(self.outcome) is NegotiationOutcomeKind.ESCALATED
            and self.reason == GATE_QUOTE_REASON
        )
        if not agreed and not gate_quote and self.price_minor is not None:
            raise ValueError("price_minor is only set when the outcome is agreed or the gate quote")
        if gate_quote and not complete:
            raise ValueError("the gate quote needs price_minor, currency and quantity")
        return self


class DecisionRef(_Frozen):
    id: str
    status: Literal["pending_signature", "signed", "rejected", "expired"]


class SignedDecisionView(_Frozen):
    """What the graph needs from a signed decision. ``payload`` is the signed canonical payload."""

    id: str
    type: str
    subject_ref: str
    payload: Mapping[str, Any]
    signer_count: int = Field(ge=1)


class PendingSignature(Exception):
    """Raised by ``DecisionPort.require_signed`` while a decision is not (fully) signed."""


class DecisionRejected(Exception):
    """Raised by ``DecisionPort.require_signed`` when the decision was rejected or expired."""


class OfferStep(Protocol):
    async def enrich(self, offer: Mapping[str, Any], *, tenant_id: str) -> dict[str, Any]: ...


class TrustPort(Protocol):
    async def score(self, offer: Mapping[str, Any], *, tenant_id: str) -> TrustOutcome: ...


class UnitPriceEur(_Frozen):
    """A negotiated price converted to EUR per unit (landed-cost basis is DEV-3's concern, not the graph's)."""

    unit_price_eur_minor: int
    fx_provisional: bool = False
    fx_as_of: str | None = None


class PriceNormalizer(Protocol):
    """Converts a negotiated unit price to EUR per unit with DEV-3 FX (``fx.convert``)."""

    async def to_eur_unit(
        self, *, price_minor: int, currency: str, tenant_id: str
    ) -> UnitPriceEur: ...


class SanityPort(Protocol):
    """``price_minor`` is in EUR minor units per unit, or ``None`` for the offer's own listed price."""

    async def check(
        self, offer: Mapping[str, Any], *, tenant_id: str, price_minor: int | None
    ) -> SanityOutcome: ...


class GateCombiner(Protocol):
    def combine(
        self, price_band: PriceBand, confidence_band: ConfidenceBand, *, tenant_id: str
    ) -> GateOutcome: ...


class FinancePort(Protocol):
    async def fit(self, offer: Mapping[str, Any], *, tenant_id: str) -> FitOutcome: ...


class NegotiationPort(Protocol):
    """Advance the negotiation of this offer and return at the next stop (ADR-900).

    ``idempotency_key`` is ``negotiate:<subject_ref>:<attempt>``. Calls with the same key continue the same
    negotiation, so a retry never sends a message twice. A new attempt (``renegotiate``) uses a new key.
    """

    async def negotiate(
        self, offer: Mapping[str, Any], *, tenant_id: str, idempotency_key: str
    ) -> NegotiationResult: ...


class ScoringPort(Protocol):
    async def score(self, offer: Mapping[str, Any], *, tenant_id: str) -> dict[str, Any]: ...


class DecisionPort(Protocol):
    """Subset of ``apex.signing.api`` used by the graph (issue #92). Async, tenant passed explicitly."""

    async def create_decision(
        self, type: str, subject_ref: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> DecisionRef: ...

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> SignedDecisionView: ...

    async def sign_service_event(
        self, service: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> str: ...


class AuditPort(Protocol):
    async def append(self, event: Mapping[str, Any], *, tenant_id: str) -> None: ...


class ConfigVersionPort(Protocol):
    def config_version(self, tenant_id: str) -> str: ...

    def max_renegotiations(self, tenant_id: str) -> int:
        """``gate.max_renegotiations``. Fails loudly when unset (ADR-900 Q7), never defaults."""
        ...


class EffectLedger(Protocol):
    """Runs a side effect at most once per key and replays its result afterwards.

    Graph nodes can run again after a crash or a resume. Every effect with an outside footprint (signing,
    audit, negotiation message, decision creation) goes through ``once`` so a replay never duplicates it.
    The production ledger is backed by Postgres (DEV-2 data layer); tests use the in-memory one.
    """

    async def once(
        self,
        key: str,
        effect: Callable[[], Awaitable[T]],
        *,
        cacheable: Callable[[T], bool] = ...,
    ) -> T: ...


__all__ = [
    "AuditPort",
    "ConfidenceBand",
    "ConfigVersionPort",
    "DecisionPort",
    "DecisionRejected",
    "DecisionRef",
    "EffectLedger",
    "FinancePort",
    "FitOutcome",
    "GATE_OUTCOMES",
    "GateCombiner",
    "GateOutcome",
    "GateRoute",
    "NegotiationOutcomeKind",
    "NegotiationPort",
    "NegotiationResult",
    "OfferStep",
    "PriceNormalizer",
    "PendingSignature",
    "PriceBand",
    "REJECT_OUTCOMES",
    "SanityOutcome",
    "SanityPort",
    "ScoringPort",
    "SignedDecisionView",
    "TERMINAL_OUTCOMES",
    "TrustOutcome",
    "TrustPort",
    "UnitPriceEur",
]
