"""Per-tenant hash-chained audit log (D2-10). Same shape as the signature chain in ``apex.signing.decisions``.

``hash = SHA-256(JCS(record))`` and the record includes ``prev_hash``, so changing any stored field of any row
breaks every later link. ``seq`` starts at 1 and has no gaps. The first event chains to ``GENESIS_HASH``.
Time comes from the caller (injected clock), never from this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apex.db.models import ActorType, AuditEvent
from apex.signing import jcs

GENESIS_HASH = "0" * 64


def _ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def event_hash(event: AuditEvent) -> str:
    return jcs.payload_hash(
        {
            "actor_id": event.actor_id,
            "actor_type": ActorType(event.actor_type).value,
            "created_at": _ts(event.created_at),
            "event_type": event.event_type,
            "id": event.id,
            "payload_hash": event.payload_hash,
            "prev_hash": event.prev_hash,
            "seq": event.seq,
            "service_key_id": event.service_key_id,
            "service_signature": event.service_signature,
            "subject_ref": event.subject_ref,
            "tenant_id": event.tenant_id,
        }
    )


async def append(
    session: AsyncSession,
    *,
    event_id: str,
    tenant_id: str,
    actor_type: ActorType,
    actor_id: str,
    event_type: str,
    subject_ref: str,
    payload: Mapping[str, Any],
    now: datetime,
    service_signature: str | None = None,
    service_key_id: str | None = None,
) -> AuditEvent:
    """Chain a new event to the tenant's head. Serialized per tenant by an advisory lock held to commit."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"audit_chain:{tenant_id}")))
    )
    head = await session.scalar(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.seq.desc())
        .limit(1)
    )
    event = AuditEvent(
        id=event_id,
        tenant_id=tenant_id,
        seq=1 if head is None else head.seq + 1,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        subject_ref=subject_ref,
        payload=dict(payload),
        payload_hash=jcs.payload_hash(payload),
        prev_hash=GENESIS_HASH if head is None else head.hash,
        service_signature=service_signature,
        service_key_id=service_key_id,
        created_at=now,
    )
    event.hash = event_hash(event)
    session.add(event)
    await session.flush()
    return event


@dataclass(frozen=True)
class ChainCheck:
    valid: bool
    checked: int
    head_hash: str | None
    first_broken_seq: int | None = None


async def verify(session: AsyncSession, tenant_id: str) -> ChainCheck:
    """Re-walk the whole chain: gap-free seq, links, payload hashes and every record hash."""
    rows = (
        await session.scalars(
            select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.seq)
        )
    ).all()
    prev = GENESIS_HASH
    for index, event in enumerate(rows, start=1):
        if (
            event.seq != index
            or event.prev_hash != prev
            or event.payload_hash != jcs.payload_hash(event.payload)
            or event.hash != event_hash(event)
        ):
            return ChainCheck(False, index - 1, None if index == 1 else prev, event.seq)
        prev = event.hash
    return ChainCheck(True, len(rows), rows[-1].hash if rows else None)
