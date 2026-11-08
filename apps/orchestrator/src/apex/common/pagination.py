"""Opaque cursor pagination (spec §8: paginación por cursor).

A ``Cursor`` wraps a JSON object with the keyset position, encoded as base64url without padding.
Clients treat it as an opaque string. Decoding validates shape and size; invalid cursors raise
``Problem`` 400 so they never reach a query.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from apex.common.errors import Problem

MAX_CURSOR_CHARS = 512


class Cursor:
    """Opaque keyset position. Construct with ``Cursor.encode`` and read with ``Cursor.decode``."""

    @staticmethod
    def encode(position: Mapping[str, Any]) -> str:
        raw = json.dumps(dict(position), sort_keys=True, separators=(",", ":"), default=str)
        return base64.urlsafe_b64encode(raw.encode("utf-8")).rstrip(b"=").decode("ascii")

    @staticmethod
    def decode(token: str) -> dict[str, Any]:
        if not token or len(token) > MAX_CURSOR_CHARS:
            raise _invalid_cursor()
        padded = token + "=" * (-len(token) % 4)
        try:
            raw = base64.urlsafe_b64decode(padded.encode("ascii"))
            data = json.loads(raw.decode("utf-8"))
        except (binascii.Error, UnicodeError, ValueError):
            raise _invalid_cursor() from None
        if not isinstance(data, dict):
            raise _invalid_cursor()
        return data


def _invalid_cursor() -> Problem:
    return Problem(400, "Invalid cursor", detail="The pagination cursor is malformed.")


def parse_limit(raw: int | None, *, default: int, maximum: int) -> int:
    """Validate a page size. ``default`` and ``maximum`` come from settings, never hardcoded."""
    if maximum < 1:
        raise ValueError("maximum page size must be >= 1")
    if default < 1 or default > maximum:
        raise ValueError("default page size must be within [1, maximum]")
    if raw is None:
        return default
    if raw < 1 or raw > maximum:
        raise Problem(
            422,
            "Invalid page size",
            detail=f"limit must be between 1 and {maximum}.",
        )
    return raw


class Page[T](BaseModel):
    """A page of results. ``next_cursor`` is None on the last page."""

    items: list[T] = Field(default_factory=list)
    next_cursor: str | None = None


__all__ = ["Cursor", "Page", "parse_limit"]
