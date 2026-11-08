"""Sourcing request endpoints (owner: DEV-4, D4-08).

``POST /v1/sourcing-requests`` turns free text into a structured request. The LLM drafts it; code owns the
ids, the clock, the config version and the validation. The response echoes ``missing_fields`` so the UI can
ask for what the buyer did not say instead of inventing it.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from apex.agents.sourcing import SourcingRequest
from apex.agents.sourcing_service import SourcingService
from apex.common.clock import Clock, get_clock
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_tenant_id
from apex.llm.structured import StructuredOutputError

router = APIRouter()


class SourcingRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=8000, description="The need in natural language")
    base_currency: str = Field(default="EUR", pattern="^(EUR|USD|CNY)$")
    today: date | None = Field(
        default=None,
        description="Reference date for relative deadlines; defaults to the server clock",
    )


class QuantityTierOut(BaseModel):
    min_quantity: int


class SourcingRequestOut(BaseModel):
    id: str
    tenant_id: str
    spec: str
    quantity_tiers: list[QuantityTierOut]
    deadline: date | None
    deadline_text: str | None
    destination_country: str | None
    certifications: list[str]
    budget_text: str | None
    missing_fields: list[str]
    created_at: str
    config_version: str

    @classmethod
    def of(cls, request: SourcingRequest) -> SourcingRequestOut:
        return cls(
            id=request.id,
            tenant_id=request.tenant_id,
            spec=request.spec,
            quantity_tiers=[
                QuantityTierOut(min_quantity=t.min_quantity) for t in request.quantity_tiers
            ],
            deadline=request.deadline,
            deadline_text=request.deadline_text,
            destination_country=request.destination_country,
            certifications=request.certifications,
            budget_text=request.budget_text,
            missing_fields=request.missing_fields,
            created_at=request.created_at.isoformat(),
            config_version=request.config_version,
        )


def get_sourcing_service() -> SourcingService:
    """Overridable dependency. The default refuses: no LLM gateway is wired into the app yet."""
    raise not_implemented(
        "sourcing needs an LLM gateway; wire SourcingService in the app (D4-04 + D4-03 config)"
    )


@router.post(
    "",
    response_model=SourcingRequestOut,
    status_code=status.HTTP_201_CREATED,
    tags=["sourcing"],
)
async def create_sourcing_request(
    body: SourcingRequestIn,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> SourcingRequestOut:
    """Normalise a purchase need. Never invents a quantity, deadline or budget: absent fields stay null."""
    try:
        request = await service.create_request(
            tenant_id=tenant_id,
            text=body.text,
            base_currency=body.base_currency,
            today=body.today or clock.now().date(),
        )
    except StructuredOutputError as exc:
        raise Problem(
            502,
            "Model output unusable",
            detail="the intake model did not return a valid sourcing request",
            reason="structured_output_failed",
        ) from exc
    return SourcingRequestOut.of(request)


__all__ = ["get_sourcing_service", "router"]
