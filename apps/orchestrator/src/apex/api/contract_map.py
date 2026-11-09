"""Mapping between the orchestrator's domain objects and the generated contract models.

The contract in ``/contracts/openapi.yaml`` is the source of truth for the HTTP surface (spec §5.1: no DTO
defined twice by hand). The domain objects are richer than the wire shape — they carry the tenant, the config
version and the internal status machine — so this module is the single place that translates one into the
other. Routers call it; nothing else should.
"""

from __future__ import annotations

from typing import Any

from apex.agents.missions import Mission as DomainMission
from apex.agents.missions import MissionEvent as DomainEvent
from apex.agents.missions import MissionEventType, MissionStatus
from apex.agents.sourcing import QuantityTier, SourcingRequest
from apex.contracts.generated.models import (
    Mission,
    MissionEvent,
    MissionState,
    NullableMoney,
    Problem,
    QuantityPriority,
    SourcingRequestStatus,
    SourcingSpec,
)
from apex.contracts.generated.models import (
    MissionEventType as ContractEventType,
)
from apex.contracts.generated.models import (
    QuantityTier as ContractTier,
)
from apex.contracts.generated.models import (
    SourcingRequest as ContractRequest,
)

#: Internal status -> the contract's public state machine. The contract has no "planned" or "running":
#: a planned mission is about to source, and a running one is sourcing.
_STATUS_TO_STATE: dict[MissionStatus, MissionState] = {
    MissionStatus.QUEUED: MissionState.created,
    MissionStatus.PLANNING: MissionState.planning,
    MissionStatus.PLANNED: MissionState.sourcing,
    MissionStatus.RUNNING: MissionState.sourcing,
    MissionStatus.COMPLETED: MissionState.completed,
    MissionStatus.FAILED: MissionState.failed,
    MissionStatus.CANCELLED: MissionState.cancelled,
}

#: Internal event -> the contract's closed event set. ``keepalive`` is not used: the SSE comment is enough.
_EVENT_TO_CONTRACT: dict[MissionEventType, ContractEventType] = {
    MissionEventType.MISSION_CREATED: ContractEventType.state_changed,
    MissionEventType.PLANNING_STARTED: ContractEventType.state_changed,
    MissionEventType.PLAN_READY: ContractEventType.state_changed,
    MissionEventType.SOURCING_STARTED: ContractEventType.state_changed,
    MissionEventType.OFFERS_COLLECTED: ContractEventType.offer_discovered,
    MissionEventType.ANALYSIS_COMPLETED: ContractEventType.sanity_checked,
    MissionEventType.MISSION_FAILED: ContractEventType.error,
    MissionEventType.MISSION_CANCELLED: ContractEventType.state_changed,
}


def mission_state(status: MissionStatus) -> MissionState:
    return _STATUS_TO_STATE[status]


def to_contract_request(
    request: SourcingRequest,
    *,
    status: SourcingRequestStatus | None = None,
    max_budget: NullableMoney | None = None,
) -> ContractRequest:
    """Domain request -> wire shape. ``spec`` becomes the structured object the contract defines."""
    return ContractRequest(
        id=request.id,
        status=status
        or (
            SourcingRequestStatus.needs_clarification
            if request.missing_fields
            else SourcingRequestStatus.normalized
        ),
        spec=SourcingSpec(
            description=request.spec,
            specifications=None,
            certifications=list(request.certifications) or None,
        ),
        quantity_tiers=[_tier(t) for t in request.quantity_tiers],
        max_budget=max_budget,
        target_delivery_date=request.deadline,
        delivery_country=request.destination_country or "ES",
        needs_clarification=list(request.missing_fields),
        created_at=request.created_at,
    )


def _tier(tier: QuantityTier) -> ContractTier:
    return ContractTier(quantity=tier.min_quantity, priority=QuantityPriority.primary)


def to_contract_mission(
    mission: DomainMission, *, token_budget: int, tokens_used: int = 0
) -> Mission:
    """Domain mission -> wire shape. Counts come from the event log, never from a guess."""
    discovered = _last_count(mission, "offers_collected")
    in_gate = _last_count(mission, "gate_items")
    error = None
    if mission.status is MissionStatus.FAILED and mission.failure_reason:
        error = Problem(
            type="about:blank",
            title="Mission failed",
            status=500,
            detail=mission.failure_reason,
        )
    return Mission(
        id=mission.id,
        sourcing_request_id=mission.sourcing_request_id,
        plan_id=None,
        state=mission_state(mission.status),
        offers_discovered=discovered,
        offers_negotiated=0,
        offers_in_gate=in_gate,
        tokens_used=tokens_used,
        token_budget=token_budget,
        started_at=mission.created_at,
        completed_at=mission.updated_at if mission.status is MissionStatus.COMPLETED else None,
        error=error,
    )


def _last_count(mission: DomainMission, key: str) -> int:
    for event in reversed(mission.events):
        value = event.payload.get(key)
        if isinstance(value, int):
            return value
    return 0


def to_contract_event(mission: DomainMission, event: DomainEvent) -> MissionEvent:
    """Domain event -> the contract's ``MissionEvent``. The SSE ``event`` field equals ``type``."""
    data: dict[str, Any] = {"state": mission_state(mission.status).value, **event.payload}
    return MissionEvent(
        id=str(event.seq),
        mission_id=mission.id,
        type=_EVENT_TO_CONTRACT[event.type],
        at=event.at,
        data=data,
    )


__all__ = [
    "mission_state",
    "to_contract_event",
    "to_contract_mission",
    "to_contract_request",
]
