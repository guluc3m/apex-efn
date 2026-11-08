"""Negotiation engine (D5-07b, spec 3.6).

The engine drives one seller conversation step by step. It is the only place that sends messages, and
every outgoing text passes :func:`apex.negotiation.guardrails.check_outgoing` immediately before the
transport call. The LLM only drafts wording for a :class:`Plan` chosen by the playbook and extracts the
seller's quote; prices and limits are decided in code.

Flow of :meth:`NegotiationEngine.advance`:

1. Stop if terminal, if a human holds control, or if a draft waits for approval (semi-automatic mode).
2. Read new seller messages. Classify them with ``check_incoming``: escalations stop the agent.
3. Extract the quote (LLM, grounded against the deterministic parser), re-check it with DEV-3's sanity
   engine (criterion 13): ``atypical`` or ``implausible`` stops the negotiation for the gate.
4. Ask the playbook for the next :class:`Plan`, draft it, guard it, and either send it (autonomous) or
   park it as a pending draft for a human (Phase 1).
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from apex.common.clock import Clock
from apex.negotiation.guardrails import (
    ConversationState,
    GuardrailVerdict,
    HitCode,
    IncomingVerdict,
    check_incoming,
    check_outgoing,
)
from apex.negotiation.models import (
    Intent,
    NegotiationOutcome,
    NegotiationParams,
    NegotiationSession,
    PendingDraft,
    Plan,
    Quote,
    SanityBand,
    TranscriptMessage,
)
from apex.negotiation.playbook import Stop, build_ladder, decide, select_quote
from apex.negotiation.ports import (
    AccountSendLog,
    ChatTransport,
    Drafter,
    Extractor,
    NegotiationStore,
    SanityRecheck,
)
from apex.negotiation.templates import render
from apex.negotiation.text import find_percentages, find_prices

__all__ = ["NegotiationEngine", "NegotiationError", "OpenRequest", "confirms", "plan_matches"]

# Bands that stop the negotiation for the gate: anomalous prices (criterion 13) and prices that cannot be
# judged for lack of reference (ADR-900 Q12, spec 3.3.1 "no se negocia a ciegas").
_STOP_BANDS = frozenset(
    {SanityBand.ATYPICAL, SanityBand.IMPLAUSIBLE, SanityBand.INSUFFICIENT_REFERENCE}
)


class NegotiationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class OpenRequest:
    tenant_id: str
    platform: str
    seller_id: str
    product_id: str
    account_id: str
    config_version: str
    params: NegotiationParams


_REFUSAL_RE = re.compile(
    r"\b(?:no|not|cannot|can't|can not|unable|impossible|sorry|but)\b|\bno\s+podemos\b|\blo\s+siento\b|"
    r"不能|无法|不行|抱歉|但是",
    re.IGNORECASE,
)
_CONFIRM_RE = re.compile(
    r"\bconfirm(?:ed|s)?\b|\bwe\s+agree\b|\bagreed\b|\bconfirmad[oa]s?\b|\bconfirmamos\b|"
    r"\bde\s+acuerdo\b|确认|同意",
    re.IGNORECASE,
)


def confirms(text: str, agreed: Quote) -> bool:
    """True when the seller confirms the summarised price in writing (spec 3.6 step 7).

    Deliberately strict: an explicit confirmation word, the exact summarised price, no other price in the
    negotiation currency and no refusal word. Anything else goes to a human.
    """
    if _REFUSAL_RE.search(text) or not _CONFIRM_RE.search(text):
        return False
    prices = [p for p in find_prices(text) if p.currency == agreed.currency]
    return bool(prices) and all(p.minor == agreed.unit_price_minor for p in prices)


def plan_matches(text: str, plan: Plan, currency: str) -> bool:
    """A draft may only state the price the playbook chose, and no price when it chose none.

    This keeps the LLM from inventing a different number that would still pass the guardrail limits.
    """
    prices = find_prices(text)
    if find_percentages(text):
        return False
    if plan.price_minor is None:
        return not prices
    return bool(prices) and all(
        p.currency == currency and p.minor == plan.price_minor for p in prices
    )


class NegotiationEngine:
    def __init__(
        self,
        *,
        transport: ChatTransport,
        drafter: Drafter,
        extractor: Extractor,
        sanity: SanityRecheck,
        store: NegotiationStore,
        send_log: AccountSendLog,
        clock: Clock,
        new_id: Callable[[], str],
    ) -> None:
        self._transport = transport
        self._drafter = drafter
        self._extractor = extractor
        self._sanity = sanity
        self._store = store
        self._send_log = send_log
        self._clock = clock
        self._new_id = new_id
        # One operation at a time per negotiation (approve, advance, takeover...). In-process only;
        # a multi-worker deployment needs the store's optimistic version check as well (D2-05).
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def _locked(self, key: str) -> AsyncIterator[None]:
        async with self._locks[key]:
            yield

    # ------------------------------------------------------------------ lifecycle

    async def start(self, request: OpenRequest, *, idempotency_key: str) -> NegotiationSession:
        """Opens the chat and prepares the first message. Idempotent per ``idempotency_key``.

        A retry after a failed or interrupted start resumes it: the chat is opened if it is still
        missing and the opening message is prepared if nothing was prepared or sent yet.
        """
        async with self._locked(f"key:{idempotency_key}"):
            session = await self._store.find_by_key(idempotency_key)
            if session is not None and session.tenant_id != request.tenant_id:
                raise NegotiationError("not_found", "unknown negotiation for this tenant")
            if session is None:
                session = NegotiationSession(
                    id=self._new_id(),
                    tenant_id=request.tenant_id,
                    platform=request.platform,
                    seller_id=request.seller_id,
                    product_id=request.product_id,
                    account_id=request.account_id,
                    config_version=request.config_version,
                    params=request.params,
                )
                session.ladder = build_ladder(session)
                await self._store.save(session, idempotency_key=idempotency_key)
            async with self._locked(session.id):
                if session.terminal:
                    return session
                if session.chat_id is None:
                    session.chat_id = await self._transport.open(
                        platform=session.platform,
                        seller_id=session.seller_id,
                        product_id=session.product_id,
                        account_id=session.account_id,
                    )
                    await self._store.save(session)
                if session.rounds_sent == 0 and session.pending is None:
                    await self._prepare(session, Plan(intent=Intent.OPEN), seller_text=None)
                    await self._store.save(session)
                return session

    async def advance(self, negotiation_id: str, *, tenant_id: str) -> NegotiationSession:
        async with self._locked(negotiation_id):
            session = await self._load(negotiation_id, tenant_id)
            await self._step(session)
            return session

    async def _step(self, session: NegotiationSession) -> None:
        if session.terminal or session.human_in_control:
            return
        if session.chat_id is None:
            raise NegotiationError("no_chat", "negotiation has no open chat")

        # Seller messages are always read first, even while a draft waits for approval, so an
        # escalation is never preceded by one more agent message.
        text = await self._read_seller(session)
        if text is None:
            await self._retry_pending(session)
            await self._store.save(session)
            return

        verdict = check_incoming(text, supported_currencies=session.params.supported_currencies)
        session.notices.extend(h.code.value for h in verdict.hits)
        if verdict.escalate:
            await self._finish(
                session,
                NegotiationOutcome.ESCALATED,
                ",".join(sorted(h.code.value for h in verdict.hits)),
            )
            return

        if session.summary_sent:
            # Only an explicit written confirmation of the summarised conditions counts (step 7).
            if session.agreed is not None and confirms(text, session.agreed):
                await self._finish(
                    session, NegotiationOutcome.AGREED, "seller_confirmed_in_writing"
                )
            else:
                await self._finish(session, NegotiationOutcome.ESCALATED, "summary_not_confirmed")
            return

        # A new seller turn supersedes any draft prepared for the previous one.
        session.pending = None
        quote = await self._quote(session, text, verdict)
        if quote is not None:
            band = await self._sanity.check(quote, session=session)
            session.quotes.append(quote)
            if band in _STOP_BANDS:
                await self._finish(
                    session, NegotiationOutcome.STOPPED_ANOMALOUS_PRICE, f"sanity_{band.value}"
                )
                return

        decision = decide(session, verdict, quote)
        if isinstance(decision, Stop):
            await self._finish(session, decision.outcome, decision.reason)
            return
        if decision.intent in (Intent.ANCHOR, Intent.COUNTER):
            session.next_rung += 1
        if decision.intent is Intent.REQUEST_PRICE:
            session.asked_for_price = True
        if decision.intent is Intent.SUMMARY and quote is not None:
            session.agreed = quote
        await self._prepare(session, decision, seller_text=text)
        await self._store.save(session)

    async def _read_seller(self, session: NegotiationSession) -> str | None:
        assert session.chat_id is not None
        lines = await self._transport.read(session.chat_id, after_seq=session.last_seller_seq)
        if lines:
            session.last_seller_seq = max(line.seq for line in lines)
        seller = [line for line in lines if line.role == "seller"]
        for line in seller:
            self._log(session, "seller", line.text)
        if not seller:
            if session.status is NegotiationOutcome.IN_PROGRESS and session.pending is None:
                session.status = NegotiationOutcome.AWAITING_SELLER
            return None
        return "\n".join(line.text for line in seller)

    async def _retry_pending(self, session: NegotiationSession) -> None:
        """Autonomous mode parks a draft only while the account is rate limited: retry it."""
        pending = session.pending
        if pending is None or session.params.semi_automatic:
            return
        if (await self._check(session, pending.text, 0)).allowed:
            await self._send(session, pending.plan, pending.text, approved_by=None)

    # ------------------------------------------------------------------ human controls

    async def approve(
        self, negotiation_id: str, draft_id: str, *, approver: str, tenant_id: str
    ) -> NegotiationSession:
        """Semi-automatic mode: a human approves the pending draft.

        Unread seller messages are processed first: if they escalate or supersede the draft, nothing is
        sent and the caller gets ``draft_not_pending``. The guardrails run again right before sending.
        """
        async with self._locked(negotiation_id):
            session = await self._load(negotiation_id, tenant_id)
            if session.human_in_control:
                raise NegotiationError("human_in_control", "a human holds the conversation")
            pending = session.pending
            if pending is None or pending.id != draft_id or session.terminal:
                raise NegotiationError("draft_not_pending", "this draft is not awaiting approval")
            await self._step(session)
            if session.pending is None or session.pending.id != draft_id or session.terminal:
                await self._store.save(session)
                raise NegotiationError(
                    "draft_superseded", "new seller messages arrived; review the new state"
                )
            await self._send(session, pending.plan, pending.text, approved_by=approver)
            await self._store.save(session)
            return session

    async def reject(
        self, negotiation_id: str, draft_id: str, *, tenant_id: str
    ) -> NegotiationSession:
        """Discards the pending draft and prepares the deterministic template instead."""
        async with self._locked(negotiation_id):
            session = await self._load(negotiation_id, tenant_id)
            pending = session.pending
            if pending is None or pending.id != draft_id:
                raise NegotiationError("draft_not_pending", "this draft is not awaiting approval")
            session.pending = None
            await self._park_or_send(
                session, pending.plan, render(pending.plan, session), 0, "template"
            )
            await self._store.save(session)
            return session

    async def take_over(self, negotiation_id: str, *, tenant_id: str) -> NegotiationSession:
        """A human takes the chat. Any pending draft is dropped; the agent sends nothing until resume."""
        async with self._locked(negotiation_id):
            session = await self._load(negotiation_id, tenant_id)
            session.human_in_control = True
            session.pending = None
            await self._store.save(session)
            return session

    async def resume(self, negotiation_id: str, *, tenant_id: str) -> NegotiationSession:
        async with self._locked(negotiation_id):
            session = await self._load(negotiation_id, tenant_id)
            if session.terminal:
                raise NegotiationError("terminal", "negotiation already finished")
            session.human_in_control = False
            session.status = NegotiationOutcome.AWAITING_SELLER
            await self._store.save(session)
            return session

    async def abort(
        self, negotiation_id: str, *, reason: str, tenant_id: str
    ) -> NegotiationSession:
        async with self._locked(negotiation_id):
            session = await self._load(negotiation_id, tenant_id)
            if not session.terminal:
                await self._finish(session, NegotiationOutcome.ABORTED, reason)
            return session

    # ------------------------------------------------------------------ internals

    async def _load(self, negotiation_id: str, tenant_id: str) -> NegotiationSession:
        session = await self._store.get(negotiation_id)
        # Another tenant's negotiation is indistinguishable from a missing one (spec 6, RLS).
        if session is None or session.tenant_id != tenant_id:
            raise NegotiationError("not_found", f"unknown negotiation {negotiation_id}")
        return session

    async def _finish(
        self, session: NegotiationSession, outcome: NegotiationOutcome, reason: str
    ) -> None:
        session.status = outcome
        session.stop_reason = reason
        session.pending = None
        if outcome is not NegotiationOutcome.AGREED:
            session.agreed = None
        await self._store.save(session)

    async def _quote(
        self, session: NegotiationSession, text: str, verdict: IncomingVerdict
    ) -> Quote | None:
        """LLM extraction, accepted only when grounded in a price literally present in the text."""
        currency = session.params.currency
        fallback = select_quote(verdict, currency, session.rounds_sent)
        try:
            extraction = await self._extractor.extract(text, session)
        except Exception:
            return fallback
        session.tokens_used += extraction.tokens
        if extraction.unit_price_minor is None or extraction.currency != currency:
            return fallback
        grounded = any(
            p.currency == currency and p.minor == extraction.unit_price_minor
            for p in verdict.prices
        )
        if not grounded:
            session.guardrail_hits.append("extraction_not_grounded")
            return fallback
        return Quote(
            unit_price_minor=extraction.unit_price_minor,
            currency=currency,
            at_round=session.rounds_sent,
        )

    async def _state(self, session: NegotiationSession) -> ConversationState:
        return ConversationState(
            rounds_sent=session.rounds_sent,
            tokens_used=session.tokens_used,
            human_in_control=session.human_in_control,
            account_sends=tuple(await self._send_log.sends(session.account_id)),
        )

    async def _check(self, session: NegotiationSession, text: str, tokens: int) -> GuardrailVerdict:
        return check_outgoing(
            text,
            session.params.limits(),
            await self._state(session),
            now=self._clock.now(),
            draft_tokens=tokens,
        )

    async def _prepare(
        self, session: NegotiationSession, plan: Plan, seller_text: str | None
    ) -> None:
        """Drafts the message for ``plan`` with the LLM, falling back to the template."""
        currency = session.params.currency
        for _ in range(session.params.max_drafts):
            try:
                draft = await self._drafter.draft(plan, session, seller_text)
            except Exception:
                session.guardrail_hits.append("draft_failed")
                break
            session.tokens_used += draft.tokens
            if not plan_matches(draft.text, plan, currency):
                session.guardrail_hits.append("draft_off_plan")
                continue
            verdict = await self._check(session, draft.text, 0)
            if verdict.allowed:
                await self._park_or_send(session, plan, draft.text, draft.tokens, "llm")
                return
            session.guardrail_hits.extend(h.code.value for h in verdict.hits)
            if verdict.escalate:
                await self._finish(
                    session, NegotiationOutcome.ESCALATED, "draft_guardrail_escalation"
                )
                return
        await self._park_or_send(session, plan, render(plan, session), 0, "template")

    async def _park_or_send(
        self,
        session: NegotiationSession,
        plan: Plan,
        text: str,
        tokens: int,
        source: str,
    ) -> None:
        verdict = await self._check(session, text, 0)
        # Rate limiting only delays a message: park it and send it once the window allows.
        blocking = verdict.codes - {HitCode.ACCOUNT_RATE_LIMITED}
        if blocking:
            session.guardrail_hits.extend(h.code.value for h in verdict.hits)
            outcome = (
                NegotiationOutcome.NO_AGREEMENT
                if blocking <= {HitCode.MAX_ROUNDS_REACHED}
                else NegotiationOutcome.ESCALATED
            )
            await self._finish(session, outcome, "draft_blocked:" + ",".join(sorted(blocking)))
            return
        if session.params.semi_automatic or not verdict.allowed:
            session.pending = PendingDraft(
                id=self._new_id(),
                plan=plan,
                text=text,
                tokens=tokens,
                created_at=self._clock.now(),
                source="llm" if source == "llm" else "template",
            )
            session.status = (
                NegotiationOutcome.AWAITING_HUMAN_APPROVAL
                if session.params.semi_automatic
                else NegotiationOutcome.IN_PROGRESS
            )
            return
        await self._send(session, plan, text, approved_by=None)

    async def _send(
        self,
        session: NegotiationSession,
        plan: Plan,
        text: str,
        *,
        approved_by: str | None,
    ) -> None:
        """The single send path. Re-checks the guardrails right before the transport call."""
        verdict = await self._check(session, text, 0)
        if not verdict.allowed:
            session.guardrail_hits.extend(h.code.value for h in verdict.hits)
            raise NegotiationError("guardrail_blocked", ",".join(sorted(verdict.codes)))
        if session.chat_id is None:
            raise NegotiationError("no_chat", "negotiation has no open chat")
        await self._transport.send(session.chat_id, text)
        now = self._clock.now()
        await self._send_log.record(session.account_id, now)
        session.rounds_sent += 1
        session.pending = None
        session.status = NegotiationOutcome.AWAITING_SELLER
        if plan.intent is Intent.SUMMARY:
            session.summary_sent = True
        self._log(session, "agent", text, intent=plan.intent, approved_by=approved_by)

    def _log(
        self,
        session: NegotiationSession,
        role: str,
        text: str,
        *,
        intent: Intent | None = None,
        approved_by: str | None = None,
    ) -> None:
        session.transcript.append(
            TranscriptMessage(
                seq=len(session.transcript) + 1,
                role="agent" if role == "agent" else "seller" if role == "seller" else "human",
                text=text,
                at=self._clock.now(),
                intent=intent,
                approved_by=approved_by,
            )
        )
