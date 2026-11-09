"""Gate queue endpoints (owner: DEV-4, D4-11).

``GET /v1/gate/queue`` lists what is waiting for a human, oldest SLA first.
``POST /v1/gate/queue/{id}/actions`` creates the signed decision for ``unblock`` or ``override_discard``.

Every refusal is a problem+json with a closed ``reason`` and the list of blocking reasons, so the UI can
explain why an action is unavailable instead of hiding it (criterion 16).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from apex.agents.gate import (
    ActionBlocked,
    GateAgent,
    GateQueueItem,
    QueueAction,
)
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_roles, get_tenant_id

router = APIRouter()


class GateItemOut(BaseModel):
    id: str
    mission_id: str
    offer_id: str
    causes: list[str]
    created_at: str
    sla_due_at: str
    status: str
    resolution: str | None
    decision_id: str | None

    @classmethod
    def of(cls, item: GateQueueItem) -> GateItemOut:
        return cls(
            id=item.id,
            mission_id=item.mission_id,
            offer_id=item.offer_id,
            causes=[c.value for c in item.causes],
            created_at=item.created_at.isoformat(),
            sla_due_at=item.sla_due_at.isoformat(),
            status=item.status.value,
            resolution=item.resolution.value if item.resolution else None,
            decision_id=item.decision_id,
        )


class GateQueueOut(BaseModel):
    items: list[GateItemOut]


class QueueActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: QueueAction
    comment: str | None = Field(default=None, max_length=2000)


class DecisionAcceptedOut(BaseModel):
    decision_id: str
    status: str = "pending_signature"


def get_gate_agent() -> GateAgent:
    """Overridable dependency. The default refuses: signing and the engines are not wired yet."""
    raise not_implemented(
        "the gate queue needs signing (D2-09) and the engines; wire GateAgent in the app"
    )


@router.get("/queue", response_model=GateQueueOut, tags=["gate"])
async def get_gate_queue(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    agent: Annotated[GateAgent, Depends(get_gate_agent)],
) -> GateQueueOut:
    """Open items, most urgent first."""
    items = await agent.list_open(tenant_id=tenant_id)
    return GateQueueOut(items=[GateItemOut.of(i) for i in items])


@router.post(
    "/queue/{id}/actions",
    response_model=DecisionAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["gate"],
)
async def gate_queue_action(
    id: str,
    body: QueueActionIn,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    roles: Annotated[tuple[str, ...], Depends(get_roles)],
    agent: Annotated[GateAgent, Depends(get_gate_agent)],
) -> DecisionAcceptedOut:
    """``unblock`` or ``override_discard``. Both are signed decisions; nothing changes until signed."""
    try:
        decision = await agent.decide_queue_action(
            tenant_id=tenant_id,
            item_id=id,
            action=body.action,
            roles=roles,
            comment=body.comment,
        )
    except ActionBlocked as exc:
        raise _blocked(exc) from exc
    return DecisionAcceptedOut(decision_id=decision.id)


def _blocked(exc: ActionBlocked) -> Problem:
    reasons = [b.reason.value for b in exc.blocked]
    return Problem(
        409,
        "Action blocked",
        detail="; ".join(f"{b.action}: {b.detail}" for b in exc.blocked),
        reason=reasons[0] if reasons else "blocked",
        blocked=[b.model_dump(mode="json") for b in exc.blocked],
    )


__all__ = ["get_gate_agent", "router"]
