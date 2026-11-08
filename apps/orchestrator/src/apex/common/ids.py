"""Sortable identifiers (ULID-like, 128-bit).

Layout: 48-bit millisecond timestamp, then 80 random bits, rendered as 26 Crockford base32
characters. Lexicographic order matches creation order within a millisecond resolution. Time comes
from the injected ``Clock`` and randomness from an injectable ``RandomSource``, so tests are
deterministic. Production uses ``secrets`` randomness; nothing here is a business default.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Protocol

from apex.common.clock import Clock

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TIMESTAMP_MAX = (1 << 48) - 1
_RANDOM_BITS = 80


class RandomSource(Protocol):
    """Returns ``n`` random bits as a non-negative integer (``n`` <= 128)."""

    def __call__(self, n_bits: int) -> int: ...


def system_random_bits(n_bits: int) -> int:
    """Cryptographically secure randomness (production)."""
    return secrets.randbits(n_bits)


def _encode(value: int) -> str:
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


class IdGenerator:
    """Creates sortable ids. Inject ``clock`` and ``random_bits`` for deterministic tests."""

    def __init__(self, clock: Clock, random_bits: RandomSource = system_random_bits) -> None:
        self._clock = clock
        self._random_bits: Callable[[int], int] = random_bits

    def new_id(self) -> str:
        millis = int(self._clock.now().timestamp() * 1000)
        if not 0 <= millis <= _TIMESTAMP_MAX:
            raise ValueError("clock is outside the representable id time range")
        value = (millis << _RANDOM_BITS) | self._random_bits(_RANDOM_BITS)
        return _encode(value)


__all__ = ["IdGenerator", "RandomSource", "system_random_bits"]
