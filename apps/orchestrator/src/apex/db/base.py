"""Declarative base for the SQLAlchemy mapping of the Prisma schema (D2-05, ADR-201, ADR-207)."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Maps tables that Prisma Migrate owns. Never call ``Base.metadata.create_all()`` or ``drop_all()``:
    DDL comes only from ``apps/web/prisma/migrations`` (ADR-201)."""


__all__ = ["Base"]
