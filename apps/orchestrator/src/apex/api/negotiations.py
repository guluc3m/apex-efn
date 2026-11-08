"""Negotiation control endpoints (owner: DEV-5, D5-08). Bootstrap stubs created by DEV-4."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.post("/{id}/takeover")
async def takeover_negotiation(id: str) -> None:
    """Human takes control of a negotiation."""
    raise not_implemented()


@router.post("/{id}/resume")
async def resume_negotiation(id: str) -> None:
    """Return control to the agent."""
    raise not_implemented()


@router.post("/{id}/abort")
async def abort_negotiation(id: str) -> None:
    """Stop a negotiation cleanly."""
    raise not_implemented()
