"""Dashboard endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/deals")
async def get_deals() -> dict[str, str]:
    """Get final deals for dashboard."""
    return {"status": "not_implemented"}


@router.post("/deals/{deal_id}/actions")
async def deal_action(deal_id: str) -> dict[str, str]:
    """Execute action on a deal (follow, hold, discard, renegotiate, takeover)."""
    return {"deal_id": deal_id, "status": "not_implemented"}
