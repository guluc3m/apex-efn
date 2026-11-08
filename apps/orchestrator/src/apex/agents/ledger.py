"""In-memory effect ledger for tests and local runs (see ``EffectLedger``)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


class InMemoryEffectLedger:
    def __init__(self) -> None:
        self._results: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def once(self, key: str, effect: Callable[[], Awaitable[T]]) -> T:
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key in self._results:
                cached: T = self._results[key]
                return cached
            result = await effect()
            self._results[key] = result
            return result

    def keys(self) -> list[str]:
        return sorted(self._results)


__all__ = ["InMemoryEffectLedger"]
