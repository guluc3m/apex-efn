"""Tenant configuration endpoints (owner: DEV-4, D4-03). Paths outside §8: pending a contract PR."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.get("/effective")
async def get_effective_config() -> None:
    """Effective config for the caller's tenant, with config_version."""
    raise not_implemented()


@router.post("/proposals")
async def propose_config_change() -> None:
    """Propose a config change. Applying it is a signed decision."""
    raise not_implemented()
