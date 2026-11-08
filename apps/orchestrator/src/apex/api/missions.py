"""Mission endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("")
async def create_mission() -> dict[str, str]:
    """Launch a sourcing mission."""
    return {"status": "not_implemented"}


@router.get("/{mission_id}")
async def get_mission(mission_id: str) -> dict[str, str]:
    """Get mission status."""
    return {"mission_id": mission_id, "status": "not_implemented"}


@router.get("/{mission_id}/offers")
async def get_mission_offers(mission_id: str) -> dict[str, str]:
    """Get offers for a mission."""
    return {"mission_id": mission_id, "status": "not_implemented"}


@router.get("/{mission_id}/recommendation")
async def get_recommendation(mission_id: str) -> dict[str, str]:
    """Get ranked recommendation for a mission."""
    return {"mission_id": mission_id, "status": "not_implemented"}
