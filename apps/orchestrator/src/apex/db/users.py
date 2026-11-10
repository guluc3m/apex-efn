"""Map an access-token subject to the ``users`` row (D2-07).

``Principal.user_id`` is the Keycloak ``sub``; rows that reference a person (signing keys, signatures) use
``users.id``, linked through ``users.external_subject``. Run inside ``tenant_session``: RLS shows only members
of that tenant, so a subject that is not a member resolves to ``None``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apex.db.models import User


async def user_id_for_subject(session: AsyncSession, subject: str) -> str | None:
    return await session.scalar(select(User.id).where(User.external_subject == subject))


__all__ = ["user_id_for_subject"]
