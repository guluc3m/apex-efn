"""Negotiation endpoints (owner: DEV-5): human controls, transcript and the approval loop.

- ``POST /v1/negotiations/{id}/takeover``  a human takes the chat; the agent stops sending.
- ``POST /v1/negotiations/{id}/resume``    control returns to the agent.
- ``POST /v1/negotiations/{id}/abort``     stop cleanly; terminal and idempotent.
- ``GET  /v1/negotiations/{id}``           state, including the draft waiting for a human.
- ``GET  /v1/negotiations/{id}/messages``  transcript, oldest first, cursor-paginated.
- ``POST /v1/negotiations/{id}/messages``  a human holding the chat writes to the seller.
- ``POST /v1/negotiations/{id}/approve``   approve the drafted message and send it.
- ``POST /v1/negotiations/{id}/reject``    discard the draft and send the playbook template instead.

Every negotiation response is the contract's ``Negotiation`` view (:func:`apex.negotiation.api.to_contract`).
Refusals are RFC 9457 problems with a closed ``reason``:

- ``not_found``             the id does not exist for this tenant (another tenant's is indistinguishable).
- ``terminal``              the negotiation already finished; it cannot be taken over, resumed or written to.
- ``not_in_human_control``  ``resume`` or a human message without a previous ``takeover``.
- ``human_in_control``      approving a draft while a person holds the chat; resume first.
- ``draft_not_pending``     the draft id is unknown, already sent, or the negotiation is finished.
- ``draft_superseded``      new seller messages arrived; the draft is stale, review the new state.
- ``rate_limited``          the configured hourly cap (per account or per seller) is reached.
- ``empty_message`` / ``message_too_long``  the human text breaks the configured limits (422).

Authorization is provisional: the tenant comes from the dev-only header until DEV-1's D1-05 lands, and the
role check (``buyer|admin|owner``) belongs to the same task. The contract already declares the 403 for it.
The approver/author identity is provisional in the same way; see :func:`get_actor_id`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from apex.common.errors import Problem
from apex.common.tenant import get_tenant_id
from apex.contracts.generated.models import (
    Negotiation,
    NegotiationControlRequest,
    NegotiationDraftRef,
    NegotiationHumanMessage,
    NegotiationMessage,
    NegotiationMessagePage,
)
from apex.negotiation.api import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    NegotiationControlService,
    build_default_control,
    to_contract,
    to_message,
    transcript_page,
)
from apex.negotiation.engine import NegotiationError

router = APIRouter()

_control: NegotiationControlService = build_default_control()

ACTOR_HEADER = "X-Actor-Id"
"""Header carrying who approves or writes, until DEV-1's D1-05 supplies the authenticated principal."""

LOCAL_ACTOR = "local-user"
"""Recorded as approver/author when the caller sends no actor. Replaced by the principal in D1-05."""


def get_negotiation_control() -> NegotiationControlService:
    """Overridable dependency.

    Defaults to an in-process engine over an in-memory store, which serves every call in this router but
    cannot see negotiations created by another process. When DEV-4 wires the mission graph, it injects the
    shared engine here (or in ``apex.wiring``), exactly like the gate router's dependency.
    """
    return _control


def get_actor_id(
    x_actor_id: Annotated[str | None, Header(alias=ACTOR_HEADER)] = None,
) -> str:
    """Who approved the draft or wrote the message.

    Temporary, like the tenant header: there is no authenticated principal until DEV-1's D1-05 lands, so the
    caller states the actor and a fixed local identity is used when it does not. D1-05 replaces this
    dependency with ``current_principal().user_id``; nothing else in this file changes.
    """
    return x_actor_id or LOCAL_ACTOR


#: Closed error code -> (HTTP status, problem title).
_ERRORS: dict[str, tuple[int, str]] = {
    "not_found": (404, "Not Found"),
    "terminal": (409, "Conflict"),
    "not_in_human_control": (409, "Conflict"),
    "seller_busy": (409, "Conflict"),
    "human_in_control": (409, "Conflict"),
    "draft_not_pending": (409, "Conflict"),
    "draft_superseded": (409, "Conflict"),
    "rate_limited": (409, "Conflict"),
    "no_chat": (409, "Conflict"),
    "empty_message": (422, "Unprocessable Entity"),
    "message_too_long": (422, "Unprocessable Entity"),
}


def _problem(exc: NegotiationError) -> Problem:
    status, title = _ERRORS.get(exc.code, (409, "Conflict"))
    if status == 422:
        # The contract's validation problem carries the offending field, not just a message.
        return Problem(
            status,
            title,
            detail=str(exc),
            reason=exc.code,
            errors=[{"field": "content", "code": exc.code, "message": str(exc)}],
        )
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


@router.get("/{id}", response_model=Negotiation)
async def get_negotiation(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    control: Annotated[NegotiationControlService, Depends(get_negotiation_control)],
) -> Negotiation:
    """State of a negotiation, including the draft waiting for a human."""
    try:
        session = await control.get(id, tenant_id=tenant_id)
    except NegotiationError as exc:
        raise _problem(exc) from exc
    return to_contract(session)


@router.get("/{id}/messages", response_model=NegotiationMessagePage)
async def list_negotiation_messages(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    control: Annotated[NegotiationControlService, Depends(get_negotiation_control)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> NegotiationMessagePage:
    """Transcript of the chat with the seller, oldest first.

    Pending drafts are not here: they are ``pending_draft`` on the negotiation until a human decides.
    """
    try:
        session = await control.get(id, tenant_id=tenant_id)
    except NegotiationError as exc:
        raise _problem(exc) from exc
    try:
        items, next_cursor = transcript_page(session, cursor=cursor, limit=limit)
    except ValueError as exc:
        raise Problem(400, "Bad Request", detail=str(exc), reason="invalid_cursor") from exc
    return NegotiationMessagePage(items=items, next_cursor=next_cursor)


@router.post("/{id}/messages", response_model=NegotiationMessage, status_code=201)
async def send_human_negotiation_message(
    id: str,
    body: NegotiationHumanMessage,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    control: Annotated[NegotiationControlService, Depends(get_negotiation_control)],
    actor: Annotated[str, Depends(get_actor_id)],
) -> NegotiationMessage:
    """A human holding the chat writes to the seller. The text is sent as written."""
    try:
        session = await control.send_human(id, body.content, author=actor, tenant_id=tenant_id)
    except NegotiationError as exc:
        raise _problem(exc) from exc
    return to_message(session, session.transcript[-1])


@router.post("/{id}/approve", response_model=Negotiation)
async def approve_negotiation_draft(
    id: str,
    body: NegotiationDraftRef,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    control: Annotated[NegotiationControlService, Depends(get_negotiation_control)],
    actor: Annotated[str, Depends(get_actor_id)],
) -> Negotiation:
    """A human approves the drafted message; it is sent, and the negotiation moves on."""
    try:
        session = await control.approve(id, body.draft_id, approver=actor, tenant_id=tenant_id)
    except NegotiationError as exc:
        raise _problem(exc) from exc
    return to_contract(session)


@router.post("/{id}/reject", response_model=Negotiation)
async def reject_negotiation_draft(
    id: str,
    body: NegotiationDraftRef,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    control: Annotated[NegotiationControlService, Depends(get_negotiation_control)],
) -> Negotiation:
    """A human rejects the drafted message; the deterministic playbook template is sent instead."""
    try:
        session = await control.reject(id, body.draft_id, tenant_id=tenant_id)
    except NegotiationError as exc:
        raise _problem(exc) from exc
    return to_contract(session)
