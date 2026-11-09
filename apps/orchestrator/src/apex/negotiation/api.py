"""Human controls for a negotiation (D5-08) and their wire mapping.

The engine owns the state machine; this module is the seam DEV-4's graph and DEV-6's UI call:

- :func:`takeover`, :func:`resume`, :func:`abort` return control between a human and the agent.
  ``POST /v1/negotiations/{id}/takeover|resume|abort`` in ``apex.api.negotiations`` is the HTTP face of
  the same three calls, so behaviour cannot drift between the two callers.
- :func:`to_contract` maps the domain session onto the contract's ``Negotiation`` schema. It is the only
  place that knows which internal outcome is which public state and which internal guardrail hit has a
  counterpart in the contract's closed enum.

The seller stays claimed while a human holds the chat: no other mission of the tenant may open a second
conversation with the same seller (D5-08 anti-abuse, see :class:`~apex.negotiation.ports.SellerGuard`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from apex.common.clock import SystemClock
from apex.common.ids import IdGenerator
from apex.contracts.generated.models import (
    GuardrailCode,
    GuardrailHit,
    Negotiation,
    NegotiationState,
)
from apex.negotiation.engine import NegotiationEngine
from apex.negotiation.models import (
    NEGOTIATION_STRATEGY,
    NegotiationOutcome,
    NegotiationSession,
)
from apex.negotiation.ports import (
    ChatLine,
    InMemoryAccountSendLog,
    InMemoryNegotiationStore,
    InMemorySellerGuard,
    InMemorySellerSendLog,
)

__all__ = [
    "NegotiationControlService",
    "abort",
    "build_default_control",
    "resume",
    "state_of",
    "takeover",
    "to_contract",
]

ABORT_REASON_DEFAULT = "human_abort"
"""``stop_reason`` recorded when the caller aborts without a reason. A closed label, not a business value."""


#: Internal outcome -> the contract's public state machine. ``awaiting_seller`` is still a running
#: negotiation: the agent has sent and is waiting for the reply.
_STATE_BY_OUTCOME: dict[NegotiationOutcome, NegotiationState] = {
    NegotiationOutcome.IN_PROGRESS: NegotiationState.running,
    NegotiationOutcome.AWAITING_SELLER: NegotiationState.running,
    NegotiationOutcome.AWAITING_HUMAN_APPROVAL: NegotiationState.awaiting_approval,
    NegotiationOutcome.AGREED: NegotiationState.completed,
    NegotiationOutcome.NO_AGREEMENT: NegotiationState.completed,
    NegotiationOutcome.ESCALATED: NegotiationState.escalated,
    NegotiationOutcome.STOPPED_ANOMALOUS_PRICE: NegotiationState.escalated,
    NegotiationOutcome.ABORTED: NegotiationState.aborted,
}

_TERMINAL_STATES = frozenset(
    {
        NegotiationState.completed,
        NegotiationState.aborted,
        NegotiationState.escalated,
    }
)

#: Internal hit -> the contract's closed ``GuardrailCode``. Internal diagnostics without a public
#: equivalent (``draft_failed``, ``extraction_not_grounded``, ``draft_off_plan``, ``empty_message``, ...)
#: stay in ``guardrail_hits``, the transcript and the audit log; they are not shown in this view.
_GUARDRAIL_BY_HIT: dict[str, GuardrailCode] = {
    "max_discount_exceeded": GuardrailCode.max_discount_exceeded,
    "offer_below_floor": GuardrailCode.max_discount_exceeded,
    "percent_discount_exceeded": GuardrailCode.max_discount_exceeded,
    "unauthorized_counterpart": GuardrailCode.unauthorized_concession,
    "volume_exceeded": GuardrailCode.unauthorized_concession,
    "max_rounds_reached": GuardrailCode.max_rounds,
    "token_budget_exhausted": GuardrailCode.token_budget,
    "account_rate_limited": GuardrailCode.message_rate,
    "seller_rate_limited": GuardrailCode.message_rate,
    "sensitive_data_in_draft": GuardrailCode.sensitive_data_request,
    "seller_asks_sensitive_data": GuardrailCode.sensitive_data_request,
    "seller_off_platform_payment": GuardrailCode.off_platform_payment,
    "binding_commitment": GuardrailCode.binding_commitment_attempt,
    "wrong_currency": GuardrailCode.unsupported_currency,
    "seller_unsupported_currency": GuardrailCode.unsupported_currency,
}


def state_of(session: NegotiationSession) -> NegotiationState:
    """Public state. A human holding the chat wins over the agent-side state, never over a terminal one.

    Taking over drops the pending draft but does not rewrite ``status`` (the engine keeps the negotiation's
    own progress); the public view reports ``human_control`` while it is held.
    """
    state = _STATE_BY_OUTCOME[session.status]
    if session.human_in_control and state not in _TERMINAL_STATES:
        return NegotiationState.human_control
    return state


def _hits_of(session: NegotiationSession) -> list[GuardrailHit]:
    """Public guardrail hits, one per code, keeping the most recent timestamp.

    Deduplicating keeps a repeatedly blocked draft from growing the response without bound; the full
    sequence (every occurrence, with its clock reading) stays in ``session.guardrail_events``.
    """
    latest: dict[GuardrailCode, datetime] = {}
    for event in session.guardrail_events:
        code = _GUARDRAIL_BY_HIT.get(event.code)
        if code is not None:
            latest[code] = event.at
    return [GuardrailHit(code=code, at=at) for code, at in latest.items()]


def to_contract(session: NegotiationSession) -> Negotiation:
    """The contract's ``Negotiation`` view of a session.

    ``offer_id`` is what the caller passed when it opened the negotiation; engine-level tests that never
    came through the graph leave it empty, which the contract accepts.
    """
    return Negotiation(
        id=session.id,
        offer_id=session.offer_id,
        strategy=NEGOTIATION_STRATEGY,
        state=state_of(session),
        rounds=session.rounds_sent,
        max_rounds=session.params.max_rounds,
        guardrail_hits=_hits_of(session),
    )


class NegotiationControlService:
    """Tenant-checked façade over the engine's human controls.

    The engine already validates the tenant on every load and raises ``NegotiationError`` with a closed
    code (``not_found``, ``terminal``, ``not_in_human_control``); this class exists so the graph, the HTTP
    router and the tests share one entry point instead of calling the engine directly.
    """

    def __init__(self, engine: NegotiationEngine) -> None:
        self._engine = engine

    async def takeover(self, negotiation_id: str, *, tenant_id: str) -> NegotiationSession:
        return await self._engine.take_over(negotiation_id, tenant_id=tenant_id)

    async def resume(self, negotiation_id: str, *, tenant_id: str) -> NegotiationSession:
        return await self._engine.resume(negotiation_id, tenant_id=tenant_id)

    async def abort(
        self, negotiation_id: str, *, tenant_id: str, reason: str | None = None
    ) -> NegotiationSession:
        return await self._engine.abort(
            negotiation_id, tenant_id=tenant_id, reason=reason or ABORT_REASON_DEFAULT
        )


async def takeover(
    engine: NegotiationEngine, negotiation_id: str, *, tenant_id: str
) -> NegotiationSession:
    """DEV-4 interface (AGENTS.md section 4): a human takes the chat."""
    return await NegotiationControlService(engine).takeover(negotiation_id, tenant_id=tenant_id)


async def resume(
    engine: NegotiationEngine, negotiation_id: str, *, tenant_id: str
) -> NegotiationSession:
    """DEV-4 interface: return control to the agent."""
    return await NegotiationControlService(engine).resume(negotiation_id, tenant_id=tenant_id)


async def abort(
    engine: NegotiationEngine,
    negotiation_id: str,
    *,
    tenant_id: str,
    reason: str | None = None,
) -> NegotiationSession:
    """DEV-4 interface: stop the negotiation cleanly (terminal and idempotent)."""
    return await NegotiationControlService(engine).abort(
        negotiation_id, tenant_id=tenant_id, reason=reason
    )


class _UnwiredTransport:
    """Placeholder chat transport: the control endpoints never open or send, only the graph does."""

    async def open(self, *, platform: str, seller_id: str, product_id: str, account_id: str) -> str:
        raise NotImplementedError("negotiation drafting is not wired yet (D5-01/DEV-4 graph)")

    async def send(self, chat_id: str, text: str) -> None:
        raise NotImplementedError("negotiation drafting is not wired yet (D5-01/DEV-4 graph)")

    async def read(self, chat_id: str, *, after_seq: int) -> Sequence[ChatLine]:
        raise NotImplementedError("negotiation drafting is not wired yet (D5-01/DEV-4 graph)")


class _UnwiredDrafter:
    async def draft(self, plan: object, session: object, seller_text: str | None) -> object:
        raise NotImplementedError("negotiation drafting is not wired yet (D4-04 LLM role)")


class _UnwiredExtractor:
    async def extract(self, seller_text: str, session: object) -> object:
        raise NotImplementedError("negotiation extraction is not wired yet (D4-04 LLM role)")


class _UnwiredSanity:
    async def check(self, quote: object, *, session: object) -> object:
        raise NotImplementedError("sanity re-check is not wired yet (DEV-3 sanity.check)")


def build_default_control() -> NegotiationControlService:
    """In-process default for the HTTP router.

    It serves the control endpoints (takeover, resume, abort) over an in-memory store. It cannot see
    negotiations created by another process, so when DEV-4 wires the mission graph it must inject the
    shared engine through ``api.negotiations.get_negotiation_control``. Drafting and sending stay unwired
    on purpose: they need the browser worker and the ``negotiator`` LLM role, and a silent fake there
    would be a wrong answer, not a fallback.
    """
    clock = SystemClock()
    engine = NegotiationEngine(
        transport=_UnwiredTransport(),
        drafter=_UnwiredDrafter(),  # type: ignore[arg-type]
        extractor=_UnwiredExtractor(),  # type: ignore[arg-type]
        sanity=_UnwiredSanity(),  # type: ignore[arg-type]
        store=InMemoryNegotiationStore(),
        send_log=InMemoryAccountSendLog(),
        seller_log=InMemorySellerSendLog(),
        seller_guard=InMemorySellerGuard(),
        clock=clock,
        new_id=IdGenerator(clock).new_id,
    )
    return NegotiationControlService(engine)
