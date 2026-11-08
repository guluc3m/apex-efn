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
from apex.agents.ports import ConfidenceBand, PriceBand
from tests.agents.fakes import TENANT, AlwaysNegotiateCombiner, Rig, make_rig

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


def test_negotiate_has_a_single_incoming_edge_from_check_financial() -> None:
    graph = build_offer_graph(make_rig().deps).get_graph()
    incoming = {e.source for e in graph.edges if e.target == "negotiate"}
    assert incoming == {"check_financial"}


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


async def test_negotiation_without_a_price_rejects_the_offer() -> None:
    rig = make_rig(negotiated_price=None)
    graph, config = _start(rig)
    final = await _run(graph, config)
    assert final["status"] == "rejected" and final["reject_reason"] == "negotiation_no_price"


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
