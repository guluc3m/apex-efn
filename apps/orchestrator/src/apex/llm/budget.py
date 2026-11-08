"""Hard per-mission token budget (criterion 28, spec §5.6).

Flow per call: ``reserve(estimate)`` before the request (prompt estimate + ``max_output``) and
``commit(actual)`` after it, which releases the reservation and records actual usage. When a reservation
would exceed the hard limit, the configured policy applies:

- ``degrade``: the caller switches to the configured cheaper fallback endpoint (decided by the gateway).
- ``stop``: :class:`TokenBudgetExceeded` is raised, carrying a user-facing warning.

The gateway never silently continues past the hard limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class BudgetPolicy(StrEnum):
    DEGRADE = "degrade"
    STOP = "stop"


class TokenBudgetExceeded(Exception):
    """Raised by the ``stop`` policy. ``warning`` is safe to show to the user."""

    def __init__(self, mission_id: str, limit: int, requested: int, used: int) -> None:
        self.mission_id = mission_id
        self.limit = limit
        self.requested = requested
        self.used = used
        self.warning = (
            f"El presupuesto de tokens de la misión {mission_id} se ha agotado "
            f"({used} de {limit} tokens usados). La misión se ha detenido."
        )
        super().__init__(f"token budget exceeded for mission {mission_id}")


@dataclass
class BudgetState:
    limit: int
    committed: int = 0
    reserved: int = 0

    @property
    def headroom(self) -> int:
        return self.limit - self.committed - self.reserved


class BudgetStore(Protocol):
    """Persistence for budget ledgers. Redis implementation arrives later."""

    def get_or_create(self, mission_id: str, limit: int) -> BudgetState: ...


@dataclass
class InMemoryBudgetStore:
    _states: dict[str, BudgetState] = field(default_factory=dict)

    def get_or_create(self, mission_id: str, limit: int) -> BudgetState:
        state = self._states.get(mission_id)
        if state is None:
            state = BudgetState(limit=limit)
            self._states[mission_id] = state
        return state


class TokenBudget:
    """Ledger for one or more missions. ``reserve`` returns False when the policy is ``degrade``."""

    def __init__(
        self,
        store: BudgetStore,
        *,
        mission_limit: int,
        policy: BudgetPolicy = BudgetPolicy.STOP,
    ) -> None:
        if mission_limit <= 0:
            raise ValueError("mission_limit must be positive")
        self._store = store
        self._limit = mission_limit
        self.policy = policy

    def state(self, mission_id: str) -> BudgetState:
        return self._store.get_or_create(mission_id, self._limit)

    def reserve(self, mission_id: str, estimate: int) -> bool:
        """Reserve ``estimate`` tokens. Returns True if granted.

        On overflow: ``stop`` raises :class:`TokenBudgetExceeded`; ``degrade`` returns False so the
        caller can switch to the cheaper fallback endpoint (and then reserve for that endpoint).
        """
        if estimate < 0:
            raise ValueError("estimate must be non-negative")
        state = self.state(mission_id)
        if estimate <= state.headroom:
            state.reserved += estimate
            return True
        if self.policy is BudgetPolicy.STOP:
            raise TokenBudgetExceeded(mission_id, state.limit, estimate, state.committed)
        return False

    def commit(self, mission_id: str, reserved: int, actual: int) -> None:
        """Release a reservation and record the actual tokens used."""
        if reserved < 0 or actual < 0:
            raise ValueError("token counts must be non-negative")
        state = self.state(mission_id)
        state.reserved = max(0, state.reserved - reserved)
        state.committed += actual

    def release(self, mission_id: str, reserved: int) -> None:
        """Release a reservation without charging (call failed before producing usage)."""
        state = self.state(mission_id)
        state.reserved = max(0, state.reserved - reserved)


def estimate_prompt_tokens(messages: list[dict[str, str]]) -> int:
    """Conservative prompt estimate: ~1 token per 3 characters plus per-message overhead."""
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    return chars // 3 + 4 * len(messages) + 1


__all__ = [
    "BudgetPolicy",
    "BudgetState",
    "BudgetStore",
    "InMemoryBudgetStore",
    "TokenBudget",
    "TokenBudgetExceeded",
    "estimate_prompt_tokens",
]
