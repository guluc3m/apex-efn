"""Guardrail tests (D5-07, spec 3.6, criterion 14 at unit level).

Property tests check the money invariant for every limit: whatever discount is configured, a drafted
price that passes the guardrail never exceeds ``max_discount``. They use a seeded generator over many
cases (hypothesis is not a dependency of the orchestrator yet; DEV-4 adds it in D4-03).
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from apex.negotiation.guardrails import (
    BP_DENOMINATOR,
    ConversationState,
    Counterpart,
    GuardrailLimits,
    HitCode,
    Severity,
    check_incoming,
    check_outgoing,
    discount_bp,
    fraction_to_bp,
    price_floor_minor,
)

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
SUPPORTED = frozenset({"EUR", "USD", "CNY"})

# Test limits only. Real values come from tenant config (neg.max_discount is unset until TL answers Q7).
LIMITS = GuardrailLimits(
    reference_price_minor=465,
    currency="EUR",
    max_discount_bp=1200,
    max_quantity=5000,
    allowed_counterparts=frozenset(),
    supported_currencies=SUPPORTED,
    max_rounds=6,
    max_tokens=20_000,
    max_messages_per_hour=10,
    max_message_chars=1200,
)
STATE = ConversationState()


def codes(
    text: str, limits: GuardrailLimits = LIMITS, state: ConversationState = STATE
) -> set[HitCode]:
    return set(check_outgoing(text, limits, state, now=NOW).codes)


class TestPriceLimits:
    def test_floor_rounds_up_so_the_limit_is_never_exceeded(self) -> None:
        # 465 * 0.88 = 409.2 -> 410: proposing 410 is a 11.83% discount, 409 would be 12.04%.
        assert price_floor_minor(LIMITS) == 410
        assert discount_bp(465, 410) <= 1200
        assert discount_bp(465, 409) > 1200

    def test_offer_at_the_floor_passes(self) -> None:
        verdict = check_outgoing(
            "With 5000 units and a recurring order, could you do EUR 4.10?", LIMITS, STATE, now=NOW
        )
        assert verdict.allowed, verdict.hits

    def test_offer_below_the_floor_is_blocked(self) -> None:
        assert {HitCode.OFFER_BELOW_FLOOR, HitCode.MAX_DISCOUNT_EXCEEDED} <= codes(
            "Could you do 4,09 €?"
        )

    def test_any_price_in_the_message_counts(self) -> None:
        assert HitCode.OFFER_BELOW_FLOOR in codes(
            "Last month we paid EUR 4.40, now we target EUR 3.00."
        )

    def test_offer_above_reference_is_blocked(self) -> None:
        assert HitCode.OFFER_ABOVE_CEILING in codes("We can go up to EUR 5.00.")

    def test_price_in_another_currency_is_blocked(self) -> None:
        assert HitCode.WRONG_CURRENCY in codes("Could you do USD 4.20?")
        assert HitCode.WRONG_CURRENCY in codes("Could you do ¥30?")

    def test_bare_numbers_are_not_prices(self) -> None:
        assert codes("We need 5000 units, delivery in 3 weeks, round 2 of our sourcing.") == set()

    def test_zero_discount_allows_only_the_reference(self) -> None:
        strict = replace(LIMITS, max_discount_bp=0)
        assert codes("EUR 4.65 is fine as a starting point", strict) == set()
        assert HitCode.OFFER_BELOW_FLOOR in codes("EUR 4.64?", strict)

    def test_any_allowed_price_respects_max_discount(self) -> None:
        rng = random.Random(20261101)
        price_codes = {
            HitCode.OFFER_BELOW_FLOOR,
            HitCode.OFFER_ABOVE_CEILING,
            HitCode.MAX_DISCOUNT_EXCEEDED,
        }
        for _ in range(3000):
            reference = rng.randint(1, 10_000_000)
            max_bp = rng.randint(0, BP_DENOMINATOR - 1)
            # Bias prices around the floor, where off-by-one mistakes live.
            floor = price_floor_minor(
                replace(LIMITS, reference_price_minor=reference, max_discount_bp=max_bp)
            )
            price = (
                max(0, floor + rng.randint(-3, 3))
                if rng.random() < 0.7
                else rng.randint(0, 2 * reference)
            )
            limits = replace(LIMITS, reference_price_minor=reference, max_discount_bp=max_bp)
            text = f"Could you do EUR {price // 100}.{price % 100:02d}?"
            verdict = check_outgoing(text, limits, STATE, now=NOW)
            if not (verdict.codes & price_codes):
                assert price <= reference
                assert (reference - price) * BP_DENOMINATOR <= max_bp * reference

    def test_floor_is_the_lowest_compliant_price(self) -> None:
        rng = random.Random(7)
        for _ in range(3000):
            reference = rng.randint(1, 10_000_000)
            max_bp = rng.randint(0, BP_DENOMINATOR - 1)
            limits = replace(LIMITS, reference_price_minor=reference, max_discount_bp=max_bp)
            floor = price_floor_minor(limits)
            assert (reference - floor) * BP_DENOMINATOR <= max_bp * reference
            assert (reference - (floor - 1)) * BP_DENOMINATOR > max_bp * reference


class TestFractionToBp:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0.12, 1200), ("0.125", 1250), (0, 0), (0.33333, 3333), ("0.99995", 9999)],
    )
    def test_rounds_down(self, value: float | str, expected: int) -> None:
        assert fraction_to_bp(value) == expected

    @pytest.mark.parametrize("value", [-0.01, 1, 1.5])
    def test_rejects_out_of_range(self, value: float) -> None:
        with pytest.raises(ValueError):
            fraction_to_bp(value)


class TestVolumeAndCounterparts:
    def test_more_volume_than_requested_is_blocked(self) -> None:
        found = codes("We could raise the order to 8000 units if the price is right.")
        assert {HitCode.VOLUME_EXCEEDED, HitCode.UNAUTHORIZED_COUNTERPART} <= found

    def test_requested_volume_is_fine(self) -> None:
        assert codes("For 5,000 units, what tiers do you offer?") == set()

    @pytest.mark.parametrize(
        ("text", "counterpart"),
        [
            ("We can prepay 30% if you lower the price.", Counterpart.PREPAYMENT),
            ("We could sign a framework agreement for 12 months.", Counterpart.FRAMEWORK_CONTRACT),
            ("We can offer net 60 payment terms.", Counterpart.PAYMENT_TERMS),
            ("We can provide a letter of credit.", Counterpart.GUARANTEE),
            ("We accept a penalty clause for late payment.", Counterpart.PENALTY),
            ("Podemos pagar por adelantado el 50%.", Counterpart.PREPAYMENT),
        ],
    )
    def test_counterparts_need_profile_authorisation(
        self, text: str, counterpart: Counterpart
    ) -> None:
        verdict = check_outgoing(text, LIMITS, STATE, now=NOW)
        assert HitCode.UNAUTHORIZED_COUNTERPART in verdict.codes
        assert counterpart in verdict.counterparts
        allowed = replace(LIMITS, allowed_counterparts=frozenset({counterpart}))
        assert HitCode.UNAUTHORIZED_COUNTERPART not in codes(text, allowed)


class TestCommitmentAndLeaks:
    @pytest.mark.parametrize(
        "text",
        [
            "We accept your offer of EUR 4.20.",
            "It's a deal!",
            "Trato hecho, confirmamos el pedido.",
            "成交",
        ],
    )
    def test_never_accepts_a_binding_commitment(self, text: str) -> None:
        assert HitCode.BINDING_COMMITMENT in codes(text)

    def test_asking_for_written_confirmation_is_fine(self) -> None:
        text = (
            "Could you please confirm the final conditions in writing? Our team will review them."
        )
        assert codes(text) == set()

    def test_sensitive_data_in_a_draft_escalates(self) -> None:
        verdict = check_outgoing(
            "Our IBAN is ES91 2100 0418 4502 0005 1332.", LIMITS, STATE, now=NOW
        )
        assert HitCode.SENSITIVE_DATA_IN_DRAFT in verdict.codes
        assert verdict.escalate

    @pytest.mark.parametrize(
        "text",
        [
            "Write me at buyer@example.com",
            "Call me on +34 600 123 456",
            "Let's continue on WhatsApp",
        ],
    )
    def test_never_moves_contact_off_platform(self, text: str) -> None:
        assert HitCode.OFF_PLATFORM_CONTACT_IN_DRAFT in codes(text)

    def test_empty_and_long_drafts(self) -> None:
        assert HitCode.EMPTY_MESSAGE in codes("   ")
        assert HitCode.MESSAGE_TOO_LONG in codes("a" * 1201)


class TestConversationLimits:
    def test_max_rounds_escalates(self) -> None:
        verdict = check_outgoing("Thanks!", LIMITS, ConversationState(rounds_sent=6), now=NOW)
        assert HitCode.MAX_ROUNDS_REACHED in verdict.codes
        assert verdict.escalate

    def test_token_budget_counts_the_draft(self) -> None:
        state = ConversationState(tokens_used=19_500)
        assert check_outgoing("Thanks!", LIMITS, state, now=NOW, draft_tokens=400).allowed
        verdict = check_outgoing("Thanks!", LIMITS, state, now=NOW, draft_tokens=501)
        assert HitCode.TOKEN_BUDGET_EXHAUSTED in verdict.codes

    def test_rate_limit_uses_a_rolling_hour(self) -> None:
        sends = [NOW - timedelta(minutes=5 * i) for i in range(10)]
        assert HitCode.ACCOUNT_RATE_LIMITED in codes(
            "Thanks!", state=ConversationState(account_sends=sends)
        )
        older = [NOW - timedelta(minutes=61 + i) for i in range(50)]
        assert codes("Thanks!", state=ConversationState(account_sends=older)) == set()

    def test_human_in_control_blocks_the_agent(self) -> None:
        verdict = check_outgoing(
            "Thanks!", LIMITS, ConversationState(human_in_control=True), now=NOW
        )
        assert verdict.codes == {HitCode.HUMAN_IN_CONTROL}
        assert not verdict.allowed


class TestLimitsValidation:
    @pytest.mark.parametrize(
        "change",
        [
            {"reference_price_minor": 0},
            {"max_discount_bp": BP_DENOMINATOR},
            {"max_discount_bp": -1},
            {"max_rounds": 0},
            {"max_tokens": 0},
            {"max_messages_per_hour": 0},
            {"max_quantity": 0},
            {"currency": "GBP"},
        ],
    )
    def test_rejects_invalid_limits(self, change: dict[str, object]) -> None:
        with pytest.raises(ValueError):
            replace(LIMITS, **change)  # type: ignore[arg-type]


class TestIncoming:
    """Seller messages modelled on the mock marketplace personas (D5-04)."""

    def test_cooperative_reply_is_clean(self) -> None:
        verdict = check_incoming(
            "Our volume tiers are: 300-999 units: EUR 4.65; 1000+ units: EUR 4.40.",
            supported_currencies=SUPPORTED,
        )
        assert verdict.hits == ()
        assert [p.minor for p in verdict.prices] == [465, 440]

    @pytest.mark.parametrize(
        ("text", "code"),
        [
            (
                "For this volume better we talk on WhatsApp +00 000 000 000, I can give special price there.",
                HitCode.SELLER_OFF_PLATFORM_CONTACT,
            ),
            (
                "If you pay by direct bank transfer outside the platform I can give 5% extra discount.",
                HitCode.SELLER_OFF_PLATFORM_PAYMENT,
            ),
            (
                "Before we continue please send your company tax ID and the bank account details.",
                HitCode.SELLER_ASKS_SENSITIVE_DATA,
            ),
            ("请提供护照复印件和银行账户。", HitCode.SELLER_ASKS_SENSITIVE_DATA),
        ],
    )
    def test_escalates(self, text: str, code: HitCode) -> None:
        verdict = check_incoming(text, supported_currencies=SUPPORTED)
        assert code in verdict.codes
        assert verdict.escalate

    def test_closing_pressure_is_a_notice_not_a_stop(self) -> None:
        verdict = check_incoming(
            "Our best price is EUR 4.50 per unit. This price is only valid if you close TODAY.",
            supported_currencies=SUPPORTED,
        )
        assert HitCode.SELLER_CLOSING_PRESSURE in verdict.codes
        assert all(h.severity is Severity.NOTICE for h in verdict.hits)
        assert not verdict.escalate

    def test_unsupported_currency_is_flagged(self) -> None:
        verdict = check_incoming(
            "Unit price is GBP 3.98, minimum order 300 units.", supported_currencies=SUPPORTED
        )
        assert HitCode.SELLER_UNSUPPORTED_CURRENCY in verdict.codes
        assert not verdict.escalate

    def test_anomalous_prices_are_returned_for_the_sanity_recheck(self) -> None:
        # Judging the price is DEV-3's sanity engine; the guardrail only extracts it.
        verdict = check_incoming(
            "Special clearance price just for you: EUR 1.63 per unit, any quantity.",
            supported_currencies=SUPPORTED,
        )
        assert verdict.hits == ()
        assert verdict.prices[0].minor == 163
