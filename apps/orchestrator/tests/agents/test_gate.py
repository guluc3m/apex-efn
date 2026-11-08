"""GateAgent (D4-11): queue causes, blocking rules with reasons (criteria 11, 16) and signed actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apex.agents.gate import (
    ActionBlocked,
    BlockedReason,
    DealAction,
    DiscardReason,
    GateAgent,
    GateCause,
    GateDeps,
    GateItemStatus,
    GateQueueItem,
    GateResolution,
    GateRules,
    InMemoryGateStore,
    QueueAction,
    deal_view,
)
from apex.agents.offers import Offer, OfferAnalysis
from apex.agents.ports import (
    ConfidenceBand,
    DecisionRef,
    FitOutcome,
    PriceBand,
    SanityOutcome,
    TrustOutcome,
)
from apex.common.clock import FixedClock

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
RULES = GateRules(sla_hours=24, max_renegotiations=1, stretch_gate_threshold_eur_minor=500_000)


class _Decisions:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create_decision(
        self, type: str, subject_ref: str, payload: Any, *, tenant_id: str
    ) -> DecisionRef:
        self.created.append(
            {
                "type": type,
                "subject_ref": subject_ref,
                "payload": dict(payload),
                "tenant_id": tenant_id,
            }
        )
        return DecisionRef(id=f"d{len(self.created)}", status="pending_signature")

    async def require_signed(self, decision_id: str, *, tenant_id: str) -> Any:
        raise NotImplementedError

    async def sign_service_event(self, service: str, payload: Any, *, tenant_id: str) -> str:
        return "sig"


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> str:
        self.n += 1
        return f"g{self.n}"


def _agent() -> tuple[GateAgent, InMemoryGateStore, _Decisions]:
    store = InMemoryGateStore()
    decisions = _Decisions()
    agent = GateAgent(
        GateDeps(store=store, decisions=decisions, clock=FixedClock(NOW), ids=_Ids())  # type: ignore[arg-type]
    )
    return agent, store, decisions


def _offer(**overrides: Any) -> Offer:
    base: dict[str, Any] = {
        "id": "o-1",
        "tenant_id": TENANT,
        "mission_id": "m-1",
        "platform_id": "mock-a",
        "seller_id": "s-1",
        "product_id": "p-1",
        "unit_price_eur_minor": 412,
        "list_price_eur_minor": None,
        "currency": "EUR",
        "quantity": 100,
        "collected_at": NOW,
        "raw_signals": {},
    }
    return Offer(**{**base, **overrides})


def _analysis(
    *,
    price: PriceBand = PriceBand.NORMAL,
    confidence: ConfidenceBand = ConfidenceBand.HIGH,
    verdict: str = "within_budget",
    stale: bool = False,
    fx: bool = False,
) -> OfferAnalysis:
    return OfferAnalysis(
        offer_id="o-1",
        confidence=TrustOutcome(band=confidence, score=80, model_version="trust-v3"),
        sanity=SanityOutcome(band=price, config_version="cfg-7"),
        fit=FitOutcome(verdict=verdict, financials_stale=stale, fx_provisional=fx),  # type: ignore[arg-type]
        analysed_at=NOW,
    )


# ----- causes ------------------------------------------------------------------------------------


def test_a_clean_offer_needs_no_human() -> None:
    agent, _, _ = _agent()
    assert agent.causes_for(_offer(), _analysis(), RULES) == []


@pytest.mark.parametrize(
    ("price", "cause"),
    [
        (PriceBand.ATYPICAL, GateCause.PRICE_ATYPICAL),
        (PriceBand.INSUFFICIENT_REFERENCE, GateCause.PRICE_INSUFFICIENT_REFERENCE),
    ],
)
def test_price_bands_that_need_a_human(price: PriceBand, cause: GateCause) -> None:
    agent, _, _ = _agent()
    assert agent.causes_for(_offer(), _analysis(price=price), RULES) == [cause]


@pytest.mark.parametrize(
    ("confidence", "cause"),
    [
        (ConfidenceBand.LOW, GateCause.SELLER_LOW),
        (ConfidenceBand.INSUFFICIENT_DATA, GateCause.SELLER_INSUFFICIENT_DATA),
    ],
)
def test_seller_bands_that_need_a_human(confidence: ConfidenceBand, cause: GateCause) -> None:
    agent, _, _ = _agent()
    assert agent.causes_for(_offer(), _analysis(confidence=confidence), RULES) == [cause]


def test_out_of_budget_and_stale_financials_are_causes() -> None:
    agent, _, _ = _agent()
    causes = agent.causes_for(
        _offer(), _analysis(verdict="out_of_budget", stale=True, fx=True), RULES
    )
    assert causes == [GateCause.OUT_OF_BUDGET, GateCause.FINANCIALS_STALE, GateCause.FX_PROVISIONAL]


def test_stretch_only_goes_to_the_gate_above_the_threshold() -> None:
    agent, _, _ = _agent()
    small = _offer(unit_price_eur_minor=100, quantity=10)  # 1,000 total
    big = _offer(unit_price_eur_minor=10_000, quantity=100)  # 1,000,000 total
    assert agent.causes_for(small, _analysis(verdict="stretch"), RULES) == []
    assert agent.causes_for(big, _analysis(verdict="stretch"), RULES) == [
        GateCause.STRETCH_ABOVE_THRESHOLD
    ]


# ----- enqueue -----------------------------------------------------------------------------------


async def test_enqueue_creates_one_item_with_an_sla_and_never_duplicates() -> None:
    agent, store, _ = _agent()
    first = await agent.enqueue(
        tenant_id=TENANT, offer=_offer(), analysis=_analysis(price=PriceBand.ATYPICAL), rules=RULES
    )
    second = await agent.enqueue(
        tenant_id=TENANT, offer=_offer(), analysis=_analysis(price=PriceBand.ATYPICAL), rules=RULES
    )
    assert first is not None and second is not None and first.id == second.id
    assert first.sla_due_at == NOW + timedelta(hours=24)
    assert first.causes == [GateCause.PRICE_ATYPICAL]
    assert len(await store.list_open(TENANT)) == 1


async def test_a_clean_offer_is_not_enqueued() -> None:
    agent, store, _ = _agent()
    assert (
        await agent.enqueue(tenant_id=TENANT, offer=_offer(), analysis=_analysis(), rules=RULES)
        is None
    )
    assert await store.list_open(TENANT) == []


async def test_queue_is_tenant_scoped_and_ordered_by_sla() -> None:
    agent, store, _ = _agent()
    await agent.enqueue(
        tenant_id=TENANT, offer=_offer(), analysis=_analysis(price=PriceBand.ATYPICAL), rules=RULES
    )
    assert await store.list_open("tenant-b") == []
    assert len(await agent.list_open(tenant_id=TENANT)) == 1


# ----- criterion 11: bands block purchase without a signed unblock -------------------------------


@pytest.mark.parametrize("price", [PriceBand.ATYPICAL, PriceBand.IMPLAUSIBLE])
@pytest.mark.parametrize(
    "confidence", [ConfidenceBand.LOW, ConfidenceBand.UNTRUSTED, ConfidenceBand.INSUFFICIENT_DATA]
)
async def test_follow_is_blocked_for_risky_bands_without_an_unblock(
    price: PriceBand, confidence: ConfidenceBand
) -> None:
    agent, _, _ = _agent()
    blocked = agent.blocked_deal_actions(
        offer=_offer(),
        analysis=_analysis(price=price, confidence=confidence),
        rules=RULES,
        renegotiations_used=0,
        gate_item=None,
    )
    reasons = {b.reason for b in blocked}
    assert BlockedReason.PRICE_BAND_REQUIRES_UNBLOCK in reasons
    assert BlockedReason.SELLER_BAND_REQUIRES_UNBLOCK in reasons
    assert all(b.action == "follow" for b in blocked)


async def test_a_signed_unblock_lifts_the_band_block_but_not_the_others() -> None:
    agent, _, _ = _agent()
    item = GateQueueItem(
        id="g1",
        tenant_id=TENANT,
        mission_id="m-1",
        offer_id="o-1",
        causes=[GateCause.PRICE_ATYPICAL],
        created_at=NOW,
        sla_due_at=NOW,
        resolution=GateResolution.UNBLOCKED,
    )
    blocked = agent.blocked_deal_actions(
        offer=_offer(),
        analysis=_analysis(price=PriceBand.ATYPICAL, stale=True),
        rules=RULES,
        renegotiations_used=0,
        gate_item=item,
    )
    reasons = {b.reason for b in blocked}
    assert BlockedReason.PRICE_BAND_REQUIRES_UNBLOCK not in reasons
    assert BlockedReason.FINANCIALS_STALE in reasons


@pytest.mark.parametrize(
    ("verdict", "stale", "fx", "reason"),
    [
        ("out_of_budget", False, False, BlockedReason.OUT_OF_BUDGET),
        ("within_budget", True, False, BlockedReason.FINANCIALS_STALE),
        ("within_budget", False, True, BlockedReason.FX_PROVISIONAL),
    ],
)
async def test_financial_blocks(verdict: str, stale: bool, fx: bool, reason: BlockedReason) -> None:
    agent, _, _ = _agent()
    blocked = agent.blocked_deal_actions(
        offer=_offer(),
        analysis=_analysis(verdict=verdict, stale=stale, fx=fx),
        rules=RULES,
        renegotiations_used=0,
        gate_item=None,
    )
    assert reason in {b.reason for b in blocked}


async def test_renegotiate_is_blocked_at_the_limit() -> None:
    agent, _, _ = _agent()
    blocked = agent.blocked_deal_actions(
        offer=_offer(), analysis=_analysis(), rules=RULES, renegotiations_used=1, gate_item=None
    )
    assert [(b.action, b.reason) for b in blocked] == [
        ("renegotiate", BlockedReason.RENEGOTIATION_LIMIT)
    ]


async def test_a_resolved_item_blocks_everything() -> None:
    agent, _, _ = _agent()
    item = GateQueueItem(
        id="g1", tenant_id=TENANT, mission_id="m-1", offer_id="o-1",
        causes=[GateCause.PRICE_ATYPICAL], created_at=NOW, sla_due_at=NOW,
        status=GateItemStatus.RESOLVED, resolution=GateResolution.DISCARDED,
    )  # fmt: skip
    blocked = agent.blocked_deal_actions(
        offer=_offer(), analysis=_analysis(), rules=RULES, renegotiations_used=0, gate_item=item
    )
    assert [b.reason for b in blocked] == [BlockedReason.ALREADY_DECIDED]


# ----- criterion 16: the deal view explains what is allowed ----------------------------------------


async def test_deal_view_lists_allowed_actions_and_every_block_with_its_reason() -> None:
    agent, _, _ = _agent()
    analysis = _analysis(price=PriceBand.ATYPICAL, stale=True)
    blocked = agent.blocked_deal_actions(
        offer=_offer(), analysis=analysis, rules=RULES, renegotiations_used=1, gate_item=None
    )
    deal = deal_view(offer=_offer(), analysis=analysis, gate_item=None, blocked=blocked)
    assert "follow" not in deal.allowed_actions
    assert "renegotiate" not in deal.allowed_actions
    assert {"takeover", "hold", "discard"} <= set(deal.allowed_actions)
    assert all(b.detail for b in blocked), "every block must explain itself"


# ----- signed actions ----------------------------------------------------------------------------


async def test_a_follow_creates_a_signed_decision_with_the_full_payload() -> None:
    agent, _, decisions = _agent()
    decision = await agent.decide_deal_action(
        tenant_id=TENANT,
        offer=_offer(),
        analysis=_analysis(),
        action=DealAction.FOLLOW,
        rules=RULES,
        renegotiations_used=0,
        gate_item=None,
    )
    assert decision.status == "pending_signature"
    created = decisions.created[0]
    assert created["type"] == "deal_action"
    assert created["subject_ref"] == "offer:m-1:o-1"
    payload = created["payload"]
    assert payload["action"] == "follow"
    assert payload["price_band"] == "normal"
    assert payload["seller_confidence"]["model_version"] == "trust-v3"
    assert payload["financial_verdict"] == "within_budget"
    assert payload["config_version"] == "cfg-7"


async def test_a_blocked_action_creates_no_decision_and_lists_every_reason() -> None:
    agent, _, decisions = _agent()
    with pytest.raises(ActionBlocked) as caught:
        await agent.decide_deal_action(
            tenant_id=TENANT,
            offer=_offer(),
            analysis=_analysis(price=PriceBand.ATYPICAL, verdict="out_of_budget"),
            action=DealAction.FOLLOW,
            rules=RULES,
            renegotiations_used=0,
            gate_item=None,
        )
    reasons = {b.reason for b in caught.value.blocked}
    assert BlockedReason.PRICE_BAND_REQUIRES_UNBLOCK in reasons
    assert BlockedReason.OUT_OF_BUDGET in reasons
    assert decisions.created == []


async def test_a_discard_needs_a_closed_reason_code() -> None:
    agent, _, decisions = _agent()
    with pytest.raises(ActionBlocked) as caught:
        await agent.decide_deal_action(
            tenant_id=TENANT,
            offer=_offer(),
            analysis=_analysis(),
            action=DealAction.DISCARD,
            rules=RULES,
            renegotiations_used=0,
            gate_item=None,
        )
    assert BlockedReason.COMMENT_REQUIRED in {b.reason for b in caught.value.blocked}
    await agent.decide_deal_action(
        tenant_id=TENANT,
        offer=_offer(),
        analysis=_analysis(),
        action=DealAction.DISCARD,
        rules=RULES,
        renegotiations_used=0,
        gate_item=None,
        discard_reason=DiscardReason.PRICE_TOO_HIGH,
        comment="overpriced",
    )
    assert decisions.created[0]["payload"]["discard_reason"] == "price_too_high"


async def test_unblock_creates_a_gate_decision() -> None:
    agent, store, decisions = _agent()
    item = await agent.enqueue(
        tenant_id=TENANT, offer=_offer(), analysis=_analysis(price=PriceBand.ATYPICAL), rules=RULES
    )
    assert item is not None
    await agent.decide_queue_action(tenant_id=TENANT, item_id=item.id, action=QueueAction.UNBLOCK)
    created = decisions.created[0]
    assert created["type"] == "gate_unblock"
    assert created["payload"]["gate_item_id"] == item.id
    assert created["payload"]["causes"] == ["price_atypical"]


@pytest.mark.parametrize("roles", [[], ["buyer"], ["viewer"]])
async def test_override_discard_is_limited_to_finance_admin_owner(roles: list[str]) -> None:
    agent, _, decisions = _agent()
    item = await agent.enqueue(
        tenant_id=TENANT, offer=_offer(), analysis=_analysis(price=PriceBand.ATYPICAL), rules=RULES
    )
    assert item is not None
    with pytest.raises(ActionBlocked) as caught:
        await agent.decide_queue_action(
            tenant_id=TENANT, item_id=item.id, action=QueueAction.OVERRIDE_DISCARD, roles=roles,
            comment="justified",
        )  # fmt: skip
    assert BlockedReason.ROLE_NOT_ALLOWED in {b.reason for b in caught.value.blocked}
    assert decisions.created == []


@pytest.mark.parametrize("role", ["finance", "admin", "owner"])
async def test_override_discard_is_allowed_for_the_three_roles(role: str) -> None:
    agent, _, decisions = _agent()
    item = await agent.enqueue(
        tenant_id=TENANT, offer=_offer(), analysis=_analysis(price=PriceBand.ATYPICAL), rules=RULES
    )
    assert item is not None
    await agent.decide_queue_action(
        tenant_id=TENANT,
        item_id=item.id,
        action=QueueAction.OVERRIDE_DISCARD,
        roles=[role],
        comment="checked with finance",
    )
    assert decisions.created[0]["type"] == "gate_override_discard"


async def test_override_discard_needs_a_written_justification() -> None:
    agent, _, _ = _agent()
    item = await agent.enqueue(
        tenant_id=TENANT, offer=_offer(), analysis=_analysis(price=PriceBand.ATYPICAL), rules=RULES
    )
    assert item is not None
    with pytest.raises(ActionBlocked) as caught:
        await agent.decide_queue_action(
            tenant_id=TENANT, item_id=item.id, action=QueueAction.OVERRIDE_DISCARD,
            roles=["admin"], comment="   ",
        )  # fmt: skip
    assert BlockedReason.COMMENT_REQUIRED in {b.reason for b in caught.value.blocked}


async def test_acting_on_an_unknown_item_is_blocked_not_a_crash() -> None:
    agent, _, _ = _agent()
    with pytest.raises(ActionBlocked) as caught:
        await agent.decide_queue_action(
            tenant_id=TENANT, item_id="nope", action=QueueAction.UNBLOCK
        )
    assert [b.reason for b in caught.value.blocked] == [BlockedReason.NOT_IN_QUEUE]
