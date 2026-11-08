"""Audit endpoints (owner: DEV-2, D2-10). Bootstrap stub created by DEV-4."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.get("")
async def list_audit_events() -> None:
    """Audit events (admin and compliance only)."""
    raise not_implemented()


@router.get("/verify")
async def verify_audit_chain() -> None:
    """Re-verify the full hash chain."""
    raise not_implemented()
