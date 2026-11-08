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

from pydantic import BaseModel, ConfigDict, Field

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


class SanityOutcome(_Frozen):
    band: PriceBand
    config_version: str


class FitOutcome(_Frozen):
    verdict: Literal["within_budget", "stretch", "out_of_budget"]
    financials_stale: bool = False
    fx_provisional: bool = False


class GateOutcome(_Frozen):
    route: GateRoute
    reasons: list[str] = Field(default_factory=list)


class NegotiationResult(_Frozen):
    outcome: str
    price_minor: int | None
    currency: str | None


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


class SanityPort(Protocol):
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


class EffectLedger(Protocol):
    """Runs a side effect at most once per key and replays its result afterwards.

    Graph nodes can run again after a crash or a resume. Every effect with an outside footprint (signing,
    audit, negotiation message, decision creation) goes through ``once`` so a replay never duplicates it.
    The production ledger is backed by Postgres (DEV-2 data layer); tests use the in-memory one.
    """

    async def once(self, key: str, effect: Callable[[], Awaitable[T]]) -> T: ...


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
    "GateCombiner",
    "GateOutcome",
    "GateRoute",
    "NegotiationPort",
    "NegotiationResult",
    "OfferStep",
    "PendingSignature",
    "PriceBand",
    "SanityOutcome",
    "SanityPort",
    "ScoringPort",
    "SignedDecisionView",
    "TrustOutcome",
    "TrustPort",
]
