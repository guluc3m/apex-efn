"""Mission endpoints (owner: DEV-4, D4-08 / D4-10 / D4-12).

- ``POST /v1/missions`` launches a mission from a sourcing request and plans it.
- ``GET  /v1/missions/{id}`` returns its state.
- ``GET  /v1/missions/{id}/events`` streams progress as Server-Sent Events. ``Last-Event-ID`` replays from
  the next sequence number, so a dropped connection resumes without gaps or duplicates.

``GET /{id}/offers`` and ``GET /{id}/recommendation`` belong to D4-10 and D4-12 and stay 501 until then.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from apex.agents.missions import Mission, MissionEvent, MissionStatus
from apex.agents.sourcing_service import MissionMissing, SourcingService
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_tenant_id
from apex.llm.structured import StructuredOutputError

router = APIRouter()

SSE_MEDIA_TYPE = "text/event-stream"
HEARTBEAT_SECONDS = 15.0
"""Comment lines keep proxies from closing an idle stream. No event is invented for it."""

STREAM_ENDS_AT: frozenset[MissionStatus] = frozenset(
    {MissionStatus.PLANNED, MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED}
)
"""Statuses after which this service emits nothing more for the mission.

``PLANNED`` is one of them on purpose: planning is the last step D4-08 performs, so a stream opened on a
planned mission would otherwise wait for a heartbeat forever. The client reconnects with ``Last-Event-ID``
when D4-09 starts running the mission, which loses nothing."""


class MissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourcing_request_id: str = Field(min_length=1)
    spec: str = Field(
        min_length=1, description="The normalised need, echoed from the sourcing request"
    )
    quantity_tiers: list[int] = Field(default_factory=list, description="Minimum quantities")
    deadline: str | None = None
    destination_country: str | None = None
    certifications: list[str] = Field(default_factory=list)
    budget_text: str | None = None
    config_version: str | None = Field(
        default=None, description="Ignored: the config version always comes from tenant config"
    )


class MissionOut(BaseModel):
    id: str
    tenant_id: str
    sourcing_request_id: str
    status: str
    config_version: str
    created_at: str
    updated_at: str
    steps: list[dict[str, Any]]
    rejected_steps: list[dict[str, Any]]
    failure_reason: str | None

    @classmethod
    def of(cls, mission: Mission) -> MissionOut:
        plan = mission.plan
        return cls(
            id=mission.id,
            tenant_id=mission.tenant_id,
            sourcing_request_id=mission.sourcing_request_id,
            status=mission.status.value,
            config_version=mission.config_version,
            created_at=mission.created_at.isoformat(),
            updated_at=mission.updated_at.isoformat(),
            steps=[s.model_dump(mode="json") for s in plan.steps] if plan else [],
            rejected_steps=[r.model_dump(mode="json") for r in plan.rejected_steps] if plan else [],
            failure_reason=mission.failure_reason,
        )


def get_sourcing_service() -> SourcingService:
    """Overridable dependency. The default refuses: no LLM gateway is wired into the app yet."""
    raise not_implemented(
        "missions need an LLM gateway; wire SourcingService in the app (D4-04 + D4-03 config)"
    )


def get_event_bus(request: Request) -> Any:
    """The bus lives on the app state so the SSE route and the service share one instance."""
    bus = getattr(request.app.state, "mission_event_bus", None)
    if bus is None:
        raise not_implemented("mission event bus is not wired into the app")
    return bus


@router.post("", response_model=MissionOut, status_code=status.HTTP_201_CREATED, tags=["missions"])
async def create_mission(
    body: MissionIn,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
) -> MissionOut:
    """Create and plan a mission. Planning is one model call, so the response already carries the plan."""
    request = service.build_request(
        tenant_id=tenant_id,
        request_id=body.sourcing_request_id,
        spec=body.spec,
        quantity_tiers=[_tier(q) for q in body.quantity_tiers],
        deadline=_date(body.deadline),
        destination_country=body.destination_country,
        certifications=list(body.certifications),
        budget_text=body.budget_text,
    )
    try:
        mission = await service.create_mission(tenant_id=tenant_id, request=request)
    except StructuredOutputError as exc:
        raise Problem(
            502,
            "Model output unusable",
            detail="the planner did not return a valid plan",
            reason="structured_output_failed",
        ) from exc
    return MissionOut.of(mission)


@router.get("/{id}", response_model=MissionOut, tags=["missions"])
async def get_mission(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
) -> MissionOut:
    try:
        mission = await service.get_mission(tenant_id=tenant_id, mission_id=id)
    except MissionMissing as exc:
        raise Problem(404, "Mission not found", detail=f"mission {id} not found") from exc
    return MissionOut.of(mission)


@router.get("/{id}/events", tags=["missions"])
async def stream_mission_events(
    id: str,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
    bus: Annotated[Any, Depends(get_event_bus)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Server-Sent Events for one mission: replay from ``Last-Event-ID``, then follow live."""
    try:
        mission = await service.get_mission(
            tenant_id=tenant_id, mission_id=id
        )  # 404 before streaming
    except MissionMissing as exc:
        raise Problem(404, "Mission not found", detail=f"mission {id} not found") from exc
    after = _parse_last_event_id(last_event_id)
    return StreamingResponse(
        _stream(mission, bus, after_seq=after),
        media_type=SSE_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{id}/offers")
async def list_mission_offers(id: str) -> None:
    """Offers with SellerConfidence, PriceSanityCheck and FinancialFit (D4-10)."""
    raise not_implemented("offers per mission arrive with D4-10")


@router.get("/{id}/recommendation")
async def get_mission_recommendation(id: str) -> None:
    """Explainable ranking (MCDA, D4-12)."""
    raise not_implemented("recommendation arrives with D4-12")


async def _stream(mission: Mission, bus: Any, *, after_seq: int) -> AsyncIterator[bytes]:
    """Replay the mission's log, then follow the bus until the mission reaches a terminal status."""
    last = after_seq
    for event in mission.events:
        if event.seq > last:
            yield _sse(event)
            last = event.seq
    if mission.status in STREAM_ENDS_AT:
        return
    async for item in bus.stream(mission.id, after_seq=last, idle_timeout_s=HEARTBEAT_SECONDS):
        if item is None:
            yield b": heartbeat\n\n"
            continue
        yield _sse(item)
        last = item.seq
        if item.type.value in {"mission_failed", "mission_cancelled"}:
            return


def _sse(event: MissionEvent) -> bytes:
    data = json.dumps(
        {"type": event.type.value, "at": event.at.isoformat(), "payload": event.payload},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"id: {event.seq}\nevent: {event.type.value}\ndata: {data}\n\n".encode()


def _parse_last_event_id(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError as exc:
        raise Problem(
            400, "Invalid Last-Event-ID", detail="must be an integer sequence number"
        ) from exc
    if value < 0:
        raise Problem(400, "Invalid Last-Event-ID", detail="must be >= 0")
    return value


def _tier(quantity: int) -> Any:
    from apex.agents.sourcing import QuantityTier

    return QuantityTier(min_quantity=quantity)


def _date(raw: str | None) -> Any:
    from datetime import date

    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise Problem(
            422, "Invalid deadline", detail="deadline must be an ISO date (YYYY-MM-DD)"
        ) from exc


__all__ = ["get_event_bus", "get_sourcing_service", "router"]
