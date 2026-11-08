"""Per-offer graph: ordering, the trust+sanity->negotiation invariant (criterion 12), human gates, resume."""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from apex.agents.offer_graph import (
    NegotiationNotCleared,
    OfferGraphDeps,
    build_offer_graph,
    initial_state,
    thread_id,
)
from apex.agents.offer_state import (
    ALLOWED,
    TERMINAL,
    InvalidTransition,
    OfferStatus,
    check_transition,
)
from apex.agents.ports import ConfidenceBand, NegotiationOutcomeKind, PriceBand
from tests.agents.fakes import (
    TENANT,
    AlwaysNegotiateCombiner,
    Rig,
    agreed,
    make_rig,
    stopped,
)

MISSION, OFFER = "m1", "o1"


def _config(thread: str = thread_id(MISSION, OFFER)) -> Any:
    return {"configurable": {"thread_id": thread}}


def _start(rig: Rig) -> tuple[Any, Any]:
    graph = build_offer_graph(rig.deps, checkpointer=InMemorySaver())
    return graph, _config()


async def _run(graph: Any, config: Any) -> dict[str, Any]:
    state = initial_state(
        mission_id=MISSION, offer_id=OFFER, tenant_id=TENANT, offer={"price_minor": 1000}
    )
    result: dict[str, Any] = await graph.ainvoke(state, config)
    return result


async def _resume(graph: Any, config: Any) -> dict[str, Any]:
    result: dict[str, Any] = await graph.ainvoke(Command(resume=True), config)
    return result


def _resolved(value: Any) -> Any:
    """Wrap a value as an already-completed awaitable, for port stubs."""

    async def _inner() -> Any:
        return value

    return _inner()


def _interrupted(result: dict[str, Any]) -> dict[str, Any]:
    pending = result.get("__interrupt__")
    assert pending, "expected the graph to pause for a human"
    value: dict[str, Any] = pending[0].value
    return value


HAPPY = [
    "discovered", "enriched", "trust_scored", "sanity_checked", "financially_checked",
    "negotiating", "negotiated", "sanity_rechecked", "scored", "awaiting_human",
    "signed", "approved", "purchased",
]  # fmt: skip


async def test_happy_path_follows_the_spec_order_and_needs_a_signed_approval() -> None:
    rig = make_rig()
    graph, config = _start(rig)
    paused = await _run(graph, config)
    assert _interrupted(paused)["decision_type"] == "deal_action"
    assert rig.calls["negotiation"] == 1

    rig.decisions.sign(rig.decisions.pending_id(), action="approve")
    final = await _resume(graph, config)
    assert final["status"] == "purchased"
    assert final["history"] == HAPPY
    assert final["human_action"] == "approve"


async def test_unsigned_decision_cannot_reach_purchase_even_if_resumed_repeatedly() -> None:
    rig = make_rig()
    graph, config = _start(rig)
    await _run(graph, config)
    for _ in range(3):
        again = await _resume(graph, config)
        assert _interrupted(again)["kind"] == "awaiting_signature"
    state = (await graph.aget_state(config)).values
    assert state["status"] == "awaiting_human"
    assert "purchased" not in state["history"] and "approved" not in state["history"]


async def test_human_reject_ends_in_rejected_and_never_purchases() -> None:
    rig = make_rig()
    graph, config = _start(rig)
    await _run(graph, config)
    rig.decisions.sign(rig.decisions.pending_id(), action="reject")
    final = await _resume(graph, config)
    assert final["status"] == "rejected"
    assert final["reject_reason"] == "human_rejected"
    assert final["history"][-3:] == ["awaiting_human", "signed", "rejected"]


async def test_rejected_or_expired_decision_rejects_the_offer() -> None:
    rig = make_rig()
    graph, config = _start(rig)
    await _run(graph, config)
    rig.decisions.reject(rig.decisions.pending_id())
    final = await _resume(graph, config)
    assert final["status"] == "rejected"
    assert final["reject_reason"] == "decision_rejected_or_expired"


async def test_signed_decision_for_another_offer_is_refused() -> None:
    from apex.agents.offer_graph import InvalidSignedDecision

    rig = make_rig()
    graph, config = _start(rig)
    await _run(graph, config)
    pending = rig.decisions.pending_id()
    rig.decisions.sign(pending, action="approve")
    rig.decisions.signed[pending]["subject_ref"] = "offer:m1:someone-else"
    with pytest.raises(InvalidSignedDecision):
        await _resume(graph, config)


# ----- criterion 12: the negotiator is never called without a signed unblock ------------------------


@pytest.mark.parametrize(
    "price",
    [PriceBand.ATYPICAL, PriceBand.IMPLAUSIBLE, PriceBand.INSUFFICIENT_REFERENCE],
)
@pytest.mark.parametrize("trust", list(ConfidenceBand))
async def test_negotiator_call_counter_is_zero_for_anomalous_prices_without_unblock(
    price: PriceBand, trust: ConfidenceBand
) -> None:
    rig = make_rig(trust=trust, price=price)
    graph, config = _start(rig)
    result = await _run(graph, config)
    assert rig.calls["negotiation"] == 0
    state = (await graph.aget_state(config)).values
    assert state["status"] in {"gate_pending", "rejected"}
    if state["status"] == "gate_pending":
        assert _interrupted(result)["decision_type"] == "gate_unblock"


@pytest.mark.parametrize(
    "price",
    [PriceBand.ATYPICAL, PriceBand.IMPLAUSIBLE, PriceBand.INSUFFICIENT_REFERENCE],
)
async def test_graph_overrides_a_buggy_combiner_that_says_negotiate(price: PriceBand) -> None:
    rig = make_rig(trust=ConfidenceBand.HIGH, price=price, combiner=AlwaysNegotiateCombiner())
    graph, config = _start(rig)
    result = await _run(graph, config)
    assert rig.calls["negotiation"] == 0
    assert _interrupted(result)["decision_type"] == "gate_unblock"
    assert (
        "graph_override:price_band_requires_signed_unblock"
        in ((await graph.aget_state(config)).values["gate"]["reasons"])
    )


async def test_negotiation_runs_after_a_signed_unblock_and_not_before() -> None:
    rig = make_rig(
        trust=ConfidenceBand.HIGH,
        price=PriceBand.INSUFFICIENT_REFERENCE,
        rechecked=PriceBand.NORMAL,
    )
    graph, config = _start(rig)
    await _run(graph, config)
    assert rig.calls["negotiation"] == 0
    await _resume(graph, config)  # still unsigned
    assert rig.calls["negotiation"] == 0

    rig.decisions.sign(rig.decisions.pending_id(), action="unblock")
    paused = await _resume(graph, config)
    assert rig.calls["negotiation"] == 1
    assert _interrupted(paused)["decision_type"] == "deal_action"


async def test_unblock_payload_carries_price_confidence_fit_and_config_version() -> None:
    rig = make_rig(trust=ConfidenceBand.LOW, price=PriceBand.NORMAL)
    graph, config = _start(rig)
    await _run(graph, config)
    payload = next(iter(rig.decisions.created.values()))["payload"]
    assert payload["seller_confidence"]["model_version"] == "trust-test"
    assert payload["price_sanity"]["band"] == "normal"
    assert payload["financial_fit"]["verdict"] == "within_budget"
    assert payload["config_version"] == "cfg-1"


async def test_discard_cases_end_rejected_without_any_decision_or_negotiation() -> None:
    rig = make_rig(trust=ConfidenceBand.UNTRUSTED, price=PriceBand.NORMAL)
    graph, config = _start(rig)
    final = await _run(graph, config)
    assert final["status"] == "rejected" and final["reject_reason"] == "gate_discard"
    assert rig.calls["negotiation"] == 0 and rig.calls["create_decision"] == 0


async def test_cheap_atypical_with_low_confidence_is_escalated_to_discard() -> None:
    rig = make_rig(trust=ConfidenceBand.LOW, price=PriceBand.ATYPICAL)
    graph, config = _start(rig)
    final = await _run(graph, config)
    assert final["status"] == "rejected"
    assert rig.calls["negotiation"] == 0


async def test_negotiate_node_refuses_to_run_without_clearance() -> None:
    """Defence in depth: even a state forged past the router cannot reach the negotiator."""
    rig = make_rig()
    graph = build_offer_graph(rig.deps)
    forged = initial_state(mission_id=MISSION, offer_id=OFFER, tenant_id=TENANT, offer={})
    forged["status"] = OfferStatus.FINANCIALLY_CHECKED.value
    forged["negotiation_cleared"] = False
    with pytest.raises(NegotiationNotCleared):
        await graph.nodes["negotiate"].ainvoke(forged)
    assert rig.calls["negotiation"] == 0


def test_negotiation_is_reachable_only_through_check_financial() -> None:
    """``check_financial`` -> ``enter_negotiating`` -> ``negotiate``, with no other way in."""
    graph = build_offer_graph(make_rig().deps).get_graph()
    # ``wait_negotiation`` only loops back from ``negotiate`` itself (a waiting negotiation polls again).
    assert {e.source for e in graph.edges if e.target == "negotiate"} == {
        "enter_negotiating",
        "wait_negotiation",
    }
    assert {e.source for e in graph.edges if e.target == "wait_negotiation"} == {"negotiate"}
    assert {e.source for e in graph.edges if e.target == "enter_negotiating"} == {"check_financial"}


# ----- post-negotiation re-check --------------------------------------------------------------------


async def test_price_that_turns_atypical_after_negotiation_goes_to_the_gate() -> None:
    rig = make_rig(price=PriceBand.NORMAL, rechecked=PriceBand.ATYPICAL)
    graph, config = _start(rig)
    result = await _run(graph, config)
    assert rig.calls["negotiation"] == 1
    assert _interrupted(result)["decision_type"] == "gate_unblock"
    state = (await graph.aget_state(config)).values
    assert state["status"] == "gate_pending" and state["gate_stage"] == "post"

    rig.decisions.sign(rig.decisions.pending_id(), action="unblock")
    paused = await _resume(graph, config)
    assert rig.calls["negotiation"] == 1  # not negotiated again
    assert _interrupted(paused)["decision_type"] == "deal_action"


@pytest.mark.parametrize(
    "kind", [NegotiationOutcomeKind.ESCALATED, NegotiationOutcomeKind.STOPPED_ANOMALOUS_PRICE]
)
async def test_escalated_and_anomalous_negotiations_go_to_the_gate_not_to_reject(
    kind: NegotiationOutcomeKind,
) -> None:
    rig = make_rig(negotiation=(stopped(kind),))
    graph, config = _start(rig)
    result = await _run(graph, config)
    state = (await graph.aget_state(config)).values
    assert state["status"] == "gate_pending" and state["gate_stage"] == "post"
    assert state["gate"]["reasons"] == [f"negotiation:{kind.value}"]
    assert _interrupted(result)["decision_type"] == "gate_unblock"
    assert rig.calls["resanity"] == 0  # there is no agreed price to re-check


@pytest.mark.parametrize(
    "kind", [NegotiationOutcomeKind.NO_AGREEMENT, NegotiationOutcomeKind.ABORTED]
)
async def test_no_agreement_and_aborted_reject_the_offer(kind: NegotiationOutcomeKind) -> None:
    rig = make_rig(negotiation=(stopped(kind),))
    graph, config = _start(rig)
    final = await _run(graph, config)
    assert final["status"] == "rejected"
    assert final["reject_reason"] == f"negotiation_{kind.value}"
    assert rig.calls["create_decision"] == 0


async def test_unblock_cannot_push_a_priceless_negotiation_to_the_final_decision() -> None:
    from apex.agents.offer_graph import InvalidSignedDecision

    rig = make_rig(negotiation=(stopped(NegotiationOutcomeKind.ESCALATED),))
    graph, config = _start(rig)
    await _run(graph, config)
    rig.decisions.sign(rig.decisions.pending_id(), action="unblock")
    with pytest.raises(InvalidSignedDecision, match="no agreed price"):
        await _resume(graph, config)


@pytest.mark.parametrize(
    "kind",
    [NegotiationOutcomeKind.AWAITING_HUMAN_APPROVAL, NegotiationOutcomeKind.AWAITING_SELLER],
)
async def test_waiting_negotiation_pauses_and_resumes_with_the_same_key(
    kind: NegotiationOutcomeKind,
) -> None:
    rig = make_rig(negotiation=(stopped(kind), stopped(kind), agreed()))
    graph, config = _start(rig)
    paused = await _run(graph, config)
    assert _interrupted(paused)["kind"] == "awaiting_negotiation"
    assert _interrupted(paused)["outcome"] == kind.value
    assert (await graph.aget_state(config)).values["status"] == "negotiating"

    again = await _resume(graph, config)
    assert _interrupted(again)["kind"] == "awaiting_negotiation"
    final = await _resume(graph, config)
    assert _interrupted(final)["decision_type"] == "deal_action"  # reached the human decision
    assert rig.calls["negotiation"] == 3
    assert set(rig.negotiation.keys) == {"negotiate:offer:m1:o1:1"}


async def test_a_negotiator_with_its_own_enum_class_is_accepted() -> None:
    """DEV-5 returns its own ``NegotiationOutcome`` (same values, different type). The boundary is explicit."""
    from enum import StrEnum

    from apex.agents.ports import NegotiationResult

    class TheirOutcome(StrEnum):
        AGREED = "agreed"
        AWAITING_SELLER = "awaiting_seller"

    class TheirResult(NegotiationResult):
        outcome: TheirOutcome  # type: ignore[assignment]

    rig = make_rig()
    rig.deps.negotiation.negotiate = lambda *a, **k: _resolved(  # type: ignore[method-assign]
        TheirResult(
            outcome=TheirOutcome.AGREED,
            negotiation_id="n1",
            price_minor=900,
            currency="EUR",
            quantity=10,
        )
    )
    graph, config = _start(rig)
    result = await _run(graph, config)
    assert _interrupted(result)["decision_type"] == "deal_action"
    assert (await graph.aget_state(config)).values["negotiation"]["outcome"] == "agreed"


async def test_an_outcome_outside_the_closed_set_fails_loudly() -> None:
    from apex.agents.offer_graph import UnknownNegotiationOutcome
    from apex.agents.ports import NegotiationResult

    rig = make_rig()
    rig.deps.negotiation.negotiate = lambda *a, **k: _resolved(  # type: ignore[method-assign]
        NegotiationResult.model_construct(
            outcome="something_new",
            negotiation_id="n1",
            price_minor=None,
            currency=None,
            quantity=None,
        )
    )
    graph, config = _start(rig)
    with pytest.raises(UnknownNegotiationOutcome):
        await _run(graph, config)


async def test_terminal_negotiation_is_cached_and_never_repeated_on_resume() -> None:
    rig = make_rig(negotiation=(agreed(),))
    graph, config = _start(rig)
    await _run(graph, config)
    for _ in range(3):
        await _resume(graph, config)
    assert rig.calls["negotiation"] == 1


async def test_negotiating_is_recorded_in_the_history() -> None:
    rig = make_rig()
    graph, config = _start(rig)
    await _run(graph, config)
    history = (await graph.aget_state(config)).values["history"]
    assert "negotiating" in history
    assert history.index("negotiating") < history.index("negotiated")


async def test_negotiated_price_is_converted_to_eur_per_unit_before_the_sanity_recheck() -> None:
    rig = make_rig(negotiation=(agreed(price_minor=500, currency="USD"),))
    rig.prices.rates["USD"] = 3
    seen: list[int | None] = []
    original = rig.deps.sanity.check

    async def spy(offer: Any, *, tenant_id: str, price_minor: int | None) -> Any:
        seen.append(price_minor)
        return await original(offer, tenant_id=tenant_id, price_minor=price_minor)

    rig.deps.sanity.check = spy  # type: ignore[method-assign]
    graph, config = _start(rig)
    await _run(graph, config)
    assert seen == [None, 1500]  # listed price first, then the converted negotiated price
    assert (await graph.aget_state(config)).values["negotiation_price"][
        "unit_price_eur_minor"
    ] == 1500


async def test_second_gate_after_negotiation_needs_a_new_signed_unblock() -> None:
    """Pre-stage unblock must not authorize the post-negotiation gate (ADR-900, ADR-403 item 2)."""
    rig = make_rig(
        price=PriceBand.INSUFFICIENT_REFERENCE,
        rechecked=PriceBand.ATYPICAL,
        trust=ConfidenceBand.HIGH,
    )
    graph, config = _start(rig)
    await _run(graph, config)
    first = rig.decisions.pending_id()
    rig.decisions.sign(first, action="unblock")
    paused = await _resume(graph, config)
    assert _interrupted(paused)["decision_type"] == "gate_unblock"
    assert rig.calls["create_decision"] == 2
    second = rig.decisions.pending_id()
    assert second != first
    state = (await graph.aget_state(config)).values
    assert state["gate_stage"] == "post" and state["status"] == "gate_pending"

    # Re-using the first decision's signed payload for the second gate is refused.
    rig.decisions.signed[second] = {
        **rig.decisions.signed[first],
        "subject_ref": rig.decisions.created[second]["subject_ref"],
    }
    from apex.agents.offer_graph import InvalidSignedDecision

    with pytest.raises(InvalidSignedDecision, match="another gate"):
        await _resume(graph, config)


async def test_renegotiate_starts_a_new_attempt_with_a_new_key_until_the_limit() -> None:
    rig = make_rig(
        rechecked=PriceBand.ATYPICAL,
        negotiation=(agreed(), agreed(), agreed()),
        max_renegotiations=1,
    )
    graph, config = _start(rig)
    await _run(graph, config)  # attempt 1 -> post gate
    rig.decisions.sign(rig.decisions.pending_id(), action="renegotiate", stage="post", attempt=1)
    again = await _resume(graph, config)  # attempt 2 -> post gate again
    assert _interrupted(again)["decision_type"] == "gate_unblock"
    assert rig.negotiation.keys == ["negotiate:offer:m1:o1:1", "negotiate:offer:m1:o1:2"]

    rig.decisions.sign(rig.decisions.pending_id(), action="renegotiate", stage="post", attempt=2)
    final = await _resume(graph, config)  # limit of 1 renegotiation reached
    assert final["status"] == "rejected" and final["reject_reason"] == "renegotiation_limit"
    assert rig.calls["negotiation"] == 2


async def test_out_of_budget_offer_is_never_purchased_even_with_a_signed_approval() -> None:
    rig = make_rig(verdict="out_of_budget")
    graph, config = _start(rig)
    await _run(graph, config)
    rig.decisions.sign(rig.decisions.pending_id(), action="approve")
    final = await _resume(graph, config)
    assert final["status"] == "approved"
    assert final["purchase_blocked"] == ["out_of_budget"]
    assert "purchased" not in final["history"]


# ----- idempotency and resume -----------------------------------------------------------------------


async def test_resume_never_duplicates_effects() -> None:
    rig = make_rig()
    graph, config = _start(rig)
    await _run(graph, config)
    for _ in range(4):
        await _resume(graph, config)
    rig.decisions.sign(rig.decisions.pending_id(), action="approve")
    final = await _resume(graph, config)
    await _resume(graph, config)  # resuming a finished thread is a no-op

    assert final["status"] == "purchased"
    assert rig.calls["negotiation"] == 1
    assert rig.calls["create_decision"] == 1
    assert rig.calls["enrich"] == 1
    transitions = [(e["from"], e["to"]) for e in rig.audit.events]
    assert len(transitions) == len(set(transitions)) == len(HAPPY) - 1
    assert rig.calls["service_signature"] == rig.calls["audit"] == len(HAPPY) - 1


async def test_every_audit_event_is_service_signed_and_carries_config_version() -> None:
    rig = make_rig()
    graph, config = _start(rig)
    await _run(graph, config)
    assert rig.audit.events
    for event in rig.audit.events:
        assert event["service_signature"].startswith("sig-")
        assert event["config_version"] == "cfg-1"


async def test_state_survives_a_new_graph_instance_on_the_same_checkpointer() -> None:
    """A restarted worker rebuilds the graph and resumes from the checkpoint without redoing work."""
    saver = InMemorySaver()
    rig = make_rig()
    first = build_offer_graph(rig.deps, checkpointer=saver)
    await _run(first, _config())
    rig.decisions.sign(rig.decisions.pending_id(), action="approve")

    second = build_offer_graph(rig.deps, checkpointer=saver)
    final = await _resume(second, _config())
    assert final["status"] == "purchased"
    assert rig.calls["negotiation"] == 1


async def test_two_offers_in_one_mission_do_not_interfere() -> None:
    rig = make_rig()
    graph = build_offer_graph(rig.deps, checkpointer=InMemorySaver())
    for offer_id in ("a", "b"):
        state = initial_state(mission_id=MISSION, offer_id=offer_id, tenant_id=TENANT, offer={})
        await graph.ainvoke(state, _config(thread_id(MISSION, offer_id)))
    assert rig.calls["negotiation"] == 2
    assert len(rig.decisions.created) == 2


# ----- state machine table --------------------------------------------------------------------------


def test_transition_table_is_total_and_terminals_are_final() -> None:
    assert set(ALLOWED) == set(OfferStatus)
    for status in TERMINAL:
        assert ALLOWED[status] == frozenset()


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (OfferStatus.DISCOVERED, OfferStatus.NEGOTIATING),
        (OfferStatus.SANITY_CHECKED, OfferStatus.NEGOTIATING),
        (OfferStatus.GATE_PENDING, OfferStatus.NEGOTIATING),
        (OfferStatus.SCORED, OfferStatus.PURCHASED),
        (OfferStatus.AWAITING_HUMAN, OfferStatus.APPROVED),
        (OfferStatus.SIGNED, OfferStatus.PURCHASED),
        (OfferStatus.REJECTED, OfferStatus.APPROVED),
    ],
)
def test_skipping_steps_is_not_allowed(source: OfferStatus, target: OfferStatus) -> None:
    with pytest.raises(InvalidTransition):
        check_transition(source, target)


def test_nothing_but_financial_check_leads_to_negotiating() -> None:
    sources = [s for s, targets in ALLOWED.items() if OfferStatus.NEGOTIATING in targets]
    assert sources == [OfferStatus.FINANCIALLY_CHECKED]


def test_deps_is_a_frozen_dataclass() -> None:
    assert OfferGraphDeps.__dataclass_params__.frozen  # type: ignore[attr-defined]
