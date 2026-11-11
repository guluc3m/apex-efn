"""``apex.audit.api``: the seam for other lanes (AGENTS.md section 4). ``append(event)`` chains one event."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apex.audit import chain
from apex.common.clock import Clock
from apex.common.ids import IdGenerator
from apex.db.models import ActorType, AuditEvent


@dataclass(frozen=True)
class AuditEventInput:
    tenant_id: str
    actor_type: ActorType
    actor_id: str
    event_type: str
    subject_ref: str
    payload: Mapping[str, Any]
    service_signature: str | None = None
    service_key_id: str | None = None


async def append(session: AsyncSession, event: AuditEventInput, *, clock: Clock) -> AuditEvent:
    """Append inside the caller's transaction, so the event commits or rolls back with the action it records."""
    return await chain.append(
        session,
        event_id=IdGenerator(clock).new_id(),
        tenant_id=event.tenant_id,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        event_type=event.event_type,
        subject_ref=event.subject_ref,
        payload=event.payload,
        now=clock.now(),
        service_signature=event.service_signature,
        service_key_id=event.service_key_id,
    )
