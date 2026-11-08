"""Seller endpoints (owner: DEV-4, D4-10)."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.get("/{id}/confidence")
async def get_seller_confidence(id: str) -> None:
    """Seller confidence: score, band, signals, flags and history."""
    raise not_implemented()


@router.post("/{id}/confidence/recompute")
async def recompute_seller_confidence(id: str) -> None:
    """Force a recomputation (audited)."""
    raise not_implemented()
