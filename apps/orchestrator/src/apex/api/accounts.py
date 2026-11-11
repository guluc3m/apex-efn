"""Marketplace accounts (issue 154): credentials go straight into the vault, the database keeps a ``CredentialRef``.

- ``GET    /v1/connected-accounts``       accounts with their status, plus the platforms that can be connected.
- ``POST   /v1/connected-accounts``       store ``{username, password}`` in the vault and connect the account.
- ``DELETE /v1/connected-accounts/{id}``  delete the credential from the vault and disable the account.

Secrets are never returned, logged, put in the audit payload or sent to the LLM: the request model holds the
password as ``SecretStr`` and the only thing that leaves this module is the opaque ``CredentialRef``. Owner and
admin only. Connecting a platform again replaces its previous account, so a tenant has one live account per
platform (the worker resolves "the" active account for a platform).
"""

from __future__ import annotations

import contextlib
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apex.api.keys import get_sessionmaker
from apex.audit.api import AuditEventInput
from apex.audit.api import append as audit_append
from apex.auth.deps import require_role
from apex.auth.models import Principal
from apex.common.clock import Clock, get_clock
from apex.common.errors import Problem
from apex.common.ids import IdGenerator
from apex.contracts.generated.models import (
    ConnectAccountRequest,
    ConnectedAccountList,
    CredentialRef,
)
from apex.contracts.generated.models import ConnectedAccount as AccountOut
from apex.contracts.generated.models import ConnectedAccountStatus as ApiStatus
from apex.db import models
from apex.db.models import ActorType, ConnectedAccountStatus
from apex.db.session import tenant_session
from apex.platform.vault import VaultClient, VaultError

router = APIRouter()
Admin = Annotated[Principal, Depends(require_role("owner", "admin"))]
Sessions = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]

_vault: VaultClient | None = None


def get_vault() -> Any:
    """Overridable dependency: a ``VaultClient`` (``put_credential`` / ``delete_credential``)."""
    global _vault
    if _vault is None:
        try:
            _vault = VaultClient.from_env()
        except VaultError as exc:
            raise _unavailable() from exc
    return _vault


def get_platform_ids() -> list[str]:
    """Overridable dependency: the platforms an account can be connected to."""
    return []


def _unavailable() -> Problem:
    return Problem(
        503,
        "Service Unavailable",
        detail="The credential vault is not available.",
        reason="vault_unavailable",
    )


def _out(row: models.ConnectedAccount) -> AccountOut:
    return AccountOut(
        id=row.id,
        platform=row.platform,
        status=ApiStatus(row.status.value),
        credential_ref=CredentialRef(id=row.credential_ref_id),
    )


async def _audit(
    session: AsyncSession,
    principal: Principal,
    clock: Clock,
    event: str,
    account_id: str,
    platform: str,
) -> None:
    await audit_append(
        session,
        AuditEventInput(
            tenant_id=principal.tenant_id,
            actor_type=ActorType.HUMAN,
            actor_id=principal.user_id,
            event_type=event,
            subject_ref=f"connected_account:{account_id}",
            payload={"account_id": account_id, "platform": platform},
        ),
        clock=clock,
    )


async def _retire(
    session: AsyncSession, vault: Any, tenant_id: str, row: models.ConnectedAccount, clock: Clock
) -> None:
    """Delete the vault credential, mark the account disabled and its ref revoked."""
    ref = await session.get(models.CredentialRef, row.credential_ref_id)
    try:
        await vault.delete_credential(tenant_id, row.credential_ref_id)
    except VaultError as exc:
        raise _unavailable() from exc
    now = clock.now()
    row.status = ConnectedAccountStatus.DISABLED
    row.updated_at = now
    if ref is not None and ref.revoked_at is None:
        ref.revoked_at = now


@router.get("", response_model=ConnectedAccountList)
async def list_connected_accounts(
    principal: Admin,
    sessions: Sessions,
    platforms: Annotated[list[str], Depends(get_platform_ids)],
) -> ConnectedAccountList:
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        rows = (
            await session.scalars(
                select(models.ConnectedAccount)
                .where(models.ConnectedAccount.status != ConnectedAccountStatus.DISABLED)
                .order_by(models.ConnectedAccount.platform, models.ConnectedAccount.id)
            )
        ).all()
        return ConnectedAccountList(items=[_out(r) for r in rows], platforms=platforms)


@router.post("", response_model=AccountOut, status_code=201)
async def connect_account(
    body: ConnectAccountRequest,
    principal: Admin,
    sessions: Sessions,
    vault: Annotated[Any, Depends(get_vault)],
    platforms: Annotated[list[str], Depends(get_platform_ids)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AccountOut:
    if body.platform not in platforms:
        raise Problem(
            422,
            "Unprocessable Entity",
            detail="Unknown platform.",
            reason="unknown_platform",
            errors=[
                {"field": "platform", "code": "unknown_platform", "message": "Unknown platform."}
            ],
        )
    try:
        ref = await vault.put_credential(
            principal.tenant_id,
            {"username": body.username, "password": body.password.get_secret_value()},
        )
    except VaultError as exc:
        raise _unavailable() from exc
    now = clock.now()
    try:
        async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
            old = (
                await session.scalars(
                    select(models.ConnectedAccount).where(
                        models.ConnectedAccount.platform == body.platform,
                        models.ConnectedAccount.status != ConnectedAccountStatus.DISABLED,
                    )
                )
            ).all()
            for row in old:
                await _retire(session, vault, principal.tenant_id, row, clock)
            session.add(
                models.CredentialRef(
                    id=str(ref),
                    tenant_id=principal.tenant_id,
                    vault_path=f"tenants/{principal.tenant_id}/credentials/{ref}",
                    created_at=now,
                )
            )
            await session.flush()
            account = models.ConnectedAccount(
                id=IdGenerator(clock).new_id(),
                tenant_id=principal.tenant_id,
                platform=body.platform,
                status=ConnectedAccountStatus.ACTIVE,
                credential_ref_id=str(ref),
                created_at=now,
                updated_at=now,
            )
            session.add(account)
            await session.flush()
            await _audit(session, principal, clock, "account.connected", account.id, body.platform)
            return _out(account)
    except BaseException:
        # Nothing references the new credential: do not leave it orphaned in the vault.
        with contextlib.suppress(VaultError):
            await vault.delete_credential(principal.tenant_id, ref)
        raise


@router.delete("/{id}", response_model=AccountOut)
async def disconnect_account(
    id: str,
    principal: Admin,
    sessions: Sessions,
    vault: Annotated[Any, Depends(get_vault)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AccountOut:
    async with tenant_session(principal.tenant_id, sessionmaker=sessions) as session:
        row = await session.get(models.ConnectedAccount, id)
        if row is None:
            raise Problem(404, "Not Found", detail=f"No account {id}.", reason="not_found")
        if row.status != ConnectedAccountStatus.DISABLED:
            await _retire(session, vault, principal.tenant_id, row, clock)
            await _audit(session, principal, clock, "account.disconnected", row.id, row.platform)
        return _out(row)
