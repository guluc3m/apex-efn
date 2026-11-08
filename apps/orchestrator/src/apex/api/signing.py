"""Signing session endpoints (owner: DEV-2, D2-08). Bootstrap stub created by DEV-4."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.post("")
async def open_signing_session() -> None:
    """Open a 15-minute fixed signing window (step-up auth)."""
    raise not_implemented()


@router.get("/{id}")
async def get_signing_session(id: str) -> None:
    """Session state and remaining time."""
    raise not_implemented()


@router.delete("/{id}")
async def close_signing_session(id: str) -> None:
    """Explicitly close a signing session."""
    raise not_implemented()
