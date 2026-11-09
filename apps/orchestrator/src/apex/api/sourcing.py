"""Sourcing request endpoints (owner: DEV-4, D4-08).

Shapes come from ``contracts/openapi.yaml`` (``CreateSourcingRequest`` → ``SourcingRequest``); the router
does not define DTOs of its own (spec §5.1). The LLM drafts the normalised need from the free text; code owns
the ids, the clock, the config version and the validation, and stores the result so ``POST /v1/missions`` can
reference it by id.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from apex.agents.request_store import SourcingRequestStore
from apex.agents.sourcing import SourcingRequest
from apex.agents.sourcing_service import SourcingService
from apex.api.contract_map import to_contract_request
from apex.common.clock import Clock, get_clock
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_tenant_id
from apex.contracts.generated.models import CreateSourcingRequest
from apex.contracts.generated.models import SourcingRequest as ContractRequest
from apex.llm.budget import TokenBudgetExceeded
from apex.llm.resilience import AllEndpointsUnavailableError
from apex.llm.structured import StructuredOutputError
from apex.llm.transport import LLMHTTPError, LLMTransportError

router = APIRouter()


def get_sourcing_service() -> SourcingService:
    """Overridable dependency. The default refuses: no LLM gateway is wired into the app yet."""
    raise not_implemented(
        "sourcing needs an LLM gateway; wire SourcingService in the app (D4-04 + D4-03 config)"
    )


def get_request_store() -> SourcingRequestStore:
    """Overridable dependency: the store that lets a mission reference a request by id."""
    raise not_implemented("the sourcing request store is not wired into the app")


@router.post(
    "",
    response_model=ContractRequest,
    status_code=status.HTTP_201_CREATED,
    tags=["sourcing"],
)
async def create_sourcing_request(
    body: CreateSourcingRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
    store: Annotated[SourcingRequestStore, Depends(get_request_store)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ContractRequest:
    """Normalise a purchase need. Never invents a quantity, deadline or budget: absent fields stay null."""
    try:
        request: SourcingRequest = await service.create_request(
            tenant_id=tenant_id,
            text=body.natural_language,
            base_currency="EUR",
            today=clock.now().date(),
            delivery_country=body.delivery_country,
            target_delivery_date=body.target_delivery_date,
        )
    except StructuredOutputError as exc:
        raise Problem(
            502,
            "Model output unusable",
            detail="the intake model did not return a valid sourcing request",
            reason="structured_output_failed",
        ) from exc
    except (AllEndpointsUnavailableError, LLMTransportError, LLMHTTPError) as exc:
        raise Problem(
            502,
            "Model endpoint unavailable",
            detail=f"the extractor endpoint could not be reached: {_llm_detail(exc)}",
            reason="llm_unavailable",
        ) from exc
    except TokenBudgetExceeded as exc:
        raise Problem(
            429, "Token budget exhausted", detail=exc.warning, reason="token_budget_exhausted"
        ) from exc
    await store.add(request)
    return to_contract_request(request, max_budget=body.max_budget)


def _llm_detail(exc: Exception) -> str:
    """A short, safe description of an LLM failure. Never the prompt, never a credential."""
    causes = getattr(exc, "causes", None)
    if causes:
        return str(causes)
    return f"{type(exc).__name__}: {exc}"


__all__ = ["get_request_store", "get_sourcing_service", "router"]
