"""Signing sessions: a fixed window opened by a Keycloak step-up (D2-08, ADR-204, spec 5.10.4).

``expires_at = auth_at + signing.session_minutes`` and nothing moves it. Every signature goes through
``consume``, which locks the row, checks the session is alive, the key is not revoked and the device matches,
and records the decision. Any failure raises ``ReauthRequired(reason)``, which the API turns into
``428 {error: "reauth_required", reason}``. A failed device check also kills the session, so a stolen
``session_id`` is useless after the first try.

Postgres is the only store: invalidation must be instant (criterion 22), and a row lock per signature is cheap.
All functions take a ``tenant_session``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from apex.db.models import (
    AuthMethod,
    ReauthReason,
    SigningKey,
    SigningKeyOwnerType,
    SigningSession,
    SigningSessionStatus,
)

_ENDED_REASON = {
    SigningSessionStatus.EXPIRED: ReauthReason.SESSION_EXPIRED,
    SigningSessionStatus.EXHAUSTED: ReauthReason.SESSION_EXHAUSTED,
    SigningSessionStatus.CLOSED: ReauthReason.SESSION_REVOKED,
    SigningSessionStatus.REVOKED: ReauthReason.SESSION_REVOKED,
}


class ReauthRequired(Exception):
    def __init__(self, reason: ReauthReason, detail: str = "") -> None:
        super().__init__(detail or reason.value)
        self.reason = reason


def _end(
    row: SigningSession, status: SigningSessionStatus, reason: ReauthReason | None, now: datetime
) -> None:
    row.status = status
    row.revoked_reason = reason
    row.ended_at = now


def refresh(row: SigningSession, now: datetime) -> SigningSession:
    """Expire an active session whose window has passed. Reads call this so the status never lies."""
    if row.status == SigningSessionStatus.ACTIVE and now >= row.expires_at:
        _end(row, SigningSessionStatus.EXPIRED, ReauthReason.SESSION_EXPIRED, row.expires_at)
    return row


async def open_session(
    session: AsyncSession,
    *,
    session_id: str,
    tenant_id: str,
    user_id: str,
    key_id: str,
    device_fingerprint_ref: str,
    auth_at: datetime,
    window: timedelta,
    max_decisions: int,
    now: datetime,
) -> SigningSession:
    expires_at = auth_at + window
    if now >= expires_at or auth_at > now:
        raise ReauthRequired(
            ReauthReason.STEP_UP_REQUIRED, "the step-up is too old to open a window"
        )
    key = await session.get(SigningKey, key_id)
    if key is None or key.owner_type != SigningKeyOwnerType.HUMAN or key.owner_id != user_id:
        raise LookupError(key_id)
    if key.revoked_at is not None:
        raise ReauthRequired(ReauthReason.KEY_REVOKED, "the key is revoked; enroll a new one")
    row = SigningSession(
        id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        key_id=key_id,
        auth_method=AuthMethod.KEYCLOAK_STEP_UP,
        auth_at=auth_at,
        expires_at=expires_at,
        device_fingerprint_ref=device_fingerprint_ref,
        decisions_signed=[],
        max_decisions=max_decisions,
        status=SigningSessionStatus.ACTIVE,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def get_own(
    session: AsyncSession, session_id: str, user_id: str, *, lock: bool = False
) -> SigningSession | None:
    row = await session.get(SigningSession, session_id, with_for_update=lock)
    return row if row is not None and row.user_id == user_id else None


async def close(session: AsyncSession, row: SigningSession, now: datetime) -> SigningSession:
    if refresh(row, now).status == SigningSessionStatus.ACTIVE:
        _end(row, SigningSessionStatus.CLOSED, None, now)
        await session.flush()
    return row


async def consume(
    session: AsyncSession,
    session_id: str,
    *,
    user_id: str,
    key_id: str,
    device_fingerprint_ref: str,
    decision_id: str,
    now: datetime,
) -> SigningSession:
    """Spend one signature of the window on ``decision_id``, or raise ``ReauthRequired``. For D2-09.

    The signature that reaches ``max_decisions`` is accepted and ends the session as ``exhausted``. On a refusal
    the session's new state is **committed** before raising, so the caller's rollback cannot revive it.
    """
    row = await get_own(session, session_id, user_id, lock=True)
    if row is None or row.key_id != key_id:
        raise ReauthRequired(ReauthReason.SESSION_MISSING)
    refresh(row, now)
    if row.status != SigningSessionStatus.ACTIVE:
        await session.commit()
        raise ReauthRequired(row.revoked_reason or _ENDED_REASON[row.status])
    key = await session.get(SigningKey, key_id)
    if key is None or key.revoked_at is not None:
        _end(row, SigningSessionStatus.REVOKED, ReauthReason.KEY_REVOKED, now)
        await session.commit()
        raise ReauthRequired(ReauthReason.KEY_REVOKED)
    if device_fingerprint_ref != row.device_fingerprint_ref:
        _end(row, SigningSessionStatus.REVOKED, ReauthReason.DEVICE_MISMATCH, now)
        await session.commit()
        raise ReauthRequired(ReauthReason.DEVICE_MISMATCH)
    signed = row.decisions_signed or []
    if decision_id not in signed:
        signed = row.decisions_signed = [*signed, decision_id]
    if len(signed) >= row.max_decisions:
        _end(row, SigningSessionStatus.EXHAUSTED, ReauthReason.SESSION_EXHAUSTED, now)
    await session.flush()
    return row


async def invalidate(
    session: AsyncSession, session_id: str, reason: ReauthReason, *, now: datetime
) -> bool:
    """End an active session at once: ``risk_flagged`` (GateAgent), ``network_anomaly``, logout. True if it was active."""
    result = await session.execute(
        update(SigningSession)
        .where(
            SigningSession.id == session_id, SigningSession.status == SigningSessionStatus.ACTIVE
        )
        .values(status=SigningSessionStatus.REVOKED, revoked_reason=reason, ended_at=now)
    )
    return bool(getattr(result, "rowcount", 0))


async def mark_session_risky(session: AsyncSession, session_id: str, *, now: datetime) -> bool:
    """AGENTS.md section 4 seam for the GateAgent."""
    return await invalidate(session, session_id, ReauthReason.RISK_FLAGGED, now=now)


async def invalidate_user_sessions(
    session: AsyncSession, user_id: str, reason: ReauthReason, *, now: datetime
) -> None:
    """End every active session of ``user_id``. The logout hook (DEV-1) calls it with ``session_revoked``."""
    await session.execute(
        update(SigningSession)
        .where(
            SigningSession.user_id == user_id, SigningSession.status == SigningSessionStatus.ACTIVE
        )
        .values(status=SigningSessionStatus.REVOKED, revoked_reason=reason, ended_at=now)
    )


async def invalidate_key_sessions(session: AsyncSession, key_id: str, *, now: datetime) -> None:
    """End every active session of a revoked key. ``keys.revoke`` calls this in the same transaction."""
    await session.execute(
        update(SigningSession)
        .where(
            SigningSession.key_id == key_id, SigningSession.status == SigningSessionStatus.ACTIVE
        )
        .values(
            status=SigningSessionStatus.REVOKED,
            revoked_reason=ReauthReason.KEY_REVOKED,
            ended_at=now,
        )
    )


__all__ = [
    "ReauthRequired",
    "close",
    "consume",
    "get_own",
    "invalidate",
    "invalidate_key_sessions",
    "invalidate_user_sessions",
    "mark_session_risky",
    "open_session",
    "refresh",
]
