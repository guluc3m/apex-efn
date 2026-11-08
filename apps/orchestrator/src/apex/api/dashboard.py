"""Dashboard endpoints (owner: DEV-4, D4-11)."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.get("/deals")
async def list_deals() -> None:
    """Final deals with bands, verdicts and signature status."""
    raise not_implemented()


@router.post("/deals/{id}/actions")
async def deal_action(id: str) -> None:
    """follow | hold | discard | renegotiate | takeover (signed decisions)."""
    raise not_implemented()
