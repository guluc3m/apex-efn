"""Gate queue endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/queue")
async def get_gate_queue() -> dict[str, str]:
    """Get human gate queue with SLAs."""
    return {"status": "not_implemented"}
