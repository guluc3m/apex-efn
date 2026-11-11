"""Approvals inbox (D6-165-contract): a read-only view over the decisions that authorise a purchase.

An approval is a signed decision (``approve_purchase``, or a ``deal_action`` that follows or approves).
``required_signers`` and the signatures come from the decision itself, so dual control is whatever D2-09
decided. The second signature is ``POST /v1/decisions/{id}/sign``, not a route here. No documents exist
until the decision is fully signed, so each kind is listed as unavailable before that; after, the PDF is rendered on
demand by ``GET /{id}/documents/{kind}`` (D2-11) and ``POST /{id}/notify-finance`` records an audit event (issue 302).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apex.agents.post_decision import DocumentKind, DocumentRequest
from apex.api.keys import Sessions
from apex.audit.api import AuditEventInput
from apex.audit.api import append as audit_append
from apex.auth.deps import current_principal
from apex.auth.models import Principal
from apex.common.clock import Clock, get_clock
from apex.common.errors import Problem
from apex.common.pagination import Cursor
from apex.contracts.generated.models import (
    ApprovalDocument,
    ApprovalDocumentKind,
    ApprovalFinanceNotice,
    ApprovalInboxStatus,
    ApprovalView,
    ApprovalViewPage,
    Signature,
)
from apex.db import models
from apex.db.models import ActorType, DecisionStatus, DecisionType
from apex.db.session import tenant_session
from apex.documents.render import DocumentError
from apex.documents.service import PdfDocumentService

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
                ApprovalDocument(kind=k, sha256=None, available=row.status == DecisionStatus.SIGNED)
                for k in ApprovalDocumentKind
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


_KINDS = {
    ApprovalDocumentKind.rfq: DocumentKind.RFQ,
    ApprovalDocumentKind.po: DocumentKind.PURCHASE_ORDER,
    ApprovalDocumentKind.certificate: DocumentKind.VERIFICATION_CERTIFICATE,
}


class _CaptureStore:
    """Keeps the rendered bytes for the response; the PDF is derived from the decision, so it is not stored."""

    def __init__(self) -> None:
        self.body = b""

    def put(self, key: str, body: bytes, content_type: str) -> None:
        self.body = body


@router.get(
    "/{id}/documents/{kind}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_approval_document(
    id: str,
    kind: ApprovalDocumentKind,
    principal: Reader,
    sessions: Sessions,
    clock: Annotated[Clock, Depends(get_clock)],
) -> Response:
    """Render the PDF from the signed decision. Unsigned approvals answer 409 ``not_signed``."""
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        row = await session.scalar(
            select(models.Decision).where(models.Decision.id == id, _is_approval())
        )
        if row is None:
            raise Problem(404, "Approval not found", detail=f"No approval {id}.")
        subject = row.subject_ref
    store = _CaptureStore()
    try:
        await PdfDocumentService(sessions, store).generate(
            DocumentRequest(
                kind=_KINDS[kind],
                tenant_id=principal.tenant_id,
                mission_id="",
                offer_id=subject,
                decision_id=id,
                requested_at=clock.now(),
            )
        )
    except DocumentError as exc:
        raise Problem(
            409, "Conflict", detail="The approval is not fully signed yet.", reason="not_signed"
        ) from exc
    return Response(
        store.body,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{kind.value}-{id}.pdf"'},
    )


@router.post("/{id}/notify-finance", response_model=ApprovalFinanceNotice, status_code=202)
async def notify_finance(
    id: str,
    principal: Reader,
    sessions: Sessions,
    clock: Annotated[Clock, Depends(get_clock)],
) -> ApprovalFinanceNotice:
    """Ask Finance for the missing signature. The audit event is the notification (no delivery channel yet)."""
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        row = await session.scalar(
            select(models.Decision).where(models.Decision.id == id, _is_approval())
        )
        if row is None:
            raise Problem(404, "Approval not found", detail=f"No approval {id}.")
        if row.status != DecisionStatus.PENDING_SIGNATURE:
            raise Problem(
                409,
                "Conflict",
                detail="The approval is not waiting for signatures.",
                reason="not_pending",
            )
        await audit_append(
            session,
            AuditEventInput(
                tenant_id=principal.tenant_id,
                actor_type=ActorType.HUMAN,
                actor_id=principal.user_id,
                event_type="approval.finance_notified",
                subject_ref=f"decision:{id}",
                payload={"decision_id": id, "required_signers": row.required_signers},
            ),
            clock=clock,
        )
    return ApprovalFinanceNotice(approval_id=id, notified_at=clock.now())
