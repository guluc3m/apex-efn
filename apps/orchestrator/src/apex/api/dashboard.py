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
)
from apex.api.gate import DecisionAcceptedOut, _blocked
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_tenant_id

router = APIRouter()


class BlockedOut(BaseModel):
    action: str
    reason: str
    detail: str


class DealOut(BaseModel):
    offer_id: str
    mission_id: str
    platform_id: str
    seller_id: str
    product_id: str
    unit_price_eur_minor: int
    list_price_eur_minor: int | None
    quantity: int
    currency: str
    seller_confidence: dict[str, Any]
    price_sanity: dict[str, Any]
    financial_fit: dict[str, Any]
    gate_item_id: str | None
    allowed_actions: list[str]
    blocked_actions: list[BlockedOut]


class DealsOut(BaseModel):
    deals: list[DealOut]


class DealActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: DealAction
    discard_reason: DiscardReason | None = None
    comment: str | None = Field(default=None, max_length=2000)
    roles: list[str] = Field(default_factory=list)


def get_dashboard() -> Any:
    """Overridable dependency: the dashboard reads offers, analyses and the gate queue."""
    raise not_implemented(
        "the dashboard needs offers (D4-09/D4-10) and the gate agent; wire it in the app"
    )


@router.get("/deals", response_model=DealsOut, tags=["dashboard"])
async def get_deals(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    dashboard: Annotated[Any, Depends(get_dashboard)],
    platform: Annotated[str | None, Query(max_length=64)] = None,
    price_band: Annotated[str | None, Query(max_length=32)] = None,
    verdict: Annotated[str | None, Query(max_length=32)] = None,
    signature_status: Annotated[str | None, Query(max_length=32)] = None,
) -> DealsOut:
    """Deals with the filters the spec asks for (band, verdict, platform, signature status)."""
    deals = await dashboard.deals(
        tenant_id=tenant_id,
        platform=platform,
        price_band=price_band,
        verdict=verdict,
        signature_status=signature_status,
    )
    return DealsOut(
        deals=[
            DealOut(
                offer_id=d.offer.id,
                mission_id=d.offer.mission_id,
                platform_id=d.offer.platform_id,
                seller_id=d.offer.seller_id,
                product_id=d.offer.product_id,
                unit_price_eur_minor=d.offer.unit_price_eur_minor,
                list_price_eur_minor=d.offer.list_price_eur_minor,
                quantity=d.offer.quantity,
                currency=d.offer.currency,
                seller_confidence=d.analysis.confidence.model_dump(mode="json"),
                price_sanity=d.analysis.sanity.model_dump(mode="json"),
                financial_fit=d.analysis.fit.model_dump(mode="json"),
                gate_item_id=d.gate_item_id,
                allowed_actions=d.allowed_actions,
                blocked_actions=[
                    BlockedOut(action=b.action, reason=b.reason.value, detail=b.detail)
                    for b in d.blocked_actions
                ],
            )
            for d in deals
        ]
    )


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
            roles=body.roles,
        )
    except ActionBlocked as exc:
        raise _blocked(exc) from exc
    except LookupError as exc:
        raise Problem(404, "Deal not found", detail=str(exc)) from exc
    return DecisionAcceptedOut(decision_id=decision.id)


__all__ = ["get_dashboard", "router"]
