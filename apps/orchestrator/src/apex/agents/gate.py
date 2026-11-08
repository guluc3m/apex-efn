"""GateAgent: the human decision queue and the rules that guard it (D4-11, spec §3.8).

Two jobs, both deterministic:

1. **Build the queue.** Every offer that needs a person becomes one :class:`GateQueueItem` with the closed
   set of causes that put it there. The causes come from the engines' verdicts, never from the model.
2. **Explain what is blocked.** Every action a person can take is checked against the rules; a blocked action
   comes back with a closed reason code and a human-readable detail, so the UI can say *why* a button is
   disabled instead of hiding it (criterion 16).

Actions are signed decisions (DEV-2's ``create_decision``): the graph never mutates an offer on its own. This
module decides *whether* an action is allowed and *what* the signed payload must contain; it does not sign.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from apex.agents.offers import Offer, OfferAnalysis
from apex.agents.ports import ConfidenceBand, DecisionPort, DecisionRef, PriceBand


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GateCause(StrEnum):
    """Closed set of reasons an offer waits for a human (spec §3.8)."""

    PRICE_ATYPICAL = "price_atypical"
    PRICE_INSUFFICIENT_REFERENCE = "price_insufficient_reference"
    SELLER_LOW = "seller_low"
    SELLER_INSUFFICIENT_DATA = "seller_insufficient_data"
    OUT_OF_BUDGET = "out_of_budget"
    STRETCH_ABOVE_THRESHOLD = "stretch_above_threshold"
    NEGOTIATOR_ESCALATED = "negotiator_escalated"
    FINANCIALS_STALE = "financials_stale"
    FX_PROVISIONAL = "fx_provisional"
    DUAL_CONTROL_PENDING = "dual_control_pending"


class DealAction(StrEnum):
    FOLLOW = "follow"
    RENEGOTIATE = "renegotiate"
    TAKEOVER = "takeover"
    HOLD = "hold"
    DISCARD = "discard"


class QueueAction(StrEnum):
    UNBLOCK = "unblock"
    OVERRIDE_DISCARD = "override_discard"


class DiscardReason(StrEnum):
    """Closed codes for a discard. A free-text comment is required alongside (spec §3.8)."""

    PRICE_TOO_HIGH = "price_too_high"
    SELLER_NOT_TRUSTED = "seller_not_trusted"
    SPEC_MISMATCH = "spec_mismatch"
    LEAD_TIME = "lead_time"
    OUT_OF_BUDGET = "out_of_budget"
    DUPLICATE = "duplicate"
    OTHER = "other"


class BlockedReason(StrEnum):
    """Why an action is not available. Closed so the UI can translate it (criterion 16)."""

    PRICE_BAND_REQUIRES_UNBLOCK = "price_band_requires_unblock"
    SELLER_BAND_REQUIRES_UNBLOCK = "seller_band_requires_unblock"
    OUT_OF_BUDGET = "out_of_budget"
    FINANCIALS_STALE = "financials_stale"
    FX_PROVISIONAL = "fx_provisional"
    RENEGOTIATION_LIMIT = "renegotiation_limit"
    ALREADY_DECIDED = "already_decided"
    NOT_IN_QUEUE = "not_in_queue"
    ROLE_NOT_ALLOWED = "role_not_allowed"
    COMMENT_REQUIRED = "comment_required"


class GateItemStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class GateResolution(StrEnum):
    UNBLOCKED = "unblocked"
    DISCARDED = "discarded"
    OVERRIDDEN = "overridden"
    HELD = "held"
    FOLLOWED = "followed"


class BlockedAction(_Model):
    action: str
    reason: BlockedReason
    detail: str


class GateQueueItem(_Model):
    id: str
    tenant_id: str
    mission_id: str
    offer_id: str
    causes: list[GateCause] = Field(min_length=1)
    created_at: datetime
    sla_due_at: datetime
    status: GateItemStatus = GateItemStatus.OPEN
    resolution: GateResolution | None = None
    decision_id: str | None = None
    discard_reason: DiscardReason | None = None
    comment: str | None = None


class Deal(_Model):
    """One row of the dashboard: the offer, its analysis and what a person may do with it."""

    offer: Offer
    analysis: OfferAnalysis
    gate_item_id: str | None
    blocked_actions: list[BlockedAction] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class GateRules(_Model):
    """Thresholds the rules need. Read from tenant config; no defaults here."""

    sla_hours: int = Field(ge=1)
    max_renegotiations: int = Field(ge=0)
    stretch_gate_threshold_eur_minor: int = Field(ge=0)
    """``approval.threshold`` in minor units: a ``stretch`` verdict above it goes to the gate (ADR-900 Q8)."""


class GateStore(Protocol):
    async def add(self, item: GateQueueItem) -> GateQueueItem: ...

    async def get(self, tenant_id: str, item_id: str) -> GateQueueItem | None: ...

    async def save(self, item: GateQueueItem) -> GateQueueItem: ...

    async def list_open(self, tenant_id: str) -> list[GateQueueItem]: ...

    async def find_for_offer(self, tenant_id: str, offer_id: str) -> GateQueueItem | None: ...


class InMemoryGateStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], GateQueueItem] = {}

    async def add(self, item: GateQueueItem) -> GateQueueItem:
        self._items[(item.tenant_id, item.id)] = item
        return item

    async def get(self, tenant_id: str, item_id: str) -> GateQueueItem | None:
        return self._items.get((tenant_id, item_id))

    async def save(self, item: GateQueueItem) -> GateQueueItem:
        self._items[(item.tenant_id, item.id)] = item
        return item

    async def list_open(self, tenant_id: str) -> list[GateQueueItem]:
        open_items = [
            i
            for (t, _), i in self._items.items()
            if t == tenant_id and i.status is GateItemStatus.OPEN
        ]
        return sorted(open_items, key=lambda i: (i.sla_due_at, i.id))

    async def find_for_offer(self, tenant_id: str, offer_id: str) -> GateQueueItem | None:
        for (t, _), item in self._items.items():
            if t == tenant_id and item.offer_id == offer_id and item.status is GateItemStatus.OPEN:
                return item
        return None


@dataclass(frozen=True)
class GateDeps:
    store: GateStore
    decisions: DecisionPort
    clock: Any
    ids: Any


class GateAgent:
    def __init__(self, deps: GateDeps) -> None:
        self._deps = deps

    # ------------------------------------------------------------------ queue

    def causes_for(
        self, offer: Offer, analysis: OfferAnalysis, rules: GateRules
    ) -> list[GateCause]:
        """Which causes put this offer in front of a human. Deterministic, from the verdicts only."""
        causes: list[GateCause] = []
        price = analysis.sanity.band
        confidence = analysis.confidence.band
        fit = analysis.fit
        if price is PriceBand.ATYPICAL:
            causes.append(GateCause.PRICE_ATYPICAL)
        if price is PriceBand.INSUFFICIENT_REFERENCE:
            causes.append(GateCause.PRICE_INSUFFICIENT_REFERENCE)
        if confidence is ConfidenceBand.LOW:
            causes.append(GateCause.SELLER_LOW)
        if confidence is ConfidenceBand.INSUFFICIENT_DATA:
            causes.append(GateCause.SELLER_INSUFFICIENT_DATA)
        if fit.verdict == "out_of_budget":
            causes.append(GateCause.OUT_OF_BUDGET)
        if (
            fit.verdict == "stretch"
            and offer.unit_price_eur_minor * offer.quantity
            >= rules.stretch_gate_threshold_eur_minor
        ):
            causes.append(GateCause.STRETCH_ABOVE_THRESHOLD)
        if fit.financials_stale:
            causes.append(GateCause.FINANCIALS_STALE)
        if fit.fx_provisional:
            causes.append(GateCause.FX_PROVISIONAL)
        return causes

    async def enqueue(
        self, *, tenant_id: str, offer: Offer, analysis: OfferAnalysis, rules: GateRules
    ) -> GateQueueItem | None:
        """Create the queue item for an offer, or return the existing open one. ``None`` when it needs no human."""
        existing = await self._deps.store.find_for_offer(tenant_id, offer.id)
        if existing is not None:
            return existing
        causes = self.causes_for(offer, analysis, rules)
        if not causes:
            return None
        now = self._deps.clock.now()
        item = GateQueueItem(
            id=self._deps.ids.new_id(),
            tenant_id=tenant_id,
            mission_id=offer.mission_id,
            offer_id=offer.id,
            causes=causes,
            created_at=now,
            sla_due_at=now + timedelta(hours=rules.sla_hours),
        )
        return await self._deps.store.add(item)

    # ------------------------------------------------------------------ blocking rules

    def blocked_deal_actions(
        self,
        *,
        offer: Offer,
        analysis: OfferAnalysis,
        rules: GateRules,
        renegotiations_used: int,
        gate_item: GateQueueItem | None,
        roles: Sequence[str] = (),
    ) -> list[BlockedAction]:
        """Every action that is not available, with the reason. Empty means everything is allowed."""
        blocked: list[BlockedAction] = []
        if gate_item is not None and gate_item.status is GateItemStatus.RESOLVED:
            blocked.append(
                BlockedAction(
                    action="all",
                    reason=BlockedReason.ALREADY_DECIDED,
                    detail="this offer already has a signed decision",
                )
            )
            return blocked
        unblocked = gate_item is not None and gate_item.resolution is GateResolution.UNBLOCKED
        if not unblocked:
            # Report every band that blocks, not just the first: the UI explains all of them (criterion 16).
            blocked.extend(_band_blocks(analysis))
        if analysis.fit.verdict == "out_of_budget":
            blocked.append(
                BlockedAction(
                    action=DealAction.FOLLOW.value,
                    reason=BlockedReason.OUT_OF_BUDGET,
                    detail="the financial fit is out_of_budget; a signed unblock is required",
                )
            )
        if analysis.fit.financials_stale:
            blocked.append(
                BlockedAction(
                    action=DealAction.FOLLOW.value,
                    reason=BlockedReason.FINANCIALS_STALE,
                    detail="the financial snapshot is stale; re-import it before buying",
                )
            )
        if analysis.fit.fx_provisional:
            blocked.append(
                BlockedAction(
                    action=DealAction.FOLLOW.value,
                    reason=BlockedReason.FX_PROVISIONAL,
                    detail="the FX rate is provisional; an extra confirmation is required",
                )
            )
        if renegotiations_used >= rules.max_renegotiations:
            blocked.append(
                BlockedAction(
                    action=DealAction.RENEGOTIATE.value,
                    reason=BlockedReason.RENEGOTIATION_LIMIT,
                    detail=f"gate.max_renegotiations is {rules.max_renegotiations}",
                )
            )
        return blocked

    def blocked_queue_actions(
        self,
        *,
        item: GateQueueItem | None,
        action: QueueAction,
        roles: Sequence[str] = (),
        comment: str | None = None,
    ) -> list[BlockedAction]:
        if item is None:
            return [
                BlockedAction(
                    action=action.value,
                    reason=BlockedReason.NOT_IN_QUEUE,
                    detail="this offer is not waiting in the gate queue",
                )
            ]
        if item.status is GateItemStatus.RESOLVED:
            return [
                BlockedAction(
                    action=action.value,
                    reason=BlockedReason.ALREADY_DECIDED,
                    detail="this item already has a signed decision",
                )
            ]
        blocked: list[BlockedAction] = []
        if action is QueueAction.OVERRIDE_DISCARD and not set(roles) & {
            "finance",
            "admin",
            "owner",
        }:
            blocked.append(
                BlockedAction(
                    action=action.value,
                    reason=BlockedReason.ROLE_NOT_ALLOWED,
                    detail="override_discard is limited to finance, admin and owner",
                )
            )
        if action is QueueAction.OVERRIDE_DISCARD and not (comment or "").strip():
            blocked.append(
                BlockedAction(
                    action=action.value,
                    reason=BlockedReason.COMMENT_REQUIRED,
                    detail="an override needs a written justification",
                )
            )
        return blocked

    # ------------------------------------------------------------------ signed actions

    async def decide_deal_action(
        self,
        *,
        tenant_id: str,
        offer: Offer,
        analysis: OfferAnalysis,
        action: DealAction,
        rules: GateRules,
        renegotiations_used: int,
        gate_item: GateQueueItem | None,
        discard_reason: DiscardReason | None = None,
        comment: str | None = None,
        roles: Sequence[str] = (),
    ) -> DecisionRef:
        """Create the signed decision for a dashboard action. Raises ``ActionBlocked`` when it is not allowed."""
        blocked = self.blocked_deal_actions(
            offer=offer,
            analysis=analysis,
            rules=rules,
            renegotiations_used=renegotiations_used,
            gate_item=gate_item,
            roles=roles,
        )
        relevant = [b for b in blocked if b.action in {"all", action.value}]
        if action is DealAction.DISCARD and discard_reason is None:
            relevant.append(
                BlockedAction(
                    action=action.value,
                    reason=BlockedReason.COMMENT_REQUIRED,
                    detail="a discard needs a closed reason code",
                )
            )
        if relevant:
            raise ActionBlocked(relevant)
        payload = {
            "action": action.value,
            "offer_id": offer.id,
            "mission_id": offer.mission_id,
            "unit_price_eur_minor": offer.unit_price_eur_minor,
            "quantity": offer.quantity,
            "price_band": analysis.sanity.band.value,
            "seller_confidence": {
                "band": analysis.confidence.band.value,
                "score": analysis.confidence.score,
                "model_version": analysis.confidence.model_version,
            },
            "financial_verdict": analysis.fit.verdict,
            "financials_stale": analysis.fit.financials_stale,
            "fx_provisional": analysis.fit.fx_provisional,
            "config_version": analysis.sanity.config_version,
        }
        if discard_reason is not None:
            payload["discard_reason"] = discard_reason.value
        if comment is not None:
            payload["comment"] = comment
        return await self._deps.decisions.create_decision(
            "deal_action", f"offer:{offer.mission_id}:{offer.id}", payload, tenant_id=tenant_id
        )

    async def list_open(self, *, tenant_id: str) -> list[GateQueueItem]:
        """Open items, most urgent first (soonest SLA)."""
        return await self._deps.store.list_open(tenant_id)

    async def decide_queue_action(
        self,
        *,
        tenant_id: str,
        item_id: str,
        action: QueueAction,
        roles: Sequence[str] = (),
        comment: str | None = None,
    ) -> DecisionRef:
        item = await self._deps.store.get(tenant_id, item_id)
        blocked = self.blocked_queue_actions(item=item, action=action, roles=roles, comment=comment)
        if blocked or item is None:
            raise ActionBlocked(blocked)
        payload = {
            "action": action.value,
            "gate_item_id": item.id,
            "offer_id": item.offer_id,
            "mission_id": item.mission_id,
            "causes": [c.value for c in item.causes],
        }
        if comment is not None:
            payload["comment"] = comment
        decision_type = "gate_unblock" if action is QueueAction.UNBLOCK else "gate_override_discard"
        return await self._deps.decisions.create_decision(
            decision_type, f"gate:{item.id}", payload, tenant_id=tenant_id
        )


class ActionBlocked(Exception):
    """The action is not allowed. ``blocked`` carries every reason, so the UI can explain all of them."""

    def __init__(self, blocked: Sequence[BlockedAction]) -> None:
        super().__init__("; ".join(f"{b.action}: {b.reason.value}" for b in blocked))
        self.blocked = list(blocked)


def _band_blocks(analysis: OfferAnalysis) -> list[BlockedAction]:
    """Every band that requires a signed unblock before purchase (criterion 11)."""
    blocks: list[BlockedAction] = []
    if analysis.sanity.band in {PriceBand.ATYPICAL, PriceBand.IMPLAUSIBLE}:
        blocks.append(
            BlockedAction(
                action=DealAction.FOLLOW.value,
                reason=BlockedReason.PRICE_BAND_REQUIRES_UNBLOCK,
                detail=f"price band is {analysis.sanity.band.value}; a signed unblock is required",
            )
        )
    if analysis.confidence.band in {
        ConfidenceBand.LOW,
        ConfidenceBand.UNTRUSTED,
        ConfidenceBand.INSUFFICIENT_DATA,
    }:
        blocks.append(
            BlockedAction(
                action=DealAction.FOLLOW.value,
                reason=BlockedReason.SELLER_BAND_REQUIRES_UNBLOCK,
                detail=(
                    f"seller confidence band is {analysis.confidence.band.value}; "
                    "a signed unblock is required"
                ),
            )
        )
    return blocks


def deal_view(
    *,
    offer: Offer,
    analysis: OfferAnalysis,
    gate_item: GateQueueItem | None,
    blocked: list[BlockedAction],
) -> Deal:
    blocked_names = {b.action for b in blocked}
    allowed = [
        a.value for a in DealAction if a.value not in blocked_names and "all" not in blocked_names
    ]
    return Deal(
        offer=offer,
        analysis=analysis,
        gate_item_id=gate_item.id if gate_item else None,
        blocked_actions=blocked,
        allowed_actions=allowed,
    )


__all__ = [
    "ActionBlocked",
    "BlockedAction",
    "BlockedReason",
    "Deal",
    "DealAction",
    "DiscardReason",
    "GateAgent",
    "GateCause",
    "GateDeps",
    "GateItemStatus",
    "GateQueueItem",
    "GateResolution",
    "GateRules",
    "GateStore",
    "InMemoryGateStore",
    "QueueAction",
    "deal_view",
]
