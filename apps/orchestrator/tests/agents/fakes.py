"""Scriptable fakes for the per-offer graph ports. Every call is counted so tests can assert on effects."""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from apex.agents.ledger import InMemoryEffectLedger
from apex.agents.offer_graph import OfferGraphDeps
from apex.agents.ports import (
    ConfidenceBand,
    DecisionRef,
    DecisionRejected,
    FitOutcome,
    GateOutcome,
    GateRoute,
    NegotiationOutcomeKind,
    NegotiationResult,
    PendingSignature,
    PriceBand,
    SanityOutcome,
    SignedDecisionView,
    TrustOutcome,
    UnitPriceEur,
)

TENANT = "tenant-a"


@dataclass
class Calls:
    counts: Counter[str] = field(default_factory=Counter)

    def hit(self, name: str) -> None:
        self.counts[name] += 1

    def __getitem__(self, name: str) -> int:
        return self.counts[name]


class FakeEnrich:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    async def enrich(self, offer: Mapping[str, Any], *, tenant_id: str) -> dict[str, Any]:
        self.calls.hit("enrich")
        return {**offer, "enriched": True}


class FakeTrust:
    def __init__(self, calls: Calls, band: ConfidenceBand = ConfidenceBand.HIGH) -> None:
        self.calls, self.band = calls, band

    async def score(self, offer: Mapping[str, Any], *, tenant_id: str) -> TrustOutcome:
        self.calls.hit("trust")
        return TrustOutcome(band=self.band, score=80, model_version="trust-test")


class FakeSanity:
    def __init__(
        self,
        calls: Calls,
        band: PriceBand = PriceBand.NORMAL,
        rechecked: PriceBand | None = None,
    ) -> None:
        self.calls, self.band, self.rechecked = calls, band, rechecked or band

    async def check(
        self, offer: Mapping[str, Any], *, tenant_id: str, price_minor: int | None
    ) -> SanityOutcome:
        self.calls.hit("sanity" if price_minor is None else "resanity")
        band = self.band if price_minor is None else self.rechecked
        return SanityOutcome(band=band, config_version="cfg-1")


class TableCombiner:
    """Spec 3.4.4 as a test double. The real one is ``gate_matrix.combine`` (DEV-3)."""

    def combine(
        self, price_band: PriceBand, confidence_band: ConfidenceBand, *, tenant_id: str
    ) -> GateOutcome:
        if price_band is PriceBand.IMPLAUSIBLE or confidence_band is ConfidenceBand.UNTRUSTED:
            return GateOutcome(route=GateRoute.DISCARD, reasons=["discard"])
        if price_band is PriceBand.ATYPICAL and confidence_band in {
            ConfidenceBand.LOW,
            ConfidenceBand.INSUFFICIENT_DATA,
        }:
            return GateOutcome(route=GateRoute.DISCARD, reasons=["cheap_and_untrustworthy"])
        if price_band in {PriceBand.ATYPICAL, PriceBand.INSUFFICIENT_REFERENCE} or (
            confidence_band in {ConfidenceBand.LOW, ConfidenceBand.INSUFFICIENT_DATA}
        ):
            return GateOutcome(route=GateRoute.GATE, reasons=["grey_zone"])
        return GateOutcome(route=GateRoute.NEGOTIATE)


class AlwaysNegotiateCombiner:
    """A buggy combiner that waves everything through, to prove the graph does not trust it blindly."""

    def combine(
        self, price_band: PriceBand, confidence_band: ConfidenceBand, *, tenant_id: str
    ) -> GateOutcome:
        return GateOutcome(route=GateRoute.NEGOTIATE)


class FakeFinance:
    def __init__(self, calls: Calls, verdict: str = "within_budget") -> None:
        self.calls, self.verdict = calls, verdict

    async def fit(self, offer: Mapping[str, Any], *, tenant_id: str) -> FitOutcome:
        self.calls.hit("finance")
        return FitOutcome(verdict=self.verdict)  # type: ignore[arg-type]


class FakeNegotiation:
    """Scripted per-call results. The last one repeats. ``keys`` records every idempotency key used."""

    def __init__(self, calls: Calls, *results: NegotiationResult) -> None:
        self.calls = calls
        self.results = list(results) or [agreed()]
        self.keys: list[str] = []

    async def negotiate(
        self, offer: Mapping[str, Any], *, tenant_id: str, idempotency_key: str
    ) -> NegotiationResult:
        self.calls.hit("negotiation")
        self.keys.append(idempotency_key)
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


def agreed(price_minor: int = 900, currency: str = "EUR", quantity: int = 100) -> NegotiationResult:
    return NegotiationResult(
        outcome=NegotiationOutcomeKind.AGREED,
        negotiation_id="n1",
        price_minor=price_minor,
        currency=currency,
        quantity=quantity,
    )


def stopped(kind: NegotiationOutcomeKind) -> NegotiationResult:
    return NegotiationResult(outcome=kind, negotiation_id="n1", reason="test")


class FakePrices:
    """Converts at a fixed test rate so tests can see that the sanity check got the EUR price."""

    def __init__(self, calls: Calls, eur_per_unit_minor: dict[str, int] | None = None) -> None:
        self.calls = calls
        self.rates = eur_per_unit_minor or {"EUR": 1, "USD": 1}
        self.sanity_prices: list[int | None] = []

    async def to_eur_unit(self, *, price_minor: int, currency: str, tenant_id: str) -> UnitPriceEur:
        self.calls.hit("prices")
        return UnitPriceEur(unit_price_eur_minor=price_minor * self.rates[currency])


class FakeScoring:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    async def score(self, offer: Mapping[str, Any], *, tenant_id: str) -> dict[str, Any]:
        self.calls.hit("scoring")
        return {"rank": 1}


class FakeDecisions:
    """Decisions start ``pending_signature``; tests sign them explicitly, like a human would."""

    def __init__(self, calls: Calls) -> None:
        self.calls = calls
        self._ids = itertools.count(1)
        self.created: dict[str, dict[str, Any]] = {}
        self.signed: dict[str, dict[str, Any]] = {}
        self.rejected: set[str] = set()
        self.service_events: list[Mapping[str, Any]] = []

    async def create_decision(
        self, type: str, subject_ref: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> DecisionRef:
        self.calls.hit("create_decision")
        decision_id = f"d{next(self._ids)}"
        self.created[decision_id] = {"type": type, "subject_ref": subject_ref, "payload": payload}
        return DecisionRef(id=decision_id, status="pending_signature")

    def sign(self, decision_id: str, **payload_overrides: Any) -> None:
        record = self.created[decision_id]
        self.signed[decision_id] = {
            **record,
            "payload": {**record["payload"], **payload_overrides},
        }

    def reject(self, decision_id: str) -> None:
        self.rejected.add(decision_id)

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> SignedDecisionView:
        self.calls.hit("require_signed")
        if decision_id in self.rejected:
            raise DecisionRejected(decision_id)
        if decision_id not in self.signed:
            raise PendingSignature(decision_id)
        record = self.signed[decision_id]
        return SignedDecisionView(
            id=decision_id,
            type=record["type"],
            subject_ref=record["subject_ref"],
            payload=record["payload"],
            signer_count=1,
        )

    async def sign_service_event(
        self, service: str, payload: Mapping[str, Any], *, tenant_id: str
    ) -> str:
        self.calls.hit("service_signature")
        self.service_events.append(payload)
        return f"sig-{len(self.service_events)}"

    def pending_id(self) -> str:
        pending = [d for d in self.created if d not in self.signed and d not in self.rejected]
        assert len(pending) == 1, pending
        return pending[0]


class FakeAudit:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls
        self.events: list[Mapping[str, Any]] = []

    async def append(self, event: Mapping[str, Any], *, tenant_id: str) -> None:
        self.calls.hit("audit")
        self.events.append(event)


class FakeConfig:
    def __init__(self, max_renegotiations: int = 2) -> None:
        self._max = max_renegotiations

    def config_version(self, tenant_id: str) -> str:
        return "cfg-1"

    def max_renegotiations(self, tenant_id: str) -> int:
        return self._max


@dataclass
class Rig:
    deps: OfferGraphDeps
    calls: Calls
    decisions: FakeDecisions
    audit: FakeAudit
    ledger: InMemoryEffectLedger
    negotiation: FakeNegotiation
    prices: FakePrices


def make_rig(
    *,
    trust: ConfidenceBand = ConfidenceBand.HIGH,
    price: PriceBand = PriceBand.NORMAL,
    rechecked: PriceBand | None = None,
    combiner: Any = None,
    negotiation: tuple[NegotiationResult, ...] = (),
    max_renegotiations: int = 2,
    verdict: str = "within_budget",
) -> Rig:
    calls = Calls()
    decisions = FakeDecisions(calls)
    audit = FakeAudit(calls)
    ledger = InMemoryEffectLedger()
    deps = OfferGraphDeps(
        enrich=FakeEnrich(calls),
        trust=FakeTrust(calls, trust),
        sanity=FakeSanity(calls, price, rechecked),
        combiner=combiner or TableCombiner(),
        finance=FakeFinance(calls, verdict),
        negotiation=FakeNegotiation(calls, *negotiation),
        prices=FakePrices(calls),
        scoring=FakeScoring(calls),
        decisions=decisions,
        audit=audit,
        config=FakeConfig(max_renegotiations),
        ledger=ledger,
    )
    return Rig(deps, calls, decisions, audit, ledger, deps.negotiation, deps.prices)  # type: ignore[arg-type]
