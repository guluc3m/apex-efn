"""Postgres checkpointer for the per-offer graph (D4-06).

Opens an ``AsyncPostgresSaver`` on a DSN. ``setup()`` creates the checkpointer's own tables; that is the
library's schema, kept apart from the Prisma-owned business schema (ADR-201 covers business tables only).
DEV-2 reviews wiring the DSN and role into the app (RLS does not apply to these tables, they hold graph
state keyed by thread id ``<mission>:<offer>``, and every state value is plain JSON without secrets).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


@asynccontextmanager
async def postgres_checkpointer(
    dsn: str, *, setup: bool = False
) -> AsyncIterator[AsyncPostgresSaver]:
    """``dsn`` is a plain libpq URL (``postgresql://...``), not the SQLAlchemy ``+asyncpg`` form."""
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        if setup:
            await saver.setup()
        yield saver


__all__ = ["postgres_checkpointer"]
