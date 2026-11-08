"""Sourcing request endpoints (owner: DEV-4, D4-08)."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.post("")
async def create_sourcing_request() -> None:
    """Create a sourcing request from natural language."""
    raise not_implemented()
