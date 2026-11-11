"""Approvals inbox (D6-165-contract): a read-only view over the decisions that authorise a purchase.

An approval is a signed decision (``approve_purchase``, or a ``deal_action`` that follows or approves).
``required_signers`` and the signatures come from the decision itself, so dual control is whatever D2-09
decided. The second signature is ``POST /v1/decisions/{id}/sign``, not a route here. No documents exist
until D2-11, so each kind is listed as unavailable.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apex.api.keys import Sessions
from apex.auth.deps import current_principal
from apex.auth.models import Principal
from apex.common.errors import Problem
from apex.common.pagination import Cursor
from apex.contracts.generated.models import (
    ApprovalDocument,
    ApprovalDocumentKind,
    ApprovalInboxStatus,
    ApprovalView,
    ApprovalViewPage,
    Signature,
)
from apex.db import models
from apex.db.models import DecisionStatus, DecisionType
from apex.db.session import tenant_session

router = APIRouter()
Reader = Annotated[Principal, Depends(current_principal)]

_STATUSES: dict[ApprovalInboxStatus, tuple[DecisionStatus, ...]] = {
    ApprovalInboxStatus.sign: (DecisionStatus.PENDING_SIGNATURE,),
    ApprovalInboxStatus.progress: (DecisionStatus.SIGNED,),
    ApprovalInboxStatus.closed: (DecisionStatus.REJECTED, DecisionStatus.EXPIRED),
}


def _is_approval() -> Any:
    """Canonical JSON is compact, so a plain substring finds the action."""
    follows = or_(
        models.Decision.payload_canonical.contains('"action":"approve"'),
        models.Decision.payload_canonical.contains('"action":"follow"'),
    )
    return or_(
        models.Decision.type == DecisionType.APPROVE_PURCHASE,
        and_(models.Decision.type == DecisionType.DEAL_ACTION, follows),
    )


def _view(row: models.Decision, sigs: list[models.Signature]) -> ApprovalView:
    payload = json.loads(row.payload_canonical)
    amount = payload.get("amount")
    status = next(s for s, ds in _STATUSES.items() if row.status in ds)
    return ApprovalView.model_validate(
        {
            "id": row.id,
            "status": status,
            "subject_ref": row.subject_ref,
            "amount": amount if isinstance(amount, dict) else None,
            "seller_ref": payload.get("seller_id"),
            "required_signers": row.required_signers,
            "signatures": [Signature.model_validate(s, from_attributes=True) for s in sigs],
            "documents": [
                ApprovalDocument(kind=k, sha256=None, available=False) for k in ApprovalDocumentKind
            ],
            "tracking": [],
            "created_at": row.created_at,
        }
    )


async def _signatures(session: AsyncSession, ids: list[str]) -> dict[str, list[models.Signature]]:
    out: dict[str, list[models.Signature]] = {i: [] for i in ids}
    rows = await session.scalars(
        select(models.Signature)
        .where(models.Signature.decision_id.in_(ids))
        .order_by(models.Signature.signed_at)
    )
    for r in rows:
        out[r.decision_id].append(r)
    return out


@router.get("", response_model=ApprovalViewPage)
async def list_approvals(
    principal: Reader,
    sessions: Sessions,
    status: ApprovalInboxStatus | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ApprovalViewPage:
    query = select(models.Decision).where(_is_approval())
    if status is not None:
        query = query.where(models.Decision.status.in_(_STATUSES[status]))
    if cursor:
        pos = Cursor.decode(cursor)
        try:
            at, last = datetime.fromisoformat(pos["created_at"]), str(pos["id"])
        except (KeyError, ValueError, TypeError):
            raise Problem(
                400, "Invalid cursor", detail="The pagination cursor is malformed."
            ) from None
        query = query.where(
            or_(
                models.Decision.created_at < at,
                and_(models.Decision.created_at == at, models.Decision.id < last),
            )
        )
    query = query.order_by(models.Decision.created_at.desc(), models.Decision.id.desc()).limit(
        limit + 1
    )
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        rows = list((await session.scalars(query)).all())
        page = rows[:limit]
        sigs = await _signatures(session, [r.id for r in page])
    nxt = (
        Cursor.encode({"created_at": page[-1].created_at.isoformat(), "id": page[-1].id})
        if len(rows) > limit
        else None
    )
    return ApprovalViewPage(items=[_view(r, sigs[r.id]) for r in page], next_cursor=nxt)


@router.get("/{id}", response_model=ApprovalView)
async def get_approval(id: str, principal: Reader, sessions: Sessions) -> ApprovalView:
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        row = await session.scalar(
            select(models.Decision).where(models.Decision.id == id, _is_approval())
        )
        if row is None:
            raise Problem(404, "Approval not found", detail=f"No approval {id}.")
        return _view(row, (await _signatures(session, [id]))[id])
