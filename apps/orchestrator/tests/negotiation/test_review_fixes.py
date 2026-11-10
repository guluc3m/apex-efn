"""Regression tests for the TL review findings on PR #135 (one test per finding)."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from apex.negotiation.engine import NegotiationError, confirms, plan_matches
from apex.negotiation.guardrails import ConversationState, HitCode, check_outgoing
from apex.negotiation.models import Intent, NegotiationOutcome, Plan, Quote, SanityBand
from apex.negotiation.ports import ChatLine
from apex.negotiation.text import find_percentages, find_prices
from tests.negotiation.fakes import (
    NOW,
    BandSanity,
    ScriptedChat,
    SellerTurn,
    T,
    cooperative_seller,
    harness,
    params,
    request,
    run_autonomous,
)

AUTO = params(semi_automatic=False)


class TestFinding1SpelledOutCurrencies:
    @pytest.mark.parametrize(
        ("text", "currency", "minor"),
        [
            ("We could pay 2 dollars per unit.", "USD", 200),
            ("Pagaríamos 2 dólares por unidad.", "USD", 200),
            ("4,10 euros la unidad", "EUR", 410),
            ("30 yuan each", "CNY", 3000),
            ("3.20 pounds", "GBP", 320),
            ("每件30人民币", "CNY", 3000),
        ],
    )
    def test_words_are_prices(self, text: str, currency: str, minor: int) -> None:
        assert [(p.currency, p.minor) for p in find_prices(text)] == [(currency, minor)]

    def test_priceless_plans_reject_spelled_out_prices(self) -> None:
        assert not plan_matches("We could pay 2 dollars per unit.", Plan(intent=Intent.OPEN), "USD")

    def test_guardrail_blocks_spelled_out_price_below_floor(self) -> None:
        verdict = check_outgoing(
            "Could you do 1 euro per unit?", params().limits(), ConversationState(), now=NOW
        )
        assert HitCode.OFFER_BELOW_FLOOR in verdict.codes


class TestFinding9Percentages:
    @pytest.mark.parametrize(
        ("text", "bp"),
        [
            ("30% off", 3000),
            ("12.5 %", 1250),
            ("veinte por ciento? 20 por ciento", 2000),
            ("打7折", 3000),
        ],
    )
    def test_percentages_are_parsed(self, text: str, bp: int) -> None:
        assert bp in find_percentages(text)

    def test_percent_above_max_discount_is_blocked(self) -> None:
        verdict = check_outgoing(
            "Would you give us 30% off?", params().limits(), ConversationState(), now=NOW
        )
        assert HitCode.PERCENT_DISCOUNT_EXCEEDED in verdict.codes

    def test_drafts_may_not_talk_in_percentages(self) -> None:
        assert not plan_matches("Could you do 5% off?", Plan(intent=Intent.REQUEST_PRICE), "EUR")


class TestFinding2WrittenConfirmation:
    def test_confirmation_must_be_explicit_and_match(self) -> None:
        q = Quote(unit_price_minor=410, currency="EUR", at_round=3)
        assert confirms("Confirmed: EUR 4.10 per unit for 5000 units.", q)
        assert not confirms("Sorry, we cannot accept that price at all.", q)
        assert not confirms("Confirmed: EUR 4.20 per unit.", q)
        assert not confirms("Confirmed, but EUR 4.10 only for 10000 units, not 5000.", q)
        assert not confirms("OK", q)

    async def test_refusal_after_summary_goes_to_a_human(self) -> None:
        def seller(agent: str, n: int) -> str:
            if "confirm" in agent.lower():
                return "Sorry, we cannot accept that price at all."
            return "Our best price is EUR 4.10 per unit."

        h = harness(seller)
        session = await run_autonomous(h, await h.engine.start(request(AUTO), idempotency_key="k"))
        assert session.status is NegotiationOutcome.ESCALATED
        assert session.stop_reason == "summary_not_confirmed"
        assert session.agreed is None


class TestFinding3InsufficientReference:
    async def test_insufficient_reference_stops_the_negotiation(self) -> None:
        class NoReference(BandSanity):
            async def check(self, quote, *, session):  # type: ignore[no-untyped-def]
                return SanityBand.INSUFFICIENT_REFERENCE

        h = harness(lambda agent, n: "Our price is EUR 4.10 per unit.", sanity=NoReference())
        session = await run_autonomous(h, await h.engine.start(request(AUTO), idempotency_key="k"))
        assert session.status is NegotiationOutcome.STOPPED_ANOMALOUS_PRICE
        assert session.stop_reason == "sanity_insufficient_reference"
        assert len(h.chat.sent) == 1


class TestFinding4Concurrency:
    async def test_concurrent_approvals_send_once(self) -> None:
        h = harness(cooperative_seller())
        original = h.chat.send

        async def slow_send(chat_id: str, text: str) -> None:
            await asyncio.sleep(0.01)
            await original(chat_id, text)

        h.chat.send = slow_send  # type: ignore[method-assign]
        session = await h.engine.start(request(), idempotency_key="k")
        assert session.pending is not None
        draft = session.pending.id
        results = await asyncio.gather(
            h.engine.approve(session.id, draft, approver="a", tenant_id=T),
            h.engine.approve(session.id, draft, approver="b", tenant_id=T),
            return_exceptions=True,
        )
        assert len(h.chat.sent) == 1
        assert sum(isinstance(r, NegotiationError) for r in results) == 1


class TestFinding5ReadBeforeApproval:
    async def test_seller_escalation_while_a_draft_is_pending_blocks_the_send(self) -> None:
        h = harness(lambda agent, n: "Unit price is EUR 4.65.")
        session = await h.engine.start(request(), idempotency_key="k")
        assert session.pending is not None
        draft = session.pending.id
        assert h.chat.sent == []
        # The seller writes while the buyer reviews the draft.
        h.chat.lines.append(ChatLine(1, "seller", "Please send your IBAN to pay in advance."))
        with pytest.raises(NegotiationError) as err:
            await h.engine.approve(session.id, draft, approver="buyer-1", tenant_id=T)
        assert err.value.code == "draft_superseded"
        assert h.chat.sent == []
        stored = await h.store.get(session.id)
        assert stored is not None and stored.status is NegotiationOutcome.ESCALATED


class TestFinding6RecoverableStart:
    async def test_retry_after_failed_open_completes_the_start(self) -> None:
        chat = ScriptedChat(cooperative_seller())
        h = harness(cooperative_seller())
        h.chat = chat
        calls = {"n": 0}
        original_open = h.engine._transport.open

        async def flaky_open(**kwargs: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("browser worker down")
            return await original_open(**kwargs)

        h.engine._transport.open = flaky_open  # type: ignore[method-assign]
        with pytest.raises(ConnectionError):
            await h.engine.start(request(AUTO), idempotency_key="k")
        session = await h.engine.start(request(AUTO), idempotency_key="k")
        assert session.chat_id == "chat-1"
        assert session.rounds_sent == 1


class TestFinding10TenantIsolation:
    async def test_other_tenants_cannot_load_or_reuse_a_negotiation(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        with pytest.raises(NegotiationError) as err:
            await h.engine.advance(session.id, tenant_id="tenant-b")
        assert err.value.code == "not_found"
        other = request()
        object.__setattr__(other, "tenant_id", "tenant-b")
        with pytest.raises(NegotiationError):
            await h.engine.start(other, idempotency_key="k")


class TestFinding12NewSellerTurnSupersedesDraft:
    async def test_pending_draft_is_replaced_when_the_seller_writes_again(self) -> None:
        h = harness(lambda agent, n: "Unit price is EUR 4.65.")
        session = await h.engine.start(request(), idempotency_key="k")
        assert session.pending is not None
        first = session.pending.id
        h.chat.lines.append(ChatLine(1, "seller", "Our volume tiers: 1000+ units: EUR 4.40."))
        h.clock.advance(timedelta(minutes=1))
        session = await h.engine.advance(session.id, tenant_id=T)
        assert session.pending is not None and session.pending.id != first
        assert h.chat.sent == []


def echoing_seller(floor: int = 409, list_price: int = 445) -> SellerTurn:
    """Like the D5-04 mock personas: a counter-offer repeats the buyer's price before stating its own."""
    state = {"ask": list_price}

    def turn(agent: str, n: int) -> str | None:
        prices = [p.minor for p in find_prices(agent)]
        if "confirm" in agent.lower() and prices and prices[-1] >= floor:
            return f"Confirmed in writing: EUR {prices[-1] / 100:.2f} per unit for 5000 units."
        if not prices:
            return "Our volume tiers are: 500-1999 units: EUR 4.45; 2000+ units: EUR 4.15."
        offer = prices[-1]
        if offer >= floor:
            return f"OK, we can accept EUR {offer / 100:.2f} per unit."
        state["ask"] = max(floor, state["ask"] - (state["ask"] - offer) // 2)
        return (
            f"Sorry, EUR {offer / 100:.2f} is too low for us. "
            f"Our best price is EUR {state['ask'] / 100:.2f} per unit."
        )

    return turn


class TestFinding13EchoedBuyerPrices:
    """Found by the D5-09 suite against the real mock: an echoed buyer price was read as the quote."""

    async def test_echo_is_not_the_quote(self) -> None:
        h = harness(echoing_seller(), sanity=BandSanity(floor=100))
        p = params(semi_automatic=False, reference_price_minor=445)
        s = await run_autonomous(h, await h.engine.start(request(p), idempotency_key="k"))
        assert s.status is NegotiationOutcome.AGREED
        assert s.agreed is not None and s.agreed.unit_price_minor == 409
        anchor = s.ladder[0]
        assert all(q.unit_price_minor != anchor for q in s.quotes)
        assert "extraction_echoes_agent_price" in s.guardrail_hits

    async def test_summary_never_states_a_rejected_price(self) -> None:
        h = harness(echoing_seller(), sanity=BandSanity(floor=100))
        p = params(semi_automatic=False, reference_price_minor=445)
        s = await run_autonomous(h, await h.engine.start(request(p), idempotency_key="k"))
        summaries = [m.text for m in s.transcript if m.intent is Intent.SUMMARY]
        assert summaries and all("EUR 4.09" in t for t in summaries)

    async def test_acceptance_of_our_price_still_counts(self) -> None:
        """The only price in the message is ours: the seller accepted it (still needs written confirmation)."""
        h = harness(echoing_seller(floor=300), sanity=BandSanity(floor=100))
        p = params(semi_automatic=False, reference_price_minor=445)
        s = await run_autonomous(h, await h.engine.start(request(p), idempotency_key="k"))
        assert s.status is NegotiationOutcome.AGREED
        assert s.agreed is not None and s.agreed.unit_price_minor == s.ladder[0]


class TestFinding14WrittenAcceptance:
    """Found by D5-09: the mock accepts the summary with "OK, we can accept EUR 4.09 per unit for 5000 units"."""

    Q = Quote(unit_price_minor=409, currency="EUR", at_round=3)

    @pytest.mark.parametrize(
        "text",
        [
            "OK, we can accept EUR 4.09 per unit for 5000 units.",
            "We accept EUR 4.09 per unit.",
            "Aceptamos EUR 4.09 por unidad para 5000 unidades.",
            "好的，可以接受 EUR 4.09 单价。",
        ],
    )
    def test_explicit_acceptance_of_the_summary_confirms(self, text: str) -> None:
        assert confirms(text, self.Q, 5000)

    @pytest.mark.parametrize(
        "text",
        [
            "We can accept EUR 4.09 if you pay 50% upfront.",
            "We accept EUR 4.09 provided you order again next month.",
            "We can accept EUR 4.09 only for 10000 units.",
            "We can accept EUR 4.09 per unit for 3000 units.",
            "Aceptamos EUR 4.09 siempre que paguen por adelantado.",
            "如果预付，可以接受 EUR 4.09。",
            "We cannot accept EUR 4.09.",
            "Accepting is hard, EUR 4.09 is our cost.",
        ],
    )
    def test_conditional_or_different_terms_go_to_a_human(self, text: str) -> None:
        assert not confirms(text, self.Q, 5000)


class TestFinding15EchoInsideARefusal:
    async def test_truncated_refusal_is_not_an_acceptance(self) -> None:
        """The mock's ``truncated`` persona cuts "Sorry, EUR 3.79 is too low for us. Our best..." short."""

        def seller(agent: str, n: int) -> str | None:
            prices = find_prices(agent)
            if not prices:
                return "Our volume tiers are: 500-1999 units: EUR 4.45; 2000+ units: EUR 4.15."
            return f"Sorry, EUR {prices[-1].minor / 100:.2f} is too low for us. O"

        h = harness(seller, sanity=BandSanity(floor=100))
        p = params(semi_automatic=False, reference_price_minor=445)
        s = await run_autonomous(h, await h.engine.start(request(p), idempotency_key="k"))
        assert all(m.intent is not Intent.SUMMARY for m in s.transcript)
        # A refusal is never an acceptance. The seller did quote EUR 4.15 (below the 4.45 list), so #241
        # sends it to the gate with the number instead of dropping it.
        assert s.status is NegotiationOutcome.ESCALATED
        assert s.stop_reason == "best_quote_above_target"
        assert s.best_quote is not None and s.best_quote.unit_price_minor == 415
