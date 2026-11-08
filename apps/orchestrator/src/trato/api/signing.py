"""Signing session endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("")
async def create_signing_session() -> dict[str, str]:
    """Open a signing session (15-minute window)."""
    return {"status": "not_implemented"}


@router.get("/{session_id}")
async def get_signing_session(session_id: str) -> dict[str, str]:
    """Get signing session status and remaining time."""
    return {"session_id": session_id, "status": "not_implemented"}


@router.delete("/{session_id}")
async def close_signing_session(session_id: str) -> dict[str, str]:
    """Explicitly close a signing session."""
    return {"session_id": session_id, "status": "not_implemented"}
