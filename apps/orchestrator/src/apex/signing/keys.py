"""Signing key registry: human keys from the browser, service keys from Vault Transit (D2-07, ADR-203).

Only public keys are stored. A row is never deleted and its ``public_key`` never changes: revoking sets
``revoked_at``, which stops new signatures but keeps the key for verifying old ones (spec 5.10.1).

Human keys are tenant rows (RLS); service keys are global rows (``tenant_id`` NULL), so they are written in a
``system_session`` only. One active human key per user: a new device or a lost key means revoke, then enroll.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apex.db.models import SigningKey, SigningKeyOwnerType
from apex.platform.vault import TransitPublicKey, VaultClient
from apex.signing.ed25519 import load_public_key

ALG = "Ed25519"


class SigningKeyError(Exception):
    """Base class. ``code`` is stable and goes into the problem+json body."""

    code = "key_error"


class ActiveKeyExists(SigningKeyError):
    code = "active_key_exists"


class PublicKeyInUse(SigningKeyError):
    code = "public_key_in_use"


class KeyNotFound(SigningKeyError):
    code = "key_not_found"


class KeyAlreadyRevoked(SigningKeyError):
    code = "key_already_revoked"


async def list_owner_keys(session: AsyncSession, owner_id: str) -> Sequence[SigningKey]:
    """Every key of ``owner_id``, revoked and historical ones included, oldest first."""
    rows = await session.scalars(
        select(SigningKey)
        .where(SigningKey.owner_id == owner_id)
        .order_by(SigningKey.created_at, SigningKey.id)
    )
    return rows.all()


async def register_human_key(
    session: AsyncSession,
    *,
    key_id: str,
    tenant_id: str,
    user_id: str,
    public_key: str,
    label: str | None,
    now: datetime,
) -> SigningKey:
    """Store the public half of a browser key. ``session`` must be a ``tenant_session(tenant_id)``."""
    load_public_key(public_key)  # canonical Base64 of 32 bytes, else MalformedKeyOrSignature
    # Serialise enrollments of the same user, so two concurrent requests cannot both pass the check below.
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"signing_key:{user_id}")))
    )
    active = await session.scalar(
        select(SigningKey.id).where(
            SigningKey.owner_type == SigningKeyOwnerType.HUMAN,
            SigningKey.owner_id == user_id,
            SigningKey.revoked_at.is_(None),
        )
    )
    if active is not None:
        raise ActiveKeyExists(f"user already has active key {active}; revoke it first")
    key = SigningKey(
        id=key_id,
        owner_type=SigningKeyOwnerType.HUMAN,
        owner_id=user_id,
        user_id=user_id,
        tenant_id=tenant_id,
        public_key=public_key,
        alg=ALG,
        label=label,
        created_at=now,
    )
    session.add(key)
    try:
        await session.flush()
    except IntegrityError as error:
        # public_key is globally unique; RLS hides other tenants' rows, so this is the only way to see it.
        raise PublicKeyInUse("public key is already registered") from error
    return key


async def revoke(session: AsyncSession, key_id: str, *, reason: str, now: datetime) -> SigningKey:
    """Mark ``key_id`` revoked. Past signatures stay verifiable with the stored public key."""
    key = await session.get(SigningKey, key_id, with_for_update=True)
    if key is None:
        raise KeyNotFound(key_id)
    if key.revoked_at is not None:
        raise KeyAlreadyRevoked(key_id)
    key.revoked_at = now
    key.revoked_reason = reason
    await session.flush()
    return key


def service_key_id(name: str, version: int) -> str:
    return f"svc:{name}:v{version}"


async def register_service_key(
    session: AsyncSession, transit_key: TransitPublicKey, *, now: datetime
) -> SigningKey:
    """Register one Vault Transit key version as a service key. Idempotent per version.

    ``session`` must be a ``system_session`` (service keys are global). The Transit key name is the service
    identity (``owner_id``). Each Transit version is its own row: after a Vault rotation the older versions
    get ``rotated_at`` and keep verifying past signatures.
    """
    key_id = service_key_id(transit_key.name, transit_key.version)
    existing = await session.get(SigningKey, key_id)
    if existing is not None:
        return existing
    older = await session.scalars(
        select(SigningKey).where(
            SigningKey.owner_type == SigningKeyOwnerType.SERVICE,
            SigningKey.owner_id == transit_key.name,
            SigningKey.rotated_at.is_(None),
        )
    )
    for previous in older:
        previous.rotated_at = now
    key = SigningKey(
        id=key_id,
        owner_type=SigningKeyOwnerType.SERVICE,
        owner_id=transit_key.name,
        public_key=base64.b64encode(transit_key.raw).decode("ascii"),
        alg=ALG,
        label=f"vault transit {transit_key.name} v{transit_key.version}",
        vault_key_ref=f"{transit_key.name}:{transit_key.version}",
        created_at=now,
    )
    session.add(key)
    await session.flush()
    return key


async def sync_service_key(
    vault: VaultClient, session: AsyncSession, name: str, *, now: datetime
) -> SigningKey:
    """Make sure Transit has a non-exportable Ed25519 key ``name`` and its latest version is registered."""
    await vault.ensure_signing_key(name)
    return await register_service_key(session, await vault.get_public_key(name), now=now)


__all__ = [
    "ALG",
    "ActiveKeyExists",
    "KeyAlreadyRevoked",
    "KeyNotFound",
    "PublicKeyInUse",
    "SigningKeyError",
    "list_owner_keys",
    "register_human_key",
    "register_service_key",
    "revoke",
    "service_key_id",
    "sync_service_key",
]
