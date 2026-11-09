"""Column types that SQLAlchemy does not ship (D2-05)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import Enum
from typing import Any

from sqlalchemy.engine import Dialect
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType[list[float]]):
    """pgvector ``vector`` without a fixed dimension (ADR-205). Values travel in the text format ``[1,2,3]``,
    which every driver can send and read without registering a codec."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "vector"

    def bind_processor(self, dialect: Dialect) -> Callable[[Sequence[float] | None], str | None]:
        def process(value: Sequence[float] | None) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(repr(float(v)) for v in value) + "]"

        return process

    def result_processor(
        self, dialect: Dialect, coltype: object
    ) -> Callable[[Any], list[float] | None]:
        def process(value: Any) -> list[float] | None:
            if value is None:
                return None
            if isinstance(value, str):
                body = value.strip().removeprefix("[").removesuffix("]")
                return [float(v) for v in body.split(",")] if body else []
            return [float(v) for v in value]

        return process


def enum_values(enum_cls: type[Enum]) -> list[str]:
    """Store enum **values** (the Postgres labels), not member names, in ``ENUM(..., values_callable=...)``."""
    return [str(member.value) for member in enum_cls]


__all__ = ["Vector", "enum_values"]
