"""Per-offer LangGraph (spec section 4, D4-06).

The graph is the only place that decides *order*; every number comes from a port (DEV-3 engines, DEV-5
negotiator, DEV-2 signing). Guarantees:

- **Trust + sanity -> negotiation is structural.** ``negotiate`` has one incoming edge, from
  ``check_financial``, and ``check_financial`` is reached only from ``route_pre`` (combiner said negotiate and
  the price band is ``normal``) or from ``gate_wait`` after ``require_signed`` succeeded. The negotiate node
  also refuses to run without ``negotiation_cleared`` (defence in depth, criterion 12).
- **Human gates are interrupts that resume only after ``require_signed``.** A resume with the decision
  still unsigned just pauses again.
- **Transitions are checked and idempotent.** Every move is validated against ``ALLOWED``; every effect with
  an outside footprint (decision creation, service signature, audit event, negotiation) goes through the
  ``EffectLedger`` keyed by offer and step, so a resumed run never duplicates a message or a signature.
- **No clock, no randomness, no thresholds.** The band names are the only vocabulary shared with the engines.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from apex.agents.offer_state import (
    OfferState,
    OfferStatus,
    check_transition,
)
from apex.agents.ports import (
    GATE_OUTCOMES,
    REJECT_OUTCOMES,
    TERMINAL_OUTCOMES,
    AuditPort,
    ConfidenceBand,
    ConfigVersionPort,
    DecisionPort,
    DecisionRejected,
    EffectLedger,
    FinancePort,
    GateCombiner,
    GateRoute,
    NegotiationOutcomeKind,
    NegotiationPort,
    OfferStep,
    PendingSignature,
    PriceBand,
    PriceNormalizer,
    SanityPort,
    ScoringPort,
    SignedDecisionView,
    TrustPort,
)

SERVICE_NAME = "mission-graph"
UNBLOCK_DECISION = "gate_unblock"
DEAL_DECISION = "deal_action"

# Price bands that must never reach the negotiator without a signed unblock, whatever the combiner says.
_NEVER_AUTO_NEGOTIATE = frozenset(
    {PriceBand.ATYPICAL, PriceBand.IMPLAUSIBLE, PriceBand.INSUFFICIENT_REFERENCE}
)


class NegotiationNotCleared(Exception):
    """The negotiate node was entered without clearance. Indicates a broken graph, never a data issue."""


class UnknownNegotiationOutcome(Exception):
    """The negotiator returned an outcome outside the closed set agreed in ADR-900."""

    def __init__(self, value: str) -> None:
        super().__init__(f"unknown negotiation outcome {value!r}; see ADR-900 / ADR-403")
        self.value = value


class InvalidSignedDecision(Exception):
    """A signed decision does not match the offer or action it is supposed to authorize."""


@dataclass(frozen=True)
class OfferGraphDeps:
    enrich: OfferStep
    trust: TrustPort
    sanity: SanityPort
    combiner: GateCombiner
    finance: FinancePort
    negotiation: NegotiationPort
    prices: PriceNormalizer
    scoring: ScoringPort
    decisions: DecisionPort
    audit: AuditPort
    config: ConfigVersionPort
    ledger: EffectLedger


def subject_ref(state: OfferState) -> str:
    return f"offer:{state['mission_id']}:{state['offer_id']}"


def initial_state(
    *, mission_id: str, offer_id: str, tenant_id: str, offer: Mapping[str, Any]
) -> OfferState:
    return OfferState(
        mission_id=mission_id,
        offer_id=offer_id,
        tenant_id=tenant_id,
        offer=dict(offer),
        status=OfferStatus.DISCOVERED.value,
        history=[OfferStatus.DISCOVERED.value],
        reject_reason=None,
        negotiation_cleared=False,
        negotiation_attempt=1,
        purchase_blocked=[],
        gate_decision_id=None,
        human_decision_id=None,
        human_action=None,
    )


def thread_id(mission_id: str, offer_id: str) -> str:
    return f"{mission_id}:{offer_id}"


def build_offer_graph(
    deps: OfferGraphDeps, *, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[OfferState, None, OfferState, OfferState]:
    """Compile the per-offer graph. Pass a Postgres checkpointer in production, ``InMemorySaver`` in tests."""

    async def move(
        state: OfferState,
        target: OfferStatus,
        *,
        source: OfferStatus | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        source = source or OfferStatus(state["status"])
        check_transition(source, target)
        key = f"{state['mission_id']}:{state['offer_id']}:{source.value}->{target.value}"
        event = {
            "mission_id": state["mission_id"],
            "offer_id": state["offer_id"],
            "from": source.value,
            "to": target.value,
            "config_version": state.get("config_version", ""),
            "reason": reason,
        }

        async def emit() -> str:
            signature_ref = await deps.decisions.sign_service_event(
                SERVICE_NAME, event, tenant_id=state["tenant_id"]
            )
            await deps.audit.append(
                {**event, "service_signature": signature_ref}, tenant_id=state["tenant_id"]
            )
            return signature_ref

        await deps.ledger.once(f"transition:{key}", emit)
        history = state.get("history", [])
        if not history or history[-1] != source.value:
            history = [*history, source.value]
        update: dict[str, Any] = {"status": target.value, "history": [*history, target.value]}
        if reason is not None:
            update["reject_reason"] = reason
        return update

    async def start(state: OfferState) -> dict[str, Any]:
        return {"config_version": deps.config.config_version(state["tenant_id"])}

    async def enrich(state: OfferState) -> dict[str, Any]:
        enriched = await deps.ledger.once(
            f"enrich:{subject_ref(state)}",
            lambda: deps.enrich.enrich(state["offer"], tenant_id=state["tenant_id"]),
        )
        return {"offer": enriched, **await move(state, OfferStatus.ENRICHED)}

    async def score_trust(state: OfferState) -> dict[str, Any]:
        outcome = await deps.trust.score(state["offer"], tenant_id=state["tenant_id"])
        return {
            "trust": outcome.model_dump(mode="json"),
            **await move(state, OfferStatus.TRUST_SCORED),
        }

    async def check_sanity(state: OfferState) -> dict[str, Any]:
        outcome = await deps.sanity.check(
            state["offer"], tenant_id=state["tenant_id"], price_minor=None
        )
        return {
            "sanity": outcome.model_dump(mode="json"),
            **await move(state, OfferStatus.SANITY_CHECKED),
        }

    def _route(state: OfferState) -> tuple[GateRoute, list[str]]:
        price = PriceBand(state["sanity"]["band"])
        confidence = ConfidenceBand(state["trust"]["band"])
        outcome = deps.combiner.combine(price, confidence, tenant_id=state["tenant_id"])
        reasons = list(outcome.reasons)
        if outcome.route is GateRoute.NEGOTIATE and price in _NEVER_AUTO_NEGOTIATE:
            reasons.append("graph_override:price_band_requires_signed_unblock")
            return GateRoute.GATE, reasons
        return outcome.route, reasons

    async def route_pre(state: OfferState) -> dict[str, Any]:
        route, reasons = _route(state)
        gate = {"route": route.value, "reasons": reasons, "stage": "pre"}
        if route is GateRoute.NEGOTIATE:
            return {"gate": gate, "gate_stage": "pre", "negotiation_cleared": True}
        if route is GateRoute.GATE:
            update = await move(state, OfferStatus.GATE_PENDING)
            return {"gate": gate, "gate_stage": "pre", "negotiation_cleared": False, **update}
        update = await move(state, OfferStatus.REJECTED, reason="gate_discard")
        return {"gate": gate, "gate_stage": "pre", "negotiation_cleared": False, **update}

    def after_route_pre(state: OfferState) -> str:
        route = state["gate"]["route"]
        if route == GateRoute.NEGOTIATE.value and state.get("negotiation_cleared"):
            return "check_financial"
        if route == GateRoute.GATE.value:
            return "gate_wait"
        return END

    async def _await_signed(
        state: OfferState, decision_type: str, payload: Mapping[str, Any], key: str
    ) -> SignedDecisionView:
        decision = await deps.ledger.once(
            f"decision:{key}",
            lambda: deps.decisions.create_decision(
                decision_type, subject_ref(state), payload, tenant_id=state["tenant_id"]
            ),
        )
        while True:
            try:
                signed = await deps.decisions.require_signed(
                    decision.id, tenant_id=state["tenant_id"]
                )
                break
            except PendingSignature:
                interrupt(
                    {
                        "kind": "awaiting_signature",
                        "decision_id": decision.id,
                        "decision_type": decision_type,
                        "subject_ref": subject_ref(state),
                    }
                )
        if signed.type != decision_type or signed.subject_ref != subject_ref(state):
            raise InvalidSignedDecision(
                f"decision {signed.id} does not authorize {decision_type} for {subject_ref(state)}"
            )
        return signed

    async def _fit(state: OfferState) -> dict[str, Any]:
        stage = state.get("gate_stage", "pre")
        outcome = await deps.ledger.once(
            f"fit:{subject_ref(state)}:{stage}",
            lambda: deps.finance.fit(state["offer"], tenant_id=state["tenant_id"]),
        )
        dumped: dict[str, Any] = outcome.model_dump(mode="json")
        return dumped

    async def _gate_payload(state: OfferState, stage: str) -> dict[str, Any]:
        return {
            "stage": stage,
            "attempt": state.get("negotiation_attempt", 1),
            "offer_id": state["offer_id"],
            "mission_id": state["mission_id"],
            "price_sanity": state.get("sanity", {}),
            "seller_confidence": state.get("trust", {}),
            "financial_fit": state.get("finance") or await _fit(state),
            "negotiation": state.get("negotiation", {}),
            "gate_reasons": state.get("gate", {}).get("reasons", []),
            "config_version": state.get("config_version", ""),
        }

    async def gate_wait(state: OfferState) -> dict[str, Any]:
        stage = state["gate_stage"]
        attempt = state.get("negotiation_attempt", 1)
        # One decision per (offer, stage, attempt): an earlier unblock is never reused for a later gate.
        try:
            signed = await _await_signed(
                state,
                UNBLOCK_DECISION,
                await _gate_payload(state, stage),
                f"{subject_ref(state)}:{stage}:{attempt}",
            )
        except DecisionRejected:
            update = await move(state, OfferStatus.REJECTED, reason="gate_rejected")
            return {"negotiation_cleared": False, **update}
        if signed.payload.get("stage") != stage or signed.payload.get("attempt") != attempt:
            raise InvalidSignedDecision(
                f"decision {signed.id} was signed for another gate (stage/attempt mismatch)"
            )
        action = signed.payload.get("action")
        negotiated_price = state.get("negotiation", {}).get("price_minor")
        if action == "unblock" and stage == "post" and negotiated_price is None:
            # Stopped negotiations and escalations without a quote have no price: there is nothing to score.
            # The human must renegotiate or discard. A #241 gate quote does carry one, and unblocking it
            # goes through the sanity recheck like an agreed price.
            raise InvalidSignedDecision(
                f"decision {signed.id}: unblock is not valid, the negotiation has no agreed price"
            )
        if action == "unblock":
            target = OfferStatus.FINANCIALLY_CHECKED if stage == "pre" else OfferStatus.SCORED
            update = await move(state, target)
            return {
                "gate_decision_id": signed.id,
                "negotiation_cleared": stage == "pre",
                **update,
            }
        if action == "renegotiate" and stage == "post":
            # ``attempt`` counts negotiations so far, so ``attempt`` renegotiations have been requested
            # after this one is allowed only while that count stays within ``gate.max_renegotiations``.
            limit = deps.config.max_renegotiations(state["tenant_id"])
            if attempt > limit:
                update = await move(state, OfferStatus.REJECTED, reason="renegotiation_limit")
                return {"negotiation_cleared": False, **update}
            update = await move(state, OfferStatus.FINANCIALLY_CHECKED)
            return {
                "gate_decision_id": signed.id,
                "negotiation_cleared": True,
                "negotiation_attempt": attempt + 1,
                **update,
            }
        raise InvalidSignedDecision(f"decision {signed.id} has action {action!r}, not valid here")

    def after_gate_wait(state: OfferState) -> str:
        status = OfferStatus(state["status"])
        if status is OfferStatus.REJECTED:
            return END
        if status is OfferStatus.FINANCIALLY_CHECKED:
            return "check_financial"  # pre-stage unblock, or a signed renegotiate
        return "score_offer"

    async def check_financial(state: OfferState) -> dict[str, Any]:
        update: dict[str, Any] = {"finance": await _fit(state)}
        if OfferStatus(state["status"]) is not OfferStatus.FINANCIALLY_CHECKED:
            update.update(await move(state, OfferStatus.FINANCIALLY_CHECKED))
        return update

    async def enter_negotiating(state: OfferState) -> dict[str, Any]:
        """Persist ``negotiating`` before the (possibly long) conversation, so the stored status is truthful."""
        if not state.get("negotiation_cleared"):
            raise NegotiationNotCleared(subject_ref(state))
        return await move(state, OfferStatus.NEGOTIATING)

    def _outcome(result: Any) -> NegotiationOutcomeKind:
        """Coerce the port's outcome into this module's enum.

        DEV-5's negotiator returns its own ``NegotiationOutcome`` class (same values, different type). Two
        ``StrEnum`` members with the same value compare equal, but relying on that would break the day a value
        is renamed on one side. Coercing here makes the boundary explicit and fails loudly on an unknown value.
        """
        try:
            return NegotiationOutcomeKind(result.outcome)
        except ValueError as exc:
            raise UnknownNegotiationOutcome(str(result.outcome)) from exc

    async def negotiate(state: OfferState) -> dict[str, Any]:
        """Poll the negotiator once. Non-terminal results go to ``wait_negotiation`` and come back here.

        The wait is a separate node on purpose: LangGraph replays a node from its start on resume, so a
        polling loop with ``interrupt()`` inside would call the negotiator twice per resume.
        """
        if not state.get("negotiation_cleared"):
            raise NegotiationNotCleared(subject_ref(state))
        attempt = state.get("negotiation_attempt", 1)
        key = f"negotiate:{subject_ref(state)}:{attempt}"
        result = await deps.ledger.once(
            key,
            lambda: deps.negotiation.negotiate(
                state["offer"], tenant_id=state["tenant_id"], idempotency_key=key
            ),
            # A waiting negotiation is never replayed from the ledger: the next call must make progress.
            cacheable=lambda r: _outcome(r) in TERMINAL_OUTCOMES,
        )
        update: dict[str, Any] = {"negotiation": result.model_dump(mode="json")}
        if _outcome(result) in TERMINAL_OUTCOMES:
            update.update(await move(state, OfferStatus.NEGOTIATED))
        return update

    def after_negotiate(state: OfferState) -> str:
        outcome = NegotiationOutcomeKind(state["negotiation"]["outcome"])
        return "route_negotiated" if outcome in TERMINAL_OUTCOMES else "wait_negotiation"

    async def wait_negotiation(state: OfferState) -> dict[str, Any]:
        negotiation = state["negotiation"]
        interrupt(
            {
                "kind": "awaiting_negotiation",
                "outcome": negotiation["outcome"],
                "negotiation_id": negotiation["negotiation_id"],
                "subject_ref": subject_ref(state),
            }
        )
        return {}

    async def route_negotiated(state: OfferState) -> dict[str, Any]:
        outcome = NegotiationOutcomeKind(state["negotiation"]["outcome"])
        if outcome is NegotiationOutcomeKind.AGREED:
            return {}
        if outcome in GATE_OUTCOMES:
            gate = {
                "route": GateRoute.GATE.value,
                "reasons": [f"negotiation:{outcome.value}"],
                "stage": "post",
            }
            return {
                "gate": gate,
                "gate_stage": "post",
                **await move(state, OfferStatus.GATE_PENDING),
            }
        assert outcome in REJECT_OUTCOMES
        gate = {"route": GateRoute.DISCARD.value, "reasons": [outcome.value], "stage": "post"}
        return {
            "gate": gate,
            **await move(state, OfferStatus.REJECTED, reason=f"negotiation_{outcome.value}"),
        }

    def after_route_negotiated(state: OfferState) -> str:
        status = OfferStatus(state["status"])
        if status is OfferStatus.NEGOTIATED:
            return "recheck_sanity"
        if status is OfferStatus.GATE_PENDING:
            return "gate_wait"
        return END

    async def recheck_sanity(state: OfferState) -> dict[str, Any]:
        negotiation = state["negotiation"]
        attempt = state.get("negotiation_attempt", 1)
        # The sanity engine works in EUR per unit; convert the negotiated price with DEV-3 FX first.
        unit = await deps.ledger.once(
            f"eur-unit:{subject_ref(state)}:{attempt}",
            lambda: deps.prices.to_eur_unit(
                price_minor=negotiation["price_minor"],
                currency=negotiation["currency"],
                tenant_id=state["tenant_id"],
            ),
        )
        outcome = await deps.sanity.check(
            state["offer"], tenant_id=state["tenant_id"], price_minor=unit.unit_price_eur_minor
        )
        return {
            "sanity": outcome.model_dump(mode="json"),
            "negotiation_price": unit.model_dump(mode="json"),
            **await move(state, OfferStatus.SANITY_RECHECKED),
        }

    async def route_post(state: OfferState) -> dict[str, Any]:
        route, reasons = _route(state)
        gate = {"route": route.value, "reasons": reasons, "stage": "post"}
        if route is GateRoute.NEGOTIATE:
            return {"gate": gate, "gate_stage": "post", **await move(state, OfferStatus.SCORED)}
        if route is GateRoute.GATE:
            return {
                "gate": gate,
                "gate_stage": "post",
                **await move(state, OfferStatus.GATE_PENDING),
            }
        return {
            "gate": gate,
            **await move(state, OfferStatus.REJECTED, reason="gate_discard_after_negotiation"),
        }

    def after_route_post(state: OfferState) -> str:
        status = OfferStatus(state["status"])
        if status is OfferStatus.SCORED:
            return "score_offer"
        if status is OfferStatus.GATE_PENDING:
            return "gate_wait"
        return END

    async def score_offer(state: OfferState) -> dict[str, Any]:
        scored = await deps.scoring.score(state["offer"], tenant_id=state["tenant_id"])
        update: dict[str, Any] = {"score": scored}
        if OfferStatus(state["status"]) is not OfferStatus.SCORED:
            update.update(await move(state, OfferStatus.SCORED))
        return update

    async def enter_awaiting(state: OfferState) -> dict[str, Any]:
        """Persist ``awaiting_human`` before pausing, so the stored status is truthful while we wait."""
        return await move(state, OfferStatus.AWAITING_HUMAN)

    async def await_human(state: OfferState) -> dict[str, Any]:
        payload = {
            "offer_id": state["offer_id"],
            "mission_id": state["mission_id"],
            "price_sanity": state.get("sanity", {}),
            "seller_confidence": state.get("trust", {}),
            "financial_fit": state.get("finance", {}),
            "negotiation": state.get("negotiation", {}),
            "negotiation_price": state.get("negotiation_price", {}),
            "score": state.get("score", {}),
            "config_version": state.get("config_version", ""),
        }
        try:
            signed = await _await_signed(
                state, DEAL_DECISION, payload, f"{subject_ref(state)}:final"
            )
        except DecisionRejected:
            return await move(
                state,
                OfferStatus.REJECTED,
                source=OfferStatus.AWAITING_HUMAN,
                reason="decision_rejected_or_expired",
            )
        action = str(signed.payload.get("action", ""))
        if action not in {"approve", "reject"}:
            raise InvalidSignedDecision(f"decision {signed.id} has unknown action {action!r}")
        update = await move(state, OfferStatus.SIGNED, source=OfferStatus.AWAITING_HUMAN)
        return {"human_decision_id": signed.id, "human_action": action, **update}

    def after_human(state: OfferState) -> str:
        return END if OfferStatus(state["status"]) is OfferStatus.REJECTED else "decide"

    async def decide(state: OfferState) -> dict[str, Any]:
        if state.get("human_action") == "approve":
            return await move(state, OfferStatus.APPROVED)
        return await move(state, OfferStatus.REJECTED, reason="human_rejected")

    def after_decide(state: OfferState) -> str:
        return "purchase" if OfferStatus(state["status"]) is OfferStatus.APPROVED else END

    async def purchase(state: OfferState) -> dict[str, Any]:
        """Records that purchase is authorized. Needs the signed approval; re-verified, never assumed."""
        decision_id = state.get("human_decision_id")
        if not decision_id:
            raise InvalidSignedDecision("purchase without a signed decision")
        signed = await deps.decisions.require_signed(decision_id, tenant_id=state["tenant_id"])
        if signed.payload.get("action") != "approve":
            raise InvalidSignedDecision(f"decision {signed.id} is not an approval")
        # ADR-900: an approval never buys an out-of-budget offer. The offer stays ``approved`` and the reason
        # is recorded so the dashboard (D4-11) can show why. ``financials_stale`` and ``fx_provisional`` are
        # enforced by D4-11 at purchase time.
        if state.get("finance", {}).get("verdict") == "out_of_budget":
            return {"purchase_blocked": ["out_of_budget"]}
        return await move(state, OfferStatus.PURCHASED)

    graph: StateGraph[OfferState, None, OfferState, OfferState] = StateGraph(OfferState)
    graph.add_node("start", start)
    graph.add_node("enrich", enrich)
    graph.add_node("score_trust", score_trust)
    graph.add_node("check_sanity", check_sanity)
    graph.add_node("route_pre", route_pre)
    graph.add_node("gate_wait", gate_wait)
    graph.add_node("check_financial", check_financial)
    graph.add_node("enter_negotiating", enter_negotiating)
    graph.add_node("negotiate", negotiate)
    graph.add_node("wait_negotiation", wait_negotiation)
    graph.add_node("route_negotiated", route_negotiated)
    graph.add_node("recheck_sanity", recheck_sanity)
    graph.add_node("route_post", route_post)
    graph.add_node("score_offer", score_offer)
    graph.add_node("enter_awaiting", enter_awaiting)
    graph.add_node("await_human", await_human)
    graph.add_node("decide", decide)
    graph.add_node("purchase", purchase)

    graph.set_entry_point("start")
    graph.add_edge("start", "enrich")
    graph.add_edge("enrich", "score_trust")
    graph.add_edge("score_trust", "check_sanity")
    graph.add_edge("check_sanity", "route_pre")
    graph.add_conditional_edges(
        "route_pre",
        after_route_pre,
        {"check_financial": "check_financial", "gate_wait": "gate_wait", END: END},
    )
    graph.add_conditional_edges(
        "gate_wait",
        after_gate_wait,
        {"check_financial": "check_financial", "score_offer": "score_offer", END: END},
    )
    graph.add_edge("check_financial", "enter_negotiating")
    graph.add_edge("enter_negotiating", "negotiate")
    graph.add_conditional_edges(
        "negotiate",
        after_negotiate,
        {"route_negotiated": "route_negotiated", "wait_negotiation": "wait_negotiation"},
    )
    graph.add_edge("wait_negotiation", "negotiate")
    graph.add_conditional_edges(
        "route_negotiated",
        after_route_negotiated,
        {"recheck_sanity": "recheck_sanity", "gate_wait": "gate_wait", END: END},
    )
    graph.add_edge("recheck_sanity", "route_post")
    graph.add_conditional_edges(
        "route_post",
        after_route_post,
        {"score_offer": "score_offer", "gate_wait": "gate_wait", END: END},
    )
    graph.add_edge("score_offer", "enter_awaiting")
    graph.add_edge("enter_awaiting", "await_human")
    graph.add_conditional_edges("await_human", after_human, {"decide": "decide", END: END})
    graph.add_conditional_edges("decide", after_decide, {"purchase": "purchase", END: END})
    graph.add_edge("purchase", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = [
    "DEAL_DECISION",
    "SERVICE_NAME",
    "UNBLOCK_DECISION",
    "InvalidSignedDecision",
    "NegotiationNotCleared",
    "UnknownNegotiationOutcome",
    "OfferGraphDeps",
    "build_offer_graph",
    "initial_state",
    "subject_ref",
    "thread_id",
]
