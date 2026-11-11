"""Audit endpoints (D2-10). Mounted at ``/v1/audit``. ``owner`` and ``admin`` only (there is no compliance role)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from apex.api.keys import Now, Sessions
from apex.audit import anchor, chain
from apex.auth.deps import require_role
from apex.auth.models import Principal
from apex.common.pagination import Cursor
from apex.contracts.generated.models import (
    Actor,
    ActorType,
    AuditEvent,
    AuditEventPage,
    ChainVerification,
)
from apex.db import models
from apex.db.session import tenant_session

router = APIRouter()
Auditor = Annotated[Principal, Depends(require_role("owner", "admin"))]
# ponytail: transport cap on page size; move to settings if it ever differs per tenant.
MAX_PAGE = 200


def get_anchor_store(request: Request) -> anchor.AnchorStore | None:
    return getattr(request.app.state, "anchor_store", None)


def _view(row: models.AuditEvent) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        seq=row.seq,
        actor=Actor(type=ActorType(row.actor_type.value), id=row.actor_id),
        event_type=row.event_type,
        subject_ref=row.subject_ref,
        payload_hash=row.payload_hash,
        prev_hash=row.prev_hash,
        hash=row.hash,
        created_at=row.created_at,
    )


@router.get("", response_model=AuditEventPage)
async def list_audit_events(
    principal: Auditor,
    sessions: Sessions,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    subject_ref: str | None = None,
    event_type: str | None = None,
) -> AuditEventPage:
    """Newest first, keyset on ``seq``."""
    query = (
        select(models.AuditEvent)
        .where(models.AuditEvent.tenant_id == principal.tenant_id)
        .order_by(models.AuditEvent.seq.desc())
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(models.AuditEvent.seq < int(Cursor.decode(cursor)["seq"]))
    if subject_ref:
        query = query.where(models.AuditEvent.subject_ref == subject_ref)
    if event_type:
        query = query.where(models.AuditEvent.event_type == event_type)
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        rows = list((await session.scalars(query)).all())
    page = rows[:limit]
    more = Cursor.encode({"seq": page[-1].seq}) if len(rows) > limit else None
    return AuditEventPage(items=[_view(r) for r in page], next_cursor=more)


@router.get("/verify", response_model=ChainVerification)
async def verify_audit_chain(
    principal: Auditor,
    sessions: Sessions,
    clock: Now,
    store: Annotated[anchor.AnchorStore | None, Depends(get_anchor_store)],
) -> ChainVerification:
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        check = await chain.verify(session, principal.tenant_id)
        anchored = anchor.read_anchor(store, principal.tenant_id) if store else None
        valid, broken = check.valid, check.first_broken_seq
        if (
            valid
            and anchored is not None
            and not await anchor.anchor_matches(session, principal.tenant_id, anchored)
        ):
            valid, broken = False, anchored.seq  # the chain was rewritten behind the WORM anchor
    return ChainVerification(
        valid=valid,
        checked_events=check.checked,
        head_hash=check.head_hash,
        first_broken_seq=broken,
        anchored_head_hash=anchored.hash if anchored else None,
        anchored_at=anchored.at if anchored else None,
        verified_at=clock.now(),
    )
