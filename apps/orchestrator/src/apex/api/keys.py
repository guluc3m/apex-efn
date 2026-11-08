"""Signing key endpoints (owner: DEV-2, D2-07). Bootstrap stub created by DEV-4."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.get("/me")
async def list_my_keys() -> None:
    """The caller's public keys."""
    raise not_implemented()


@router.post("/me")
async def register_my_key() -> None:
    """Register a new public key."""
    raise not_implemented()


@router.post("/{id}/revoke")
async def revoke_key(id: str) -> None:
    """Revoke a key (signed decision, immediate reauth)."""
    raise not_implemented()
