"""In-test fakes for the tenant_config ports (ports are async)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from apex.tenant_config.ports import Decision, PendingSignature


class FixedClock:
    def __init__(self, at: datetime | None = None) -> None:
        self._at = at or datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._at


@dataclass
class FakeDecisionPort:
    """In-memory DecisionPort fake. Signing is simulated via ``sign()``."""

    decisions: dict[str, Decision] = field(default_factory=dict)
    created: list[dict[str, Any]] = field(default_factory=list)

    async def create_decision(
        self, type: str, subject_ref: str, payload: dict[str, Any]
    ) -> Decision:
        did = f"dec-{len(self.decisions) + 1}"
        decision = Decision(
            id=did, type=type, subject_ref=subject_ref, status="pending_signature", payload=payload
        )
        self.decisions[did] = decision
        self.created.append({"type": type, "subject_ref": subject_ref, "payload": payload})
        return decision

    async def require_signed(self, decision_id: str) -> Decision:
        decision = self.decisions.get(decision_id)
        if decision is None or decision.status != "signed":
            raise PendingSignature(decision_id)
        return decision

    def sign(self, decision_id: str) -> None:
        d = self.decisions[decision_id]
        self.decisions[decision_id] = Decision(
            id=d.id, type=d.type, subject_ref=d.subject_ref, status="signed", payload=d.payload
        )
