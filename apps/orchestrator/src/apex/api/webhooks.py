"""Platform webhooks (owner: DEV-5, D5-11). Bootstrap stub created by DEV-4."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.post("/platforms/{platform}")
async def receive_platform_webhook(platform: str) -> None:
    """Receive a platform webhook."""
    raise not_implemented()
