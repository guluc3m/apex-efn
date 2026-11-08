"""Decision endpoints (owner: DEV-2, D2-09). Bootstrap stub created by DEV-4."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.post("")
async def create_decision() -> None:
    """Create a decision pending signature (canonical payload)."""
    raise not_implemented()


@router.post("/{id}/sign")
async def sign_decision(id: str) -> None:
    """Sign a pending decision."""
    raise not_implemented()


@router.post("/{id}/verify")
async def verify_decision(id: str) -> None:
    """Verify a decision signature."""
    raise not_implemented()
