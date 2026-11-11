"""Signing session endpoints (D2-08, ADR-204). Mounted at ``/v1/signing-sessions``.

- ``POST ""``      open a fixed window from the step-up token's ``auth_time``.
- ``GET  /{id}``   state, remaining signatures and ``server_time`` for the UI countdown.
- ``DELETE /{id}`` close the window explicitly.
- ``DELETE ""``    revoke every active window of the caller (logout on all devices, issue #272).

Sessions belong to their user: another user's (or tenant's) session is 404. Signatures consume the window in
D2-09 through ``apex.signing.sessions.consume``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from apex.api.keys import Now, Sessions, Signer, member_id
from apex.common.errors import Problem, not_implemented
from apex.common.ids import IdGenerator
from apex.contracts.generated.models import OpenSigningSessionRequest, SigningSession
from apex.db import models
from apex.db.session import tenant_session
from apex.signing import sessions as signing_sessions
from apex.signing.sessions import ReauthRequired

router = APIRouter()


@dataclass(frozen=True)
class SigningLimits:
    window: timedelta
    max_decisions: int


async def get_signing_limits(request: Request, principal: Signer) -> SigningLimits:
    """``signing.session_minutes`` and ``signing.max_decisions_per_session`` of the caller's tenant."""
    services = getattr(request.app.state, "app_services", None)
    if services is None:
        raise not_implemented("tenant config is not wired into the app")
    config = await services.tenant_config.effective(principal.tenant_id)
    return SigningLimits(
        window=timedelta(minutes=config.get("signing.session_minutes").require()),
        max_decisions=config.get("signing.max_decisions_per_session").require(),
    )


def reauth_problem(error: ReauthRequired) -> Problem:
    """``428 {error: "reauth_required", reason}``: the one answer for every invalid signing state."""
    return Problem(
        428,
        "Precondition Required",
        detail=str(error),
        error="reauth_required",
        reason=error.reason.value,
    )


def _view(row: models.SigningSession, now: datetime) -> SigningSession:
    signed = row.decisions_signed or []
    active = row.status == models.SigningSessionStatus.ACTIVE
    return SigningSession.model_validate(
        {
            "id": row.id,
            "user_id": row.user_id,
            "key_id": row.key_id,
            "auth_method": row.auth_method,
            "auth_at": row.auth_at,
            "expires_at": row.expires_at,
            "device_fingerprint_ref": row.device_fingerprint_ref,
            "decisions_signed": signed,
            "max_decisions": row.max_decisions,
            "remaining_decisions": max(row.max_decisions - len(signed), 0) if active else 0,
            "status": row.status,
            "revoked_reason": row.revoked_reason,
            "server_time": now,
        }
    )


@router.post("", response_model=SigningSession, status_code=status.HTTP_201_CREATED)
async def open_signing_session(
    body: OpenSigningSessionRequest,
    principal: Signer,
    sessions: Sessions,
    clock: Now,
    limits: Annotated[SigningLimits, Depends(get_signing_limits)],
) -> SigningSession:
    if principal.auth_time is None:
        raise reauth_problem(
            ReauthRequired(
                models.ReauthReason.STEP_UP_REQUIRED, "a signing window needs a step-up token"
            )
        )
    now = clock.now()
    try:
        async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
            row = await signing_sessions.open_session(
                session,
                session_id=IdGenerator(clock).new_id(),
                tenant_id=principal.tenant_id,
                user_id=await member_id(session, principal),
                key_id=body.key_id,
                device_fingerprint_ref=body.device_fingerprint_ref,
                auth_at=datetime.fromtimestamp(principal.auth_time, UTC),
                window=limits.window,
                max_decisions=limits.max_decisions,
                now=now,
            )
            return _view(row, now)
    except ReauthRequired as error:
        raise reauth_problem(error) from error
    except LookupError as error:
        raise Problem(
            422,
            "Unprocessable Content",
            detail="key_id is not one of your keys",
            code="unknown_key",
        ) from error


async def _own(session: AsyncSession, id: str, principal: Signer) -> models.SigningSession:
    row = await signing_sessions.get_own(
        session, id, await member_id(session, principal), lock=True
    )
    if row is None:
        raise Problem(404, "Not Found", detail=f"signing session {id} not found")
    return row


@router.get("/{id}", response_model=SigningSession)
async def get_signing_session(
    id: str, principal: Signer, sessions: Sessions, clock: Now
) -> SigningSession:
    now = clock.now()
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        return _view(signing_sessions.refresh(await _own(session, id, principal), now), now)


@router.delete("/{id}", response_model=SigningSession)
async def close_signing_session(
    id: str, principal: Signer, sessions: Sessions, clock: Now
) -> SigningSession:
    now = clock.now()
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        row = await signing_sessions.close(session, await _own(session, id, principal), now)
        return _view(row, now)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def close_all_my_signing_sessions(
    principal: Signer, sessions: Sessions, clock: Now
) -> Response:
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        await signing_sessions.invalidate_user_sessions(
            session,
            await member_id(session, principal),
            models.ReauthReason.SESSION_REVOKED,
            now=clock.now(),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
