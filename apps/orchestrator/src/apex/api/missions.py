"""Mission endpoints (owner: DEV-4, D4-08 / D4-10 / D4-12)."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.post("")
async def create_mission() -> None:
    """Launch a sourcing mission."""
    raise not_implemented()


@router.get("/{id}")
async def get_mission(id: str) -> None:
    """Get mission state."""
    raise not_implemented()


@router.get("/{id}/events")
async def stream_mission_events(id: str) -> None:
    """SSE stream of mission progress and live transcript."""
    raise not_implemented()


@router.get("/{id}/offers")
async def list_mission_offers(id: str) -> None:
    """Offers with SellerConfidence, PriceSanityCheck and FinancialFit."""
    raise not_implemented()


@router.get("/{id}/recommendation")
async def get_mission_recommendation(id: str) -> None:
    """Explainable ranking (MCDA)."""
    raise not_implemented()
