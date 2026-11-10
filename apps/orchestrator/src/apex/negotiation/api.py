"""Human controls and the contract view of a negotiation (D5-07c, on top of D5-08).

The engine owns the state machine; this module is the seam DEV-4's graph and DEV-6's UI call:

- :func:`takeover`, :func:`resume`, :func:`abort` return control between a human and the agent.
- :class:`NegotiationControlService` adds the rest of the semi-automatic loop: read the negotiation, read
  its transcript, approve or reject the drafted message, and send a message as a human.
- :func:`to_contract` and :func:`transcript_page` map the domain session onto the contract's
  ``Negotiation`` and ``NegotiationMessage``. This is the only place that knows which internal outcome is
  which public state, which internal guardrail hit has a counterpart in the contract's closed enum, and
  how a transcript message gets its stable public id.

``POST /v1/negotiations/...`` in ``apex.api.negotiations`` is the HTTP face of the same calls, so the
behaviour cannot drift between the graph and the browser.

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
    MessageRole,
    Negotiation,
    NegotiationDraft,
    NegotiationDraftSource,
    NegotiationMessage,
    NegotiationState,
)
from apex.negotiation.engine import NegotiationEngine
from apex.negotiation.models import (
    NEGOTIATION_STRATEGY,
    NegotiationOutcome,
    NegotiationSession,
    PendingDraft,
    TranscriptMessage,
)
from apex.negotiation.ports import (
    ChatLine,
    InMemoryAccountSendLog,
    InMemoryNegotiationStore,
    InMemorySellerGuard,
    InMemorySellerSendLog,
)

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "NegotiationControlService",
    "abort",
    "build_default_control",
    "message_id",
    "resume",
    "state_of",
    "takeover",
    "to_contract",
    "to_message",
    "transcript_page",
]

DEFAULT_PAGE_SIZE = 50
"""Messages per transcript page when the caller does not ask for a size (contract ``Limit`` default)."""

MAX_PAGE_SIZE = 200
"""Upper bound of the contract's ``Limit`` parameter."""

ABORT_REASON_DEFAULT = "human_abort"
REOPEN_REASON_DEFAULT = "human_reopen"
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


def _draft_of(pending: PendingDraft | None) -> NegotiationDraft | None:
    """The draft waiting for a human, if any. Absent means nothing is waiting."""
    if pending is None:
        return None
    return NegotiationDraft(
        id=pending.id,
        text=pending.text,
        source=NegotiationDraftSource(pending.source),
        created_at=pending.created_at,
    )


def message_id(session: NegotiationSession, message: TranscriptMessage) -> str:
    """Stable public id of a transcript message.

    The engine numbers messages with ``seq`` inside the negotiation and does not need a global id; the
    contract asks for one, so it is derived from the pair that is already unique.
    """
    return f"{session.id}:{message.seq}"


def to_message(session: NegotiationSession, message: TranscriptMessage) -> NegotiationMessage:
    """One transcript message in the contract's shape."""
    return NegotiationMessage(
        id=message_id(session, message),
        negotiation_id=session.id,
        role=MessageRole(message.role),
        content=message.text,
        at=message.at,
        seq=message.seq,
        approved_by=message.approved_by,
        screenshot_ref=None,
        redactions=0,
    )


def transcript_page(
    session: NegotiationSession, *, cursor: str | None, limit: int
) -> tuple[list[NegotiationMessage], str | None]:
    """A page of the transcript, oldest first, with the cursor of the next page.

    The cursor is the ``seq`` of the last message already delivered, which is why it is opaque to the
    client but stable across pages even while the conversation grows. A cursor that is not a number is a
    client error and raises ``ValueError``; the router turns it into a 400.
    """
    after = 0 if cursor is None else int(cursor)
    if after < 0:
        raise ValueError("cursor must not be negative")
    rows = [message for message in session.transcript if message.seq > after]
    page = rows[:limit]
    next_cursor = str(page[-1].seq) if len(rows) > limit else None
    return [to_message(session, message) for message in page], next_cursor


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
        pending_draft=_draft_of(session.pending),
        mission_id=session.mission_id or None,
        trace_id=session.trace_id or None,
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

    async def reopen(
        self, negotiation_id: str, *, tenant_id: str, reason: str | None = None
    ) -> NegotiationSession:
        return await self._engine.reopen(
            negotiation_id, tenant_id=tenant_id, reason=reason or REOPEN_REASON_DEFAULT
        )

    async def get(self, negotiation_id: str, *, tenant_id: str) -> NegotiationSession:
        """Read one negotiation. Same tenant check as every other call (``not_found`` for a stranger)."""
        return await self._engine.get(negotiation_id, tenant_id=tenant_id)

    async def approve(
        self, negotiation_id: str, draft_id: str, *, approver: str, tenant_id: str
    ) -> NegotiationSession:
        return await self._engine.approve(
            negotiation_id, draft_id, approver=approver, tenant_id=tenant_id
        )

    async def reject(
        self, negotiation_id: str, draft_id: str, *, tenant_id: str
    ) -> NegotiationSession:
        return await self._engine.reject(negotiation_id, draft_id, tenant_id=tenant_id)

    async def send_human(
        self, negotiation_id: str, text: str, *, author: str, tenant_id: str
    ) -> NegotiationSession:
        return await self._engine.send_human(
            negotiation_id, text, author=author, tenant_id=tenant_id
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
