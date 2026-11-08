"""Seller endpoints (owner: DEV-4, D4-10).

``GET /v1/sellers/{id}/confidence`` returns the latest confidence with its full history, so a decision can
be checked against what was known at the time. ``POST .../recompute`` forces a recomputation and is audited.

The engines are DEV-3's; these endpoints only call them through the analysis nodes and persist the result.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict

from apex.agents.analysis import AnalysisNodes
from apex.agents.offers import SellerConfidenceRecord
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_tenant_id

router = APIRouter()


class ConfidenceRecordOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    band: str
    score: int | None
    model_version: str
    config_version: str
    computed_at: str
    signals_used: int

    @classmethod
    def of(cls, record: SellerConfidenceRecord) -> ConfidenceRecordOut:
        return cls(
            band=record.band.value,
            score=record.score,
            model_version=record.model_version,
            config_version=record.config_version,
            computed_at=record.computed_at.isoformat(),
            signals_used=record.signals_used,
        )


class SellerConfidenceOut(BaseModel):
    seller_id: str
    tenant_id: str
    latest: ConfidenceRecordOut | None
    history: list[ConfidenceRecordOut]


class RecomputeOut(BaseModel):
    seller_id: str
    recomputed: bool
    latest: ConfidenceRecordOut


def get_analysis_nodes() -> AnalysisNodes:
    """Overridable dependency. The default refuses: the DEV-3 engines are not wired into the app yet."""
    raise not_implemented(
        "seller confidence needs the DEV-3 trust engine; wire AnalysisNodes in the app (D3-06 + D2-05)"
    )


@router.get("/{id}/confidence", response_model=SellerConfidenceOut, tags=["sellers"])
async def get_seller_confidence(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    nodes: Annotated[AnalysisNodes, Depends(get_analysis_nodes)],
) -> SellerConfidenceOut:
    """Latest confidence plus its history. An unknown seller is an empty history, not a 404."""
    history = await nodes.seller_history(tenant_id=tenant_id, seller_id=id)
    return SellerConfidenceOut(
        seller_id=id,
        tenant_id=tenant_id,
        latest=ConfidenceRecordOut.of(history[-1]) if history else None,
        history=[ConfidenceRecordOut.of(r) for r in history],
    )


@router.post(
    "/{id}/confidence/recompute",
    response_model=RecomputeOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["sellers"],
)
async def recompute_seller_confidence(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    nodes: Annotated[AnalysisNodes, Depends(get_analysis_nodes)],
) -> RecomputeOut:
    """Force a recomputation. Audited, because an operator asked for it."""
    try:
        record = await nodes.score_seller(tenant_id=tenant_id, seller_id=id, signals={}, force=True)
    except NotImplementedError as exc:  # engine not wired
        raise not_implemented(str(exc)) from exc
    except ValueError as exc:
        raise Problem(422, "Cannot recompute", detail=str(exc)) from exc
    return RecomputeOut(seller_id=id, recomputed=True, latest=ConfidenceRecordOut.of(record))


__all__ = ["get_analysis_nodes", "router"]
