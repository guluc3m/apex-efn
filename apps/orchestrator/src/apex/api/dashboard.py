"""Dashboard endpoints (owner: DEV-4, D4-11).

``GET /v1/dashboard/deals`` is the work queue of final deals: each row carries the offer, the three engine
verdicts, the gate item and — for every action — whether it is available and, if not, why (criterion 16).
``POST /v1/dashboard/deals/{id}/actions`` creates the signed decision for one action.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field

from apex.agents.gate import (
    ActionBlocked,
    DealAction,
    DiscardReason,
    GateItemStatus,
    GateQueueItem,
    GateResolution,
)
from apex.agents.gate import Deal as DomainDeal
from apex.api.contract_map import to_contract_offer
from apex.api.gate import DecisionAcceptedOut, _blocked
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_roles, get_tenant_id
from apex.contracts.generated.models import (
    ActionAvailability,
    BlockReason,
    BlockReasonCode,
    DashboardSummary,
    Deal,
    DealPage,
    DealState,
    FinancialVerdict,
    PriceSanityBand,
    SellerConfidenceBand,
    SignatureStatus,
)
from apex.contracts.generated.models import DealAction as ContractDealAction

router = APIRouter()


class DealActionIn(BaseModel):
    """The contract's body. Roles are never part of it: they come from the authenticated principal."""

    model_config = ConfigDict(extra="forbid")

    action: DealAction
    discard_reason: DiscardReason | None = None
    comment: str | None = Field(default=None, max_length=2000)


def get_dashboard() -> Any:
    """Overridable dependency: the dashboard reads offers, analyses and the gate queue."""
    raise not_implemented(
        "the dashboard needs offers (D4-09/D4-10) and the gate agent; wire it in the app"
    )


@router.get("/deals", response_model=DealPage, tags=["dashboard"])
async def get_deals(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    dashboard: Annotated[Any, Depends(get_dashboard)],
    mission_id: Annotated[str | None, Query(max_length=128)] = None,
    platform: Annotated[str | None, Query(max_length=64)] = None,
    price_band: Annotated[str | None, Query(max_length=32)] = None,
    confidence_band: Annotated[str | None, Query(max_length=32)] = None,
    financial_verdict: Annotated[str | None, Query(max_length=32)] = None,
    verdict: Annotated[str | None, Query(max_length=32)] = None,
    signature_status: Annotated[str | None, Query(max_length=32)] = None,
) -> DealPage:
    """Deals with the contract's filters (mission, bands, verdict, platform, signature status)."""
    deals = await dashboard.deals(
        tenant_id=tenant_id,
        platform=platform,
        price_band=price_band,
        verdict=financial_verdict or verdict,
    )
    items = [await _contract_deal(dashboard, tenant_id, d) for d in deals]
    items = [
        d
        for d in items
        if (mission_id is None or d.mission_id == mission_id)
        and (confidence_band is None or d.confidence_band.value == confidence_band)
        and (signature_status is None or d.signature_status.value == signature_status)
    ]
    return DealPage(
        items=items, next_cursor=None
    )  # ponytail: one page; cursor when stores move to DB


async def _contract_deal(dashboard: Any, tenant_id: str, d: DomainDeal) -> Deal:
    """The contract's ``Deal`` for one dashboard row. Every number comes from the stored analysis."""
    item: GateQueueItem | None = (
        await dashboard.gate_item(tenant_id=tenant_id, item_id=d.gate_item_id)
        if d.gate_item_id
        else None
    )
    negotiation = await dashboard.negotiation_for(tenant_id=tenant_id, offer_id=d.offer.id)
    analysis = d.analysis
    return Deal(
        id=d.offer.id,
        mission_id=d.offer.mission_id,
        offer=to_contract_offer(d.offer, analysis),
        state=_state(item),
        price_band=PriceSanityBand(analysis.sanity.band.value),
        confidence_band=SellerConfidenceBand(analysis.confidence.band.value),
        financial_verdict=FinancialVerdict(analysis.fit.verdict),
        signature_status=_signature(item),
        flags=[c.value for c in item.causes] if item is not None else [],
        negotiation=negotiation,
        actions=_actions(d),
        updated_at=analysis.analysed_at,
    )


_STATE_BY_RESOLUTION: dict[GateResolution, DealState] = {
    GateResolution.FOLLOWED: DealState.followed,
    GateResolution.DISCARDED: DealState.discarded,
    GateResolution.HELD: DealState.on_hold,
}


def _state(item: GateQueueItem | None) -> DealState:
    if item is None or item.resolution is None:
        return DealState.open
    return _STATE_BY_RESOLUTION.get(item.resolution, DealState.open)


def _signature(item: GateQueueItem | None) -> SignatureStatus:
    """Signed once the gate item is resolved (resolution only follows a signed decision)."""
    if item is None or item.decision_id is None:
        return SignatureStatus.unsigned
    return (
        SignatureStatus.signed
        if item.status is GateItemStatus.RESOLVED
        else SignatureStatus.pending
    )


def _actions(d: DomainDeal) -> list[ActionAvailability]:
    out = []
    for action in ContractDealAction:
        blocked = [b for b in d.blocked_actions if b.action in (action.value, "all")]
        out.append(
            ActionAvailability(
                action=action,
                allowed=action.value in d.allowed_actions,
                blocked_by=[
                    BlockReason(code=BlockReasonCode(b.reason.value), message=b.detail)
                    for b in blocked
                ],
            )
        )
    return out


@router.post(
    "/deals/{id}/actions",
    response_model=DecisionAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["dashboard"],
)
async def deal_action(
    id: str,
    body: DealActionIn,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    roles: Annotated[tuple[str, ...], Depends(get_roles)],
    dashboard: Annotated[Any, Depends(get_dashboard)],
) -> DecisionAcceptedOut:
    """``follow|renegotiate|takeover|hold|discard``. Every action is a signed decision."""
    try:
        decision = await dashboard.decide(
            tenant_id=tenant_id,
            offer_id=id,
            action=body.action,
            discard_reason=body.discard_reason,
            comment=body.comment,
            roles=list(roles),
        )
    except ActionBlocked as exc:
        raise _blocked(exc) from exc
    except LookupError as exc:
        raise Problem(404, "Deal not found", detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise not_implemented(str(exc)) from exc
    return DecisionAcceptedOut(decision_id=decision.id)


__all__ = ["get_dashboard", "router"]


@router.get("/summary", response_model=DashboardSummary, tags=["dashboard"])
async def get_dashboard_summary(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    dashboard: Annotated[Any, Depends(get_dashboard)],
) -> DashboardSummary:
    """Counters from the gate queue. Signed counts and savings need stores that do not exist yet."""
    items = await dashboard.open_gate_items(tenant_id=tenant_id)
    return DashboardSummary(
        pending_count=len(items),
        signed_count=0,  # ponytail: no signed-deal store yet
        nearest_sla_due_at=min((i.sla_due_at for i in items), default=None),
        savings_by_week=[],  # ponytail: savings need accepted prices, not stored yet
    )


@router.get("/deals/{id}", response_model=Deal, tags=["dashboard"])
async def get_deal(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    dashboard: Annotated[Any, Depends(get_dashboard)],
) -> Deal:
    """One deal by offer id."""
    for deal in await dashboard.deals(tenant_id=tenant_id):
        if deal.offer.id == id:
            return await _contract_deal(dashboard, tenant_id, deal)
    raise Problem(404, "Deal not found", detail=f"deal {id} not found")
