"""Decision endpoints (D2-09, ADR-209). Mounted at ``/v1/decisions``.

- ``POST ""``            create a ``pending_signature`` decision; ``params`` is the payload, stored in RFC 8785 form.
- ``POST /{id}/sign``    attach a browser signature. Verified before it is stored, spends one signature of the
                         window (``428 reauth_required`` otherwise), and is chained per tenant.
- ``POST /{id}/verify``  re-check the stored payload, every signature and its chain hash. Read-only.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apex.api.keys import (
    Now,
    Sessions,
    Signer,
    decision_problem,
    get_signing_service,
    member_id,
)
from apex.api.signing import NetworkRef, reauth_problem
from apex.auth.deps import current_principal
from apex.auth.models import Principal
from apex.common.ids import IdGenerator
from apex.contracts.generated.models import (
    CreateDecisionRequest,
    Decision,
    Signature,
    SignDecisionRequest,
    VerificationCheck,
    VerificationResult,
)
from apex.db import models
from apex.db.models import ActorType
from apex.db.session import tenant_session
from apex.signing import decisions
from apex.signing.api import SigningService
from apex.signing.sessions import ReauthRequired
from apex.tenant_config.errors import ConfigKeyUnset

router = APIRouter()
Reader = Annotated[Principal, Depends(current_principal)]  # verifying is read-only: viewers too
Service = Annotated[SigningService, Depends(get_signing_service)]


def _signature(row: models.Signature) -> Signature:
    return Signature.model_validate(row, from_attributes=True)


async def _view(session: AsyncSession, decision_id: str) -> Decision:
    row = await session.get(models.Decision, decision_id)
    if row is None:
        raise decision_problem(decisions.DecisionNotFound(decision_id))
    sigs = await session.scalars(
        select(models.Signature)
        .where(models.Signature.decision_id == decision_id)
        .order_by(models.Signature.signed_at)
    )
    return Decision.model_validate(
        {
            **{k: getattr(row, k) for k in Decision.model_fields if hasattr(row, k)},
            "signatures": [_signature(s) for s in sigs],
            "decided_by": {"type": row.created_by_type, "id": row.created_by_id},
        }
    )


@router.post("", response_model=Decision, status_code=status.HTTP_201_CREATED)
async def create_decision(
    body: CreateDecisionRequest, principal: Signer, sessions: Sessions, service: Service
) -> Decision:
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        user_id = await member_id(session, principal)
    try:
        ref = await service.create_decision(
            body.type.value,
            body.subject_ref,
            body.params,
            tenant_id=principal.tenant_id,
            created_by=(ActorType.HUMAN, user_id),
        )
    except decisions.DecisionError as error:
        raise decision_problem(error) from error
    except ConfigKeyUnset as error:
        raise decision_problem(decisions.InvalidPayload(str(error))) from error
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        return await _view(session, ref.id)


@router.get("/{id}", response_model=Decision)
async def get_decision(id: str, principal: Reader, sessions: Sessions) -> Decision:
    """The decision with its canonical payload: the bytes a signer must sign."""
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        return await _view(session, id)


@router.post("/{id}/sign", response_model=Signature, status_code=status.HTTP_201_CREATED)
async def sign_decision(
    id: str,
    body: SignDecisionRequest,
    principal: Signer,
    sessions: Sessions,
    clock: Now,
    network_ref: NetworkRef,
) -> Signature:
    try:
        async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
            row = await decisions.sign_human(
                session,
                id,
                signature_id=IdGenerator(clock).new_id(),
                user_id=await member_id(session, principal),
                key_id=body.key_id,
                payload_hash=body.payload_hash,
                signature=body.signature,
                signing_session_id=body.signing_session_id,
                device_fingerprint_ref=body.device_fingerprint_ref,
                client_attestation=body.client_attestation,
                now=clock.now(),
                network_ref=network_ref,
            )
            return _signature(row)
    except ReauthRequired as error:
        raise reauth_problem(error) from error
    except decisions.DecisionError as error:
        raise decision_problem(error) from error


@router.post("/{id}/verify", response_model=VerificationResult)
async def verify_decision(
    id: str, principal: Reader, sessions: Sessions, clock: Now
) -> VerificationResult:
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        try:
            check = await decisions.verify(session, id)
        except decisions.DecisionError as error:
            raise decision_problem(error) from error
    return VerificationResult(
        decision_id=id,
        valid=check.intact and check.enough_signers,
        checks=[
            VerificationCheck(name=c.name, ok=c.ok, detail=c.detail or None) for c in check.checks
        ],
        verified_at=clock.now(),
    )
