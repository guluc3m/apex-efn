"""Ranking profiles (contract route, issue #306). DEV-4 implements it; until then it answers 501."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.get("", tags=["config"])
async def list_profiles() -> None:
    raise not_implemented("listing ranking profiles is not implemented yet")
