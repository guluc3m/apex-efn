"""Seller endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/{seller_id}/confidence")
async def get_seller_confidence(seller_id: str) -> dict[str, str]:
    """Get seller confidence score, band, signals and flags."""
    return {"seller_id": seller_id, "status": "not_implemented"}


@router.post("/{seller_id}/confidence/recompute")
async def recompute_seller_confidence(seller_id: str) -> dict[str, str]:
    """Force recomputation of seller confidence."""
    return {"seller_id": seller_id, "status": "not_implemented"}
