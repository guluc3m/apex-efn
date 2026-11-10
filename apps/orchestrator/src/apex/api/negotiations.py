"""Negotiation control endpoints (owner: DEV-5, D5-08).

- ``POST /v1/negotiations/{id}/takeover``  a human takes the chat; the agent stops sending.
- ``POST /v1/negotiations/{id}/resume``    control returns to the agent.
- ``POST /v1/negotiations/{id}/abort``     stop cleanly; terminal and idempotent.

Every response is the contract's ``Negotiation`` view (:func:`apex.negotiation.api.to_contract`). Refusals
are RFC 9457 problems with a closed ``reason``:

- ``not_found``            the id does not exist for this tenant (another tenant's is indistinguishable).
- ``terminal``             the negotiation already finished; it cannot be taken over or resumed.
- ``not_in_human_control`` ``resume`` without a previous ``takeover``.

Authorization is provisional: the tenant comes from the dev-only header until DEV-1's D1-05 lands, and the
role check (``buyer|admin|owner``) belongs to the same task. The contract already declares the 403 for it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_tenant_id
from apex.contracts.generated.models import Negotiation, NegotiationControlRequest
from apex.negotiation.api import NegotiationControlService, build_default_control, to_contract
from apex.negotiation.engine import NegotiationError

router = APIRouter()

_control: NegotiationControlService = build_default_control()


def get_negotiation_control() -> NegotiationControlService:
    """Overridable dependency.

    Defaults to an in-process engine over an in-memory store, which serves the control calls but cannot see
    negotiations created by another process. When DEV-4 wires the mission graph, it injects the shared
    engine here (or in ``apex.wiring``), exactly like the gate router's dependency.
    """
    return _control


#: Closed error code -> (HTTP status, problem title).
_ERRORS: dict[str, tuple[int, str]] = {
    "not_found": (404, "Not Found"),
    "terminal": (409, "Conflict"),
    "not_in_human_control": (409, "Conflict"),
    "seller_busy": (409, "Conflict"),
}


def _problem(exc: NegotiationError) -> Problem:
    status, title = _ERRORS.get(exc.code, (409, "Conflict"))
    return Problem(status, title, detail=str(exc), reason=exc.code)


@router.post("/{id}/takeover", response_model=Negotiation)
async def takeover_negotiation(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    control: Annotated[NegotiationControlService, Depends(get_negotiation_control)],
    body: NegotiationControlRequest | None = None,
) -> Negotiation:
    """A human takes control of the chat. Any pending draft is dropped and the agent stops sending."""
    del body  # The contract allows a reason on every control call; takeover records none.
    try:
        session = await control.takeover(id, tenant_id=tenant_id)
    except NegotiationError as exc:
        raise _problem(exc) from exc
    return to_contract(session)


@router.post("/{id}/resume", response_model=Negotiation)
async def resume_negotiation(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    control: Annotated[NegotiationControlService, Depends(get_negotiation_control)],
    body: NegotiationControlRequest | None = None,
) -> Negotiation:
    """Return control to the agent. Only valid after a ``takeover``."""
    del body
    try:
        session = await control.resume(id, tenant_id=tenant_id)
    except NegotiationError as exc:
        raise _problem(exc) from exc
    return to_contract(session)


@router.post("/{id}/abort", response_model=Negotiation)
async def abort_negotiation(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    control: Annotated[NegotiationControlService, Depends(get_negotiation_control)],
    body: NegotiationControlRequest | None = None,
) -> Negotiation:
    """Stop the negotiation cleanly. The first call records the reason; later calls keep it."""
    try:
        session = await control.abort(id, tenant_id=tenant_id, reason=body.reason if body else None)
    except NegotiationError as exc:
        raise _problem(exc) from exc
    return to_contract(session)


# D5-07c contract: these five operations are declared in contracts/openapi.yaml and are implemented in
# the D5-07c branch. They answer 501 until then, like every other unfinished route in this app.


@router.get("/{id}")
async def get_negotiation(id: str) -> None:
    """State of a negotiation, including the draft waiting for a human."""
    raise not_implemented()


@router.get("/{id}/messages")
async def list_negotiation_messages(id: str) -> None:
    """Transcript of the chat with the seller, oldest first."""
    raise not_implemented()


@router.post("/{id}/messages")
async def send_human_negotiation_message(id: str) -> None:
    """A human holding the chat writes to the seller."""
    raise not_implemented()


@router.post("/{id}/approve")
async def approve_negotiation_draft(id: str) -> None:
    """A human approves the drafted message and it is sent to the seller."""
    raise not_implemented()


@router.post("/{id}/reject")
async def reject_negotiation_draft(id: str) -> None:
    """A human rejects the drafted message; the deterministic template is sent instead."""
    raise not_implemented()
