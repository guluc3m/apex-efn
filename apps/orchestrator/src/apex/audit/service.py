"""Scheduled audit job (D2-10 follow-up): verify every tenant's chain and anchor the heads to WORM storage.

Implements the ``AuditChainVerifier`` port of ``apex.workers`` structurally. Nothing is defaulted: the tenant
list, the store and the WORM retention (a business value) are injected by whoever wires the app.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apex.audit import anchor
from apex.common.clock import Clock
from apex.db.session import tenant_session
from apex.workers.ports import AuditVerifyResult


class AuditChainService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        tenant_ids: Callable[[], Awaitable[Sequence[str]]],
        store: anchor.AnchorStore,
        clock: Clock,
        retention: timedelta,
    ) -> None:
        self._sessions = sessionmaker
        self._tenant_ids = tenant_ids
        self._store = store
        self._clock = clock
        self._retention = retention

    async def verify_chain(self) -> AuditVerifyResult:
        """Verify and anchor every tenant. A broken chain is reported (first broken seq) and never anchored."""
        checked = 0
        first_broken: int | None = None
        ok = True
        for tenant_id in await self._tenant_ids():
            async with tenant_session(tenant_id, sessionmaker=self._sessions) as session:
                check = await anchor.anchor_head(
                    session,
                    self._store,
                    tenant_id,
                    now=self._clock.now(),
                    retention=self._retention,
                )
            checked += check.checked
            if not check.valid:
                ok = False
                if first_broken is None:
                    first_broken = check.first_broken_seq
        return AuditVerifyResult(chain_ok=ok, events_checked=checked, first_broken_seq=first_broken)
