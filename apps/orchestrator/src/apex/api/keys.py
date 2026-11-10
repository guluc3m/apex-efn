"""Signing key endpoints (D2-07, ADR-203). Mounted at ``/v1/keys``.

- ``GET  /me``           the caller's public keys, revoked and historical ones included.
- ``POST /me``           enroll the public half of a non-exportable browser key. Needs a fresh step-up
                         (``auth_time`` within ``signing.session_minutes``), else ``428 step_up_required``.
- ``POST /{id}/revoke``  revoke a key with a signed ``revoke_key`` decision whose ``subject_ref`` is
                         ``signing_key:<id>``. The key owner, or an ``owner``/``admin`` (lost device).

Signed decisions are D2-09: until it merges, ``get_decision_verifier`` answers 501, so a key cannot be revoked
over HTTP without a real signature. Invalidating the signing sessions of a revoked key is D2-08.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apex.auth.deps import require_signer
from apex.auth.models import Principal
from apex.common.clock import Clock, get_clock
from apex.common.errors import Problem, not_implemented
from apex.common.ids import IdGenerator
from apex.contracts.generated.models import (
    Decision,
    DecisionStatus,
    DecisionType,
    RegisterSigningKeyRequest,
    RevokeSigningKeyRequest,
    SigningKey,
    SigningKeyList,
)
from apex.db import models
from apex.db.session import default_sessionmaker, tenant_session
from apex.db.users import user_id_for_subject
from apex.signing import keys
from apex.signing.ed25519 import MalformedKeyOrSignature

router = APIRouter()

KEY_ADMIN_ROLES = ("owner", "admin")
Signer = Annotated[Principal, Depends(require_signer())]


class DecisionVerifier(Protocol):
    async def require_signed(self, decision_id: str, *, tenant_id: str) -> Decision: ...


class _UnwiredDecisions:
    async def require_signed(self, decision_id: str, *, tenant_id: str) -> Decision:
        raise not_implemented("signed decisions are D2-09; key revocation needs one")


def get_decision_verifier() -> DecisionVerifier:
    return _UnwiredDecisions()


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return default_sessionmaker()


async def get_enrollment_max_age(request: Request, principal: Signer) -> timedelta:
    """``signing.session_minutes`` of the caller's tenant: the same freshness a signing session gets."""
    services = getattr(request.app.state, "app_services", None)
    if services is None:
        raise not_implemented("tenant config is not wired into the app")
    config = await services.tenant_config.effective(principal.tenant_id)
    return timedelta(minutes=config.get("signing.session_minutes").require())


Sessions = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
Now = Annotated[Clock, Depends(get_clock)]


def _view(key: models.SigningKey) -> SigningKey:
    return SigningKey.model_validate(key, from_attributes=True)


def _conflict(error: keys.SigningKeyError) -> Problem:
    return Problem(409, "Conflict", detail=str(error), code=error.code)


def _reauth(detail: str) -> Problem:
    return Problem(
        428,
        "Precondition Required",
        detail=detail,
        error="reauth_required",
        reason="step_up_required",
    )


async def member_id(session: AsyncSession, principal: Principal) -> str:
    user_id = await user_id_for_subject(session, principal.user_id)
    if user_id is None:
        raise Problem(
            403,
            "Forbidden",
            detail="no user of this tenant is linked to the token subject",
            code="user_not_provisioned",
        )
    return user_id


@router.get("/me", response_model=SigningKeyList)
async def list_my_keys(principal: Signer, sessions: Sessions) -> SigningKeyList:
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        rows = await keys.list_owner_keys(session, await member_id(session, principal))
        return SigningKeyList(items=[_view(row) for row in rows])


@router.post("/me", response_model=SigningKey, status_code=status.HTTP_201_CREATED)
async def register_my_key(
    body: RegisterSigningKeyRequest,
    principal: Signer,
    sessions: Sessions,
    clock: Now,
    max_age: Annotated[timedelta, Depends(get_enrollment_max_age)],
) -> SigningKey:
    now = clock.now()
    if principal.auth_time is None:
        raise _reauth("enrolling a key needs a step-up token with auth_time")
    if now - datetime.fromtimestamp(principal.auth_time, UTC) > max_age:
        raise _reauth("the last strong authentication is too old to enroll a key")
    try:
        async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
            row = await keys.register_human_key(
                session,
                key_id=IdGenerator(clock).new_id(),
                tenant_id=principal.tenant_id,
                user_id=await member_id(session, principal),
                public_key=body.public_key,
                label=body.label,
                now=now,
            )
            return _view(row)
    except MalformedKeyOrSignature as error:
        raise Problem(
            422, "Unprocessable Content", detail=str(error), code="invalid_public_key"
        ) from error
    except keys.SigningKeyError as error:
        raise _conflict(error) from error


@router.post("/{id}/revoke", response_model=SigningKey)
async def revoke_key(
    id: str,
    body: RevokeSigningKeyRequest,
    principal: Signer,
    sessions: Sessions,
    clock: Now,
    decisions: Annotated[DecisionVerifier, Depends(get_decision_verifier)],
) -> SigningKey:
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        key = await session.get(models.SigningKey, id)  # RLS: another tenant's key is not found
        if key is None:
            raise Problem(404, "Not Found", detail=f"signing key {id} not found")
        if key.owner_id != await member_id(session, principal) and not principal.has_role(
            *KEY_ADMIN_ROLES
        ):
            raise Problem(
                403, "Forbidden", detail="only the key owner or an owner/admin may revoke it"
            )
        decision = await decisions.require_signed(body.decision_id, tenant_id=principal.tenant_id)
        if (
            decision.status is not DecisionStatus.signed
            or decision.type is not DecisionType.revoke_key
            or decision.subject_ref != f"signing_key:{id}"
        ):
            raise Problem(
                409,
                "Conflict",
                detail="decision is not a signed revoke_key for this key",
                code="decision_mismatch",
            )
        try:
            row = await keys.revoke(session, id, reason=f"decision:{decision.id}", now=clock.now())
        except keys.SigningKeyError as error:
            raise _conflict(error) from error
        return _view(row)
