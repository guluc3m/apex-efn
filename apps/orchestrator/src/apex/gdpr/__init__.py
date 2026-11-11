"""GDPR tooling (D2-12, ADR-210): subject export, erasure by pseudonymisation and retention purge.

Nothing here edits a chained table (signatures, decisions, audit_events). Time comes from the caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apex.db.models import (
    AuditEvent,
    Membership,
    ReauthReason,
    Signature,
    SigningKey,
    SigningSession,
    SigningSessionStatus,
    User,
)
from apex.signing import sessions as signing_sessions

ERASED = "erased"


class SubjectNotFound(LookupError):
    pass


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


async def export_subject(session: AsyncSession, user_id: str) -> dict[str, Any]:
    """Everything we hold about ``user_id`` in the session's tenant (RLS). Run it once per tenant of the user."""
    user = await session.get(User, user_id)
    if user is None:
        raise SubjectNotFound(user_id)

    async def rows(stmt: Any) -> list[Any]:
        return list((await session.scalars(stmt)).all())

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "external_subject": user.external_subject,
            "created_at": _iso(user.created_at),
        },
        "memberships": [
            {"tenant_id": m.tenant_id, "role": str(m.role), "created_at": _iso(m.created_at)}
            for m in await rows(select(Membership).where(Membership.user_id == user_id))
        ],
        "keys": [
            {
                "id": k.id,
                "public_key": k.public_key,
                "alg": k.alg,
                "label": k.label,
                "created_at": _iso(k.created_at),
                "revoked_at": _iso(k.revoked_at),
            }
            for k in await rows(select(SigningKey).where(SigningKey.user_id == user_id))
        ],
        "signing_sessions": [
            {
                "id": s.id,
                "auth_at": _iso(s.auth_at),
                "device_fingerprint_ref": s.device_fingerprint_ref,
                "status": str(s.status),
                "ended_at": _iso(s.ended_at),
            }
            for s in await rows(select(SigningSession).where(SigningSession.user_id == user_id))
        ],
        "signatures": [
            {"id": s.id, "decision_id": s.decision_id, "signed_at": _iso(s.signed_at)}
            for s in await rows(select(Signature).where(Signature.signer_id == user_id))
        ],
        "audit_events": [
            {
                "id": e.id,
                "seq": int(e.seq),
                "event_type": e.event_type,
                "created_at": _iso(e.created_at),
            }
            for e in await rows(select(AuditEvent).where(AuditEvent.actor_id == user_id))
        ],
    }


async def erase_subject(session: AsyncSession, user_id: str, *, now: datetime) -> None:
    """Pseudonymise ``user_id`` and cut their ability to sign. Chains are untouched (ADR-210).

    Tenant-scoped rows (sessions, keys) are only visible inside a ``tenant_session``: run it once per tenant of
    the user. The ``users`` update is global and idempotent.
    """
    user = await session.get(User, user_id, with_for_update=True)
    if user is None:
        raise SubjectNotFound(user_id)
    user.email = f"{ERASED}+{user_id}@invalid"
    user.display_name = f"{ERASED} user"
    user.external_subject = None
    user.updated_at = now
    await signing_sessions.invalidate_user_sessions(
        session, user_id, ReauthReason.SESSION_REVOKED, now=now
    )
    await session.execute(
        update(SigningSession)
        .where(SigningSession.user_id == user_id)
        .values(device_fingerprint_ref=ERASED)
    )
    await session.execute(
        update(SigningKey)
        .where(SigningKey.user_id == user_id)
        .where(SigningKey.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason="gdpr_erasure")
    )
    await session.execute(
        update(SigningKey).where(SigningKey.user_id == user_id).values(label=None)
    )
    await session.flush()


def retention_cutoff(
    retention_days: Mapping[str, int | None], data_class: str, *, now: datetime
) -> datetime | None:
    """``None`` (keep) when the tenant has not set a period for the class. No default is invented."""
    days = retention_days.get(data_class)
    return None if days is None else now - timedelta(days=days)


async def purge_session_fingerprints(session: AsyncSession, cutoff: datetime) -> int:
    """Ended sessions older than ``cutoff`` lose their device fingerprint. Returns the rows changed."""
    result = await session.execute(
        update(SigningSession)
        .where(
            SigningSession.status != SigningSessionStatus.ACTIVE,
            SigningSession.ended_at < cutoff,
            SigningSession.device_fingerprint_ref != ERASED,
        )
        .values(device_fingerprint_ref=ERASED)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
