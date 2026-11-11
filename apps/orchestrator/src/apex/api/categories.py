"""Category suggestions (contract route, issue #378). DEV-4 implements it; until then it answers 501."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.get("", tags=["config"])
async def list_categories() -> None:
    raise not_implemented("listing categories is not implemented yet")
