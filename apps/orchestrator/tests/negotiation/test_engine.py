"""Negotiation engine tests (D5-07b): playbook, guardrails on every send, sanity re-check, approvals."""

from __future__ import annotations

from datetime import timedelta

import pytest

from apex.negotiation.engine import NegotiationError, plan_matches
from apex.negotiation.guardrails import BP_DENOMINATOR, discount_bp
from apex.negotiation.models import Intent, NegotiationOutcome, Plan
from apex.negotiation.playbook import counter_ladder, target_price_minor
from apex.negotiation.text import find_prices
from tests.negotiation.fakes import (
    BandSanity,
    RegexExtractor,
    T,
    TemplateDrafter,
    cooperative_seller,
    harness,
    params,
    request,
    run_autonomous,
    run_semi_automatic,
)

AUTO = params(semi_automatic=False)


def agent_prices(sent: list[str]) -> list[int]:
    return [p.minor for text in sent for p in find_prices(text)]


class TestLadder:
    def test_increments_never_grow_and_end_at_target(self) -> None:
        ladder = counter_ladder(396, 428, 4)
        assert ladder[0] == 396 and ladder[-1] == 428
        steps = [b - a for a, b in zip(ladder, ladder[1:], strict=False)]
        assert all(s > 0 for s in steps)
        assert steps == sorted(steps, reverse=True)

    @pytest.mark.parametrize(
        ("anchor", "target", "rungs"), [(100, 100, 3), (100, 101, 5), (1, 10_000, 1)]
    )
    def test_edge_cases(self, anchor: int, target: int, rungs: int) -> None:
        ladder = counter_ladder(anchor, target, rungs)
        assert ladder[0] == anchor and ladder[-1] == target
        assert ladder == sorted(set(ladder))

    def test_target_price_rounds_up(self) -> None:
        assert target_price_minor(465, 800) == 428
        assert discount_bp(465, 428) <= 800


class TestPlanMatch:
    def test_draft_must_state_exactly_the_planned_price(self) -> None:
        plan = Plan(intent=Intent.COUNTER, price_minor=410)
        assert plan_matches("Could we agree on EUR 4.10 per unit?", plan, "EUR")
        assert not plan_matches("Could we agree on EUR 4.20 per unit?", plan, "EUR")
        assert not plan_matches("Could we agree on 4.10 USD?", plan, "EUR")
        assert not plan_matches("Could we agree on a lower price?", plan, "EUR")

    def test_no_price_plans_must_not_mention_prices(self) -> None:
        plan = Plan(intent=Intent.OPEN)
        assert plan_matches("What volume tiers do you offer?", plan, "EUR")
        assert not plan_matches("Would EUR 3.00 work?", plan, "EUR")


class TestAutonomousFlow:
    async def test_cooperative_seller_reaches_agreement_within_limits(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(AUTO), idempotency_key="k1")
        session = await run_autonomous(h, session)

        assert session.status is NegotiationOutcome.AGREED
        assert session.agreed is not None
        assert session.agreed.unit_price_minor <= target_price_minor(465, 800)
        assert "tiers" in h.chat.sent[0].lower()  # step 3: tiers before any discount
        assert "confirm" in h.chat.sent[-1].lower()  # step 7: written summary
        for price in agent_prices(h.chat.sent):
            assert (465 - price) * BP_DENOMINATOR <= 1500 * 465  # never beyond max_discount
        offers = agent_prices(h.chat.sent[:-1])
        assert offers == sorted(offers)  # the ladder only goes up

    async def test_start_is_idempotent(self) -> None:
        h = harness(cooperative_seller())
        a = await h.engine.start(request(AUTO), idempotency_key="k1")
        b = await h.engine.start(request(AUTO), idempotency_key="k1")
        assert a.id == b.id
        assert len(h.chat.opened) == 1
        assert len(h.chat.sent) == 1

    async def test_stubborn_seller_ends_without_agreement(self) -> None:
        h = harness(lambda agent, n: "Our price is EUR 4.65 per unit, no discounts.")
        session = await run_autonomous(h, await h.engine.start(request(AUTO), idempotency_key="k"))
        assert session.status is NegotiationOutcome.NO_AGREEMENT
        assert session.rounds_sent <= AUTO.max_rounds

    async def test_waits_for_the_seller(self) -> None:
        h = harness(lambda agent, n: None)
        session = await h.engine.start(request(AUTO), idempotency_key="k")
        session = await h.engine.advance(session.id, tenant_id=T)
        assert session.status is NegotiationOutcome.AWAITING_SELLER
        assert len(h.chat.sent) == 1


class TestStopsAndEscalations:
    @pytest.mark.parametrize(
        "reply",
        [
            "For this volume better we talk on WhatsApp +00 000 000 000, I can give special price there.",
            "If you pay by direct bank transfer outside the platform I can give 5% extra discount.",
            "Before we continue please send your company tax ID and the bank account details.",
        ],
    )
    async def test_escalates_on_off_platform_or_sensitive_requests(self, reply: str) -> None:
        h = harness(lambda agent, n: reply)
        session = await run_autonomous(h, await h.engine.start(request(AUTO), idempotency_key="k"))
        assert session.status is NegotiationOutcome.ESCALATED
        assert len(h.chat.sent) == 1  # nothing sent after the request

    async def test_anomalous_price_stops_for_the_gate(self) -> None:
        h = harness(lambda agent, n: "Special clearance price just for you: EUR 1.63 per unit.")
        session = await run_autonomous(h, await h.engine.start(request(AUTO), idempotency_key="k"))
        assert session.status is NegotiationOutcome.STOPPED_ANOMALOUS_PRICE
        assert session.stop_reason == "sanity_atypical"
        assert h.sanity.checked[-1].unit_price_minor == 163
        assert len(h.chat.sent) == 1

    async def test_unsupported_currency_asks_for_the_negotiation_currency(self) -> None:
        def seller(agent: str, n: int) -> str:
            if "confirm" in agent.lower():
                return "Confirmed: EUR 4.20 per unit for 5000 units."
            return (
                "Sure, in EUR: EUR 4.20 per unit." if "EUR" in agent else "Unit price is GBP 3.98."
            )

        h = harness(seller)
        session = await run_autonomous(h, await h.engine.start(request(AUTO), idempotency_key="k"))
        assert "quote in EUR" in h.chat.sent[1]
        assert "seller_unsupported_currency" in session.notices
        assert session.status is NegotiationOutcome.AGREED

    async def test_closing_pressure_never_leads_to_acceptance(self) -> None:
        h = harness(lambda agent, n: "Our best price is EUR 4.50. Only valid if you close TODAY.")
        session = await run_autonomous(h, await h.engine.start(request(AUTO), idempotency_key="k"))
        assert "seller_closing_pressure" in session.notices
        assert session.status is NegotiationOutcome.NO_AGREEMENT
        assert all("accept" not in s.lower() for s in h.chat.sent)


class TestLLMIsUntrusted:
    async def test_off_plan_and_unsafe_drafts_fall_back_to_the_template(self) -> None:
        drafter = TemplateDrafter(
            overrides=[
                "Hi! We accept your offer, send the invoice.",  # binding commitment
                "Hi! Can you do EUR 1.00? We can prepay.",  # off plan
            ]
        )
        h = harness(cooperative_seller(), drafter=drafter)
        await h.engine.start(request(AUTO), idempotency_key="k")
        assert "tiers" in h.chat.sent[0].lower()
        session = await h.store.get("id-1")
        assert session is not None
        assert "draft_off_plan" in session.guardrail_hits

    async def test_llm_down_uses_templates(self) -> None:
        h = harness(cooperative_seller(), drafter=TemplateDrafter(fail=True))
        session = await run_autonomous(h, await h.engine.start(request(AUTO), idempotency_key="k"))
        assert session.status is NegotiationOutcome.AGREED

    async def test_ungrounded_extraction_is_ignored(self) -> None:
        # The extractor claims EUR 1.00 but the seller wrote EUR 4.40: the engine keeps EUR 4.40.
        h = harness(
            lambda agent, n: "Unit price is EUR 4.40.",
            extractor=RegexExtractor(lie=100),
            sanity=BandSanity(floor=300),
        )
        session = await h.engine.start(request(AUTO), idempotency_key="k")
        session = await h.engine.advance(session.id, tenant_id=T)
        assert session.quotes[-1].unit_price_minor == 440
        assert "extraction_not_grounded" in session.guardrail_hits


class TestSemiAutomatic:
    async def test_nothing_is_sent_without_approval(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        assert session.status is NegotiationOutcome.AWAITING_HUMAN_APPROVAL
        assert session.pending is not None
        assert h.chat.sent == []
        session = await h.engine.advance(session.id, tenant_id=T)
        assert h.chat.sent == []

    async def test_approved_messages_flow_to_agreement(self) -> None:
        h = harness(cooperative_seller())
        session = await run_semi_automatic(h, await h.engine.start(request(), idempotency_key="k"))
        assert session.status is NegotiationOutcome.AGREED
        assert all(m.approved_by == "buyer-1" for m in session.transcript if m.role == "agent")

    async def test_wrong_draft_id_is_rejected(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        with pytest.raises(NegotiationError) as err:
            await h.engine.approve(session.id, "nope", approver="buyer-1", tenant_id=T)
        assert err.value.code == "draft_not_pending"

    async def test_reject_replaces_the_draft_with_the_template(self) -> None:
        h = harness(
            cooperative_seller(),
            drafter=TemplateDrafter(overrides=["What tiers do you have for us?"]),
        )
        session = await h.engine.start(request(), idempotency_key="k")
        assert session.pending is not None and session.pending.source == "llm"
        session = await h.engine.reject(session.id, session.pending.id, tenant_id=T)
        assert session.pending is not None and session.pending.source == "template"


class TestHumanControl:
    async def test_takeover_blocks_the_agent_until_resume(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        assert session.pending is not None
        draft_id = session.pending.id
        session = await h.engine.take_over(session.id, tenant_id=T)
        assert session.pending is None
        with pytest.raises(NegotiationError):
            await h.engine.approve(session.id, draft_id, approver="buyer-1", tenant_id=T)
        session = await h.engine.advance(session.id, tenant_id=T)
        assert h.chat.sent == []
        session = await h.engine.resume(session.id, tenant_id=T)
        assert not session.human_in_control

    async def test_abort_is_terminal_and_idempotent(self) -> None:
        h = harness(cooperative_seller())
        session = await h.engine.start(request(), idempotency_key="k")
        session = await h.engine.abort(session.id, reason="buyer_cancelled", tenant_id=T)
        assert session.status is NegotiationOutcome.ABORTED
        again = await h.engine.abort(session.id, reason="other", tenant_id=T)
        assert again.stop_reason == "buyer_cancelled"
        with pytest.raises(NegotiationError):
            await h.engine.resume(session.id, tenant_id=T)


class TestRateLimit:
    async def test_rate_limited_messages_wait_instead_of_failing(self) -> None:
        h = harness(cooperative_seller())
        p = params(semi_automatic=False, max_messages_per_hour=1)
        session = await h.engine.start(request(p), idempotency_key="k")
        assert len(h.chat.sent) == 1
        session = await h.engine.advance(session.id, tenant_id=T)
        assert len(h.chat.sent) == 1  # second message parked by the hourly limit
        assert session.pending is not None
        h.clock.advance(timedelta(minutes=61))
        session = await h.engine.advance(session.id, tenant_id=T)
        assert len(h.chat.sent) == 2


class TestTemplates:
    @pytest.mark.parametrize("intent", list(Intent))
    def test_every_template_passes_the_plan_check_in_both_languages(self, intent: Intent) -> None:
        from apex.negotiation.models import NegotiationContext, NegotiationSession
        from apex.negotiation.templates import render

        price = 410 if intent in (Intent.ANCHOR, Intent.COUNTER, Intent.SUMMARY) else None
        plan = Plan(intent=intent, price_minor=price)
        for language in ("en", "es"):
            p = params(
                language=language,
                context=NegotiationContext(
                    product_title="kraft box",
                    deadline="2026-12-01",
                    destination="Madrid",
                    recurring=True,
                ),
            )
            session = NegotiationSession(
                id="n",
                tenant_id="t",
                platform="mock-b",
                seller_id="s",
                product_id="p",
                account_id="a",
                config_version="1",
                params=p,
            )
            text = render(plan, session)
            assert plan_matches(text, plan, "EUR"), text
            assert "2026-12-01" in render(Plan(intent=Intent.OPEN), session)
