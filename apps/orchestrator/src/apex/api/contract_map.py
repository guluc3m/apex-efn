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
from apex.agents.offers import Offer, OfferAnalysis
from apex.agents.sourcing import QuantityTier, SourcingRequest
from apex.contracts.generated.models import (
    ConvertedMoney,
    Currency,
    Mission,
    MissionEvent,
    MissionState,
    NullableMoney,
    OfferState,
    PriceSanityCheck,
    Problem,
    QuantityPriority,
    SellerConfidence,
    SellerConfidenceBand,
    SourcingRequestStatus,
    SourcingSpec,
)
from apex.contracts.generated.models import (
    MissionEventType as ContractEventType,
)
from apex.contracts.generated.models import (
    Offer as ContractOffer,
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
    MissionEventType.NEGOTIATIONS_STARTED: ContractEventType.negotiation_state_changed,
    MissionEventType.MISSION_FAILED: ContractEventType.error,
    MissionEventType.MISSION_CANCELLED: ContractEventType.state_changed,
    MissionEventType.MISSION_PAUSED: ContractEventType.state_changed,
    MissionEventType.MISSION_RESUMED: ContractEventType.state_changed,
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
        paused=mission.paused,
        state=mission_state(mission.status),
        offers_discovered=discovered,
        offers_negotiated=_last_count(mission, "offers_negotiated"),
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


def to_contract_offer(offer: Offer, analysis: OfferAnalysis | None) -> ContractOffer:
    """An offer as the contract shows it.

    The analysis keeps the engines' own objects (``detail`` / ``landed_cost``), so the confidence
    breakdown, the sanity reference numbers and the landed-cost lines reach the UI. When an older
    analysis exists without them, only the verdicts are sent — never invented numbers.
    """
    confidence = None
    sanity = None
    fit = None
    if analysis is not None:
        confidence = (
            analysis.confidence.detail
            if analysis.confidence.detail is not None
            else SellerConfidence(
                seller_id=offer.seller_id,
                score=analysis.confidence.score,
                band=SellerConfidenceBand(analysis.confidence.band.value),
                signals_normalized={},
                penalties=[],
                flags=[],
                model_version=analysis.confidence.model_version,
                computed_at=analysis.analysed_at,
            )
        )
        sanity = analysis.sanity.detail if isinstance(analysis.sanity.detail, PriceSanityCheck) else None
        fit = analysis.fit.detail
    return ContractOffer(
        id=offer.id,
        mission_id=offer.mission_id,
        platform=offer.platform_id,
        platform_offer_id=offer.id.split(":", 1)[-1],
        product_key=offer.product_id,
        title=offer.title or offer.product_id,
        seller_id=offer.seller_id,
        seller_name=offer.seller_id,
        unit_price=ConvertedMoney(
            amount_minor=offer.unit_price_eur_minor,
            currency=Currency.EUR,
            converted=False,
            fx_provisional=analysis.fit.fx_provisional if analysis is not None else False,
        ),
        moq=offer.moq,
        state=OfferState.financially_checked if analysis is not None else OfferState.discovered,
        discovered_at=offer.collected_at,
        negotiation_id=analysis.negotiation_id if analysis is not None else None,
        seller_confidence=confidence,
        price_sanity_check=sanity,
        financial_fit=fit,
    )
