"""Human gate queue endpoints (owner: DEV-4, D4-11)."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.get("/queue")
async def list_gate_queue() -> None:
    """Gate queue with SLAs."""
    raise not_implemented()


@router.post("/queue/{id}/actions")
async def gate_queue_action(id: str) -> None:
    """unblock | override_discard (signed decisions)."""
    raise not_implemented()
