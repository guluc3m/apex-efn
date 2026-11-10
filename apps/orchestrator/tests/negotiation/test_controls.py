"""D5-08: human controls (takeover, resume, abort) and anti-abuse (seller exclusivity, per-seller rate).

The engine is the only sender. These tests pin the two guarantees that make a takeover safe and the two
that make our own traffic to a seller polite:

- while a human holds the chat, ``advance`` and ``approve`` send nothing;
- a seller an active negotiation is talking to is never opened a second time, across missions;
- messages to one seller are capped per rolling hour, using the configured account limit (no new number);
- abort is terminal and idempotent, and releases the seller.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from apex.negotiation.engine import NegotiationError, OpenRequest
from apex.negotiation.models import NegotiationOutcome
from tests.negotiation.fakes import (
    NOW,
    T,
    cooperative_seller,
    harness,
    params,
    request,
    run_autonomous,
)

SELLER = "b-standard-coop"


def _code(exc: pytest.ExceptionInfo[NegotiationError]) -> str:
    return exc.value.code


class TestHumanControls:
    async def test_takeover_drops_the_pending_draft_and_the_agent_sends_nothing(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        assert session.pending is not None  # semi-automatic: waiting for a human

        taken = await h.engine.take_over(session.id, tenant_id=T)
        assert taken.human_in_control is True
        assert taken.pending is None

        h.clock.advance(timedelta(minutes=5))
        still = await h.engine.advance(session.id, tenant_id=T)
        assert h.chat.sent == []  # nothing left the building
        assert still.human_in_control is True

    async def test_approve_is_refused_while_a_human_holds_the_chat(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        assert session.pending is not None
        draft_id = session.pending.id
        await h.engine.take_over(session.id, tenant_id=T)
        with pytest.raises(NegotiationError) as exc:
            await h.engine.approve(session.id, draft_id, approver="buyer-1", tenant_id=T)
        assert _code(exc) == "human_in_control"
        assert h.chat.sent == []

    async def test_resume_requires_a_previous_takeover(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        with pytest.raises(NegotiationError) as exc:
            await h.engine.resume(session.id, tenant_id=T)
        assert _code(exc) == "not_in_human_control"

    async def test_resume_returns_control_to_the_agent(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        await h.engine.take_over(session.id, tenant_id=T)
        resumed = await h.engine.resume(session.id, tenant_id=T)
        assert resumed.human_in_control is False
        assert resumed.status is NegotiationOutcome.AWAITING_SELLER

    async def test_takeover_is_refused_on_a_finished_negotiation(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        await h.engine.abort(session.id, reason="buyer_cancelled", tenant_id=T)
        with pytest.raises(NegotiationError) as exc:
            await h.engine.take_over(session.id, tenant_id=T)
        assert _code(exc) == "terminal"

    async def test_abort_is_terminal_and_keeps_the_first_reason(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        first = await h.engine.abort(session.id, reason="buyer_cancelled", tenant_id=T)
        again = await h.engine.abort(session.id, reason="other", tenant_id=T)
        assert first.status is NegotiationOutcome.ABORTED
        assert again.status is NegotiationOutcome.ABORTED
        assert again.stop_reason == "buyer_cancelled"

    async def test_every_control_rejects_another_tenant(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        for call in (
            lambda: h.engine.take_over(session.id, tenant_id="tenant-b"),
            lambda: h.engine.resume(session.id, tenant_id="tenant-b"),
            lambda: h.engine.abort(session.id, reason="x", tenant_id="tenant-b"),
        ):
            with pytest.raises(NegotiationError) as exc:
                await call()
            assert _code(exc) == "not_found"


class TestSellerExclusivity:
    async def test_a_second_mission_cannot_open_a_chat_with_a_busy_seller(self) -> None:
        h = harness(cooperative_seller())
        await h.engine.start(request(), idempotency_key="k1")
        with pytest.raises(NegotiationError) as exc:
            await h.engine.start(request(), idempotency_key="k2")
        assert _code(exc) == "seller_busy"
        assert len(h.chat.opened) == 1

    async def test_restarting_the_same_key_is_idempotent(self) -> None:
        h = harness(cooperative_seller())
        first = await h.engine.start(request(), idempotency_key="k")
        again = await h.engine.start(request(), idempotency_key="k")
        assert again.id == first.id
        assert len(h.chat.opened) == 1

    async def test_another_seller_is_not_blocked(self) -> None:
        h = harness(cooperative_seller())
        await h.engine.start(request(), idempotency_key="k1")
        other = await h.engine.start(
            replace(request(), seller_id="b-other-coop"), idempotency_key="k2"
        )
        assert other.seller_id == "b-other-coop"
        assert len(h.chat.opened) == 2

    async def test_another_tenant_may_contact_the_same_seller(self) -> None:
        h = harness(cooperative_seller())
        await h.engine.start(request(), idempotency_key="k1")
        other = await h.engine.start(replace(request(), tenant_id="tenant-b"), idempotency_key="k2")
        assert other.tenant_id == "tenant-b"

    async def test_a_terminal_outcome_frees_the_seller(self) -> None:
        h = harness(cooperative_seller())
        first = await h.engine.start(request(), idempotency_key="k1")
        await h.engine.abort(first.id, reason="buyer_cancelled", tenant_id=T)
        second = await h.engine.start(request(), idempotency_key="k2")
        assert second.id != first.id

    async def test_an_agreed_negotiation_frees_the_seller(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(params(semi_automatic=False)), idempotency_key="k1")
        session = await run_autonomous(h, session)
        assert session.status is NegotiationOutcome.AGREED
        second = await h.engine.start(request(params(semi_automatic=False)), idempotency_key="k2")
        assert second.id != session.id

    async def test_takeover_keeps_the_seller_claimed_until_abort(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k1")
        await h.engine.take_over(session.id, tenant_id=T)
        with pytest.raises(NegotiationError) as busy:
            await h.engine.start(request(), idempotency_key="k2")
        assert _code(busy) == "seller_busy"

        await h.engine.resume(session.id, tenant_id=T)
        with pytest.raises(NegotiationError):
            await h.engine.start(request(), idempotency_key="k2")

        await h.engine.abort(session.id, reason="buyer_cancelled", tenant_id=T)
        second = await h.engine.start(request(), idempotency_key="k2")
        assert second.id != session.id

    async def test_the_guard_reports_who_holds_the_seller(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        assert (
            await h.engine.seller_holder(tenant_id=T, platform="mock-b", seller_id=SELLER)
            == session.id
        )
        await h.engine.abort(session.id, reason="buyer_cancelled", tenant_id=T)
        assert (
            await h.engine.seller_holder(tenant_id=T, platform="mock-b", seller_id=SELLER) is None
        )


class TestPerSellerRateLimit:
    async def test_messages_to_one_seller_are_capped_and_retried_later(self) -> None:
        h = harness(cooperative_seller())
        for _ in range(20):
            await h.seller_log.record(tenant_id=T, platform="mock-b", seller_id=SELLER, at=NOW)
        p = params(semi_automatic=False)
        session = await h.engine.start(request(p), idempotency_key="k")

        assert h.chat.sent == []  # the opening message is parked, not sent
        assert session.pending is not None
        assert "seller_rate_limited" in session.guardrail_hits
        assert session.status is NegotiationOutcome.IN_PROGRESS

        h.clock.advance(timedelta(hours=1, minutes=1))
        session = await h.engine.advance(session.id, tenant_id=T)
        assert len(h.chat.sent) == 1

    async def test_the_configured_limit_is_the_cap_for_the_seller_too(self) -> None:
        h = harness(cooperative_seller())
        for _ in range(3):
            await h.seller_log.record(tenant_id=T, platform="mock-b", seller_id=SELLER, at=NOW)
        h.clock.advance(timedelta(minutes=1))
        p = params(semi_automatic=False, max_messages_per_hour=3)
        session = await h.engine.start(request(p), idempotency_key="k")
        assert h.chat.sent == []
        assert "seller_rate_limited" in session.guardrail_hits
        assert "account_rate_limited" not in session.guardrail_hits


class TestGuardrailEvents:
    async def test_hits_carry_the_clock_reading(self) -> None:
        h = harness(cooperative_seller())
        p = params(semi_automatic=False, max_messages_per_hour=1)
        session = await h.engine.start(request(p), idempotency_key="k")
        h.clock.advance(timedelta(minutes=1))
        session = await h.engine.advance(session.id, tenant_id=T)

        codes = {event.code for event in session.guardrail_events}
        assert {"account_rate_limited", "seller_rate_limited"} <= codes
        assert all(event.at == NOW + timedelta(minutes=1) for event in session.guardrail_events)

    async def test_the_bare_hit_list_is_still_kept(self) -> None:
        h = harness(cooperative_seller())
        p = params(semi_automatic=False, max_messages_per_hour=1)
        session = await h.engine.start(request(p), idempotency_key="k")
        session = await h.engine.advance(session.id, tenant_id=T)
        assert session.guardrail_hits == [event.code for event in session.guardrail_events]


class TestOpenRequestCarriesTheOffer:
    async def test_the_offer_id_is_persisted_for_the_api_view(self) -> None:
        h = harness(cooperative_seller())
        req: OpenRequest = replace(request(), offer_id="offer-42")
        session = await h.engine.start(req, idempotency_key="k")
        assert session.offer_id == "offer-42"

    async def test_the_mission_and_trace_are_persisted_for_event_routing(self) -> None:
        h = harness(cooperative_seller())
        req: OpenRequest = replace(request(), mission_id="m-7", trace_id="tr-9")
        session = await h.engine.start(req, idempotency_key="k")
        assert session.mission_id == "m-7"
        assert session.trace_id == "tr-9"


class TestHumanMessages:
    """A human holding the chat writes to the seller (D5-08 controls, D5-07c contract)."""

    async def test_a_human_message_is_sent_as_written_and_attributed(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        await h.engine.take_over(session.id, tenant_id=T)

        sent = await h.engine.send_human(
            session.id, "  Can you do 400?  ", author="buyer-1", tenant_id=T
        )

        assert h.chat.sent == ["Can you do 400?"]  # trimmed, otherwise untouched
        assert sent.transcript[-1].role == "human"
        assert sent.transcript[-1].text == "Can you do 400?"
        assert sent.transcript[-1].approved_by == "buyer-1"
        assert sent.human_in_control is True  # the agent still has no say

    async def test_it_is_refused_without_a_takeover(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        with pytest.raises(NegotiationError) as exc:
            await h.engine.send_human(session.id, "hello", author="buyer-1", tenant_id=T)
        assert _code(exc) == "not_in_human_control"
        assert h.chat.sent == []

    async def test_it_is_refused_on_a_finished_negotiation(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        await h.engine.abort(session.id, reason="buyer_cancelled", tenant_id=T)
        with pytest.raises(NegotiationError) as exc:
            await h.engine.send_human(session.id, "hello", author="buyer-1", tenant_id=T)
        assert _code(exc) == "terminal"

    async def test_an_empty_message_is_refused(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        await h.engine.take_over(session.id, tenant_id=T)
        with pytest.raises(NegotiationError) as exc:
            await h.engine.send_human(session.id, "   ", author="buyer-1", tenant_id=T)
        assert _code(exc) == "empty_message"
        assert h.chat.sent == []

    async def test_a_message_over_the_configured_length_is_refused(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(params(max_message_chars=200)), idempotency_key="k")
        await h.engine.take_over(session.id, tenant_id=T)
        with pytest.raises(NegotiationError) as exc:
            await h.engine.send_human(session.id, "x" * 201, author="buyer-1", tenant_id=T)
        assert _code(exc) == "message_too_long"
        assert h.chat.sent == []

    async def test_the_hourly_cap_refuses_instead_of_parking(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(
            request(params(semi_automatic=False, max_messages_per_hour=1)),
            idempotency_key="k",
        )
        assert len(h.chat.sent) == 1  # the opening message used the hour's allowance
        await h.engine.take_over(session.id, tenant_id=T)
        with pytest.raises(NegotiationError) as exc:
            await h.engine.send_human(session.id, "one more", author="buyer-1", tenant_id=T)
        assert _code(exc) == "rate_limited"
        assert len(h.chat.sent) == 1

    async def test_another_tenant_cannot_write(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        await h.engine.take_over(session.id, tenant_id=T)
        with pytest.raises(NegotiationError) as exc:
            await h.engine.send_human(session.id, "hello", author="x", tenant_id="tenant-b")
        assert _code(exc) == "not_found"
        assert h.chat.sent == []


class TestReadOne:
    async def test_get_is_tenant_checked(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        same = await h.engine.get(session.id, tenant_id=T)
        assert same.id == session.id
        with pytest.raises(NegotiationError) as exc:
            await h.engine.get(session.id, tenant_id="tenant-b")
        assert _code(exc) == "not_found"

    async def test_get_of_an_unknown_id_is_not_found(self) -> None:
        h = harness(cooperative_seller())
        with pytest.raises(NegotiationError) as exc:
            await h.engine.get("nope", tenant_id=T)
        assert _code(exc) == "not_found"
