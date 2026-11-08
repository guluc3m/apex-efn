"""Per-offer state machine (spec section 4) and its LangGraph state.

``discovered -> enriched -> trust_scored -> sanity_checked -> (gate_pending) -> financially_checked ->
negotiating -> negotiated -> sanity_rechecked -> scored -> awaiting_human -> signed -> approved | rejected
-> purchased``. ``gate_pending`` is the "(gate)" node of the diagram. ``rejected`` is also where a discard
ends. The transition table is the single source of truth; the graph refuses any other move.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict


class OfferStatus(StrEnum):
    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    TRUST_SCORED = "trust_scored"
    SANITY_CHECKED = "sanity_checked"
    GATE_PENDING = "gate_pending"
    FINANCIALLY_CHECKED = "financially_checked"
    NEGOTIATING = "negotiating"
    NEGOTIATED = "negotiated"
    SANITY_RECHECKED = "sanity_rechecked"
    SCORED = "scored"
    AWAITING_HUMAN = "awaiting_human"
    SIGNED = "signed"
    APPROVED = "approved"
    REJECTED = "rejected"
    PURCHASED = "purchased"


S = OfferStatus

ALLOWED: dict[OfferStatus, frozenset[OfferStatus]] = {
    S.DISCOVERED: frozenset({S.ENRICHED}),
    S.ENRICHED: frozenset({S.TRUST_SCORED}),
    S.TRUST_SCORED: frozenset({S.SANITY_CHECKED}),
    S.SANITY_CHECKED: frozenset({S.GATE_PENDING, S.FINANCIALLY_CHECKED, S.REJECTED}),
    S.GATE_PENDING: frozenset({S.FINANCIALLY_CHECKED, S.SCORED, S.REJECTED}),
    S.FINANCIALLY_CHECKED: frozenset({S.NEGOTIATING}),
    S.NEGOTIATING: frozenset({S.NEGOTIATED}),
    S.NEGOTIATED: frozenset({S.SANITY_RECHECKED}),
    S.SANITY_RECHECKED: frozenset({S.GATE_PENDING, S.SCORED, S.REJECTED}),
    S.SCORED: frozenset({S.AWAITING_HUMAN}),
    S.AWAITING_HUMAN: frozenset({S.SIGNED, S.REJECTED}),
    S.SIGNED: frozenset({S.APPROVED, S.REJECTED}),
    S.APPROVED: frozenset({S.PURCHASED}),
    S.REJECTED: frozenset(),
    S.PURCHASED: frozenset(),
}

TERMINAL = frozenset({S.REJECTED, S.PURCHASED})


class InvalidTransition(Exception):
    def __init__(self, source: OfferStatus, target: OfferStatus) -> None:
        super().__init__(f"transition {source.value} -> {target.value} is not allowed")
        self.source = source
        self.target = target


def check_transition(source: OfferStatus, target: OfferStatus) -> None:
    if target not in ALLOWED[source]:
        raise InvalidTransition(source, target)


class OfferState(TypedDict, total=False):
    """LangGraph state for one offer. Everything is plain JSON so any checkpointer can store it."""

    mission_id: str
    offer_id: str
    tenant_id: str
    config_version: str
    offer: dict[str, Any]

    status: str
    history: list[str]
    reject_reason: str | None

    trust: dict[str, Any]
    sanity: dict[str, Any]
    finance: dict[str, Any]
    gate: dict[str, Any]
    negotiation: dict[str, Any]
    score: dict[str, Any]

    # Gate bookkeeping. ``negotiation_cleared`` is True only after route=negotiate or a signed unblock.
    gate_stage: str
    gate_decision_id: str | None
    negotiation_cleared: bool
    human_decision_id: str | None
    human_action: str | None


__all__ = [
    "ALLOWED",
    "TERMINAL",
    "InvalidTransition",
    "OfferState",
    "OfferStatus",
    "check_transition",
]
