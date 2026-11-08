"""Onboarding endpoints (owner: DEV-4, D4-07)."""

from fastapi import APIRouter

from apex.common.errors import not_implemented

router = APIRouter()


@router.post("/sessions")
async def create_onboarding_session() -> None:
    """Start a conversational profiling session."""
    raise not_implemented()


@router.post("/{id}/financial-csv")
async def upload_financial_csv(id: str) -> None:
    """Upload a financial CSV and return an ImportReport (never activates)."""
    raise not_implemented()


@router.post("/{id}/financial-csv/activate")
async def activate_financial_snapshot(id: str) -> None:
    """Activate a financial snapshot. Requires a signed decision."""
    raise not_implemented()
