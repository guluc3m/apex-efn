"""Mission endpoints (owner: DEV-4, D4-08 / D4-10 / D4-12).

Shapes come from ``contracts/openapi.yaml``: ``CreateMissionRequest`` → ``Mission``, and ``MissionEvent``
for the SSE payload. The router defines no DTOs of its own (spec §5.1).

``POST /v1/missions`` takes only a ``sourcing_request_id``, so the request is looked up in the store the
sourcing router writes to. Planning runs inline (one model call), which is why the reply already carries the
mission's state.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import Response, StreamingResponse

from apex.agents.missions import InvalidMissionTransition, MissionStatus
from apex.agents.missions import Mission as DomainMission
from apex.agents.recommendation_export import (
    MEDIA_TYPES,
    ExportFormat,
    RecommendationProvider,
    render,
)
from apex.agents.request_store import SourcingRequestStore
from apex.agents.sourcing_service import MissionMissing, SourcingService
from apex.api.contract_map import mission_state, to_contract_event, to_contract_mission
from apex.api.sourcing import get_request_store, get_sourcing_service
from apex.common.errors import Problem, not_implemented
from apex.common.pagination import Cursor, parse_limit
from apex.common.tenant import get_tenant_id
from apex.contracts.generated.models import (
    CreateMissionRequest,
    Mission,
    MissionEvent,
    MissionPage,
)
from apex.llm.budget import TokenBudgetExceeded
from apex.llm.resilience import AllEndpointsUnavailableError
from apex.llm.structured import StructuredOutputError
from apex.llm.transport import LLMHTTPError, LLMTransportError

router = APIRouter()

SSE_MEDIA_TYPE = "text/event-stream"
HEARTBEAT_SECONDS = 15.0
"""Comment lines keep proxies from closing an idle stream. No event is invented for it."""

STREAM_ENDS_AT: frozenset[MissionStatus] = frozenset(
    {MissionStatus.PLANNED, MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED}
)
"""Statuses after which this service emits nothing more for the mission.

``PLANNED`` is one of them on purpose: planning is the last step the sourcing service performs, so a stream
opened on a planned mission would otherwise wait for a heartbeat forever. The client reconnects with
``Last-Event-ID`` when the mission starts running, which loses nothing."""


def get_event_bus(request: Request) -> Any:
    """The bus lives on the app state so the SSE route and the service share one instance."""
    bus = getattr(request.app.state, "mission_event_bus", None)
    if bus is None:
        raise not_implemented("mission event bus is not wired into the app")
    return bus


def get_token_budget(request: Request) -> int:
    """The mission token budget the contract reports. Read from settings, never a literal here."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise not_implemented("settings are not wired into the app")
    budget: int = settings.llm_mission_token_budget
    return budget


def _tokens_used(request: Request, mission_id: str) -> int:
    """What the gateway has committed for this mission. Zero when no gateway is wired."""
    services = getattr(request.app.state, "app_services", None)
    gateway = getattr(services, "gateway", None)
    if gateway is None:
        return 0
    used: int = gateway.tokens_used(mission_id)
    return used


@router.post("", response_model=Mission, status_code=status.HTTP_201_CREATED, tags=["missions"])
async def create_mission(
    body: CreateMissionRequest,
    http_request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
    store: Annotated[SourcingRequestStore, Depends(get_request_store)],
    token_budget: Annotated[int, Depends(get_token_budget)],
) -> Mission:
    """Create and plan a mission for a stored sourcing request."""
    request = await store.get(tenant_id, body.sourcing_request_id)
    if request is None:
        raise Problem(
            404,
            "Sourcing request not found",
            detail=f"sourcing request {body.sourcing_request_id} not found",
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
    except (AllEndpointsUnavailableError, LLMTransportError, LLMHTTPError) as exc:
        raise Problem(
            502,
            "Model endpoint unavailable",
            detail=f"the planner endpoint could not be reached: {_llm_detail(exc)}",
            reason="llm_unavailable",
        ) from exc
    except TokenBudgetExceeded as exc:
        raise Problem(
            429, "Token budget exhausted", detail=exc.warning, reason="token_budget_exhausted"
        ) from exc
    mission = await _maybe_autorun(http_request, tenant_id=tenant_id, mission=mission)
    return to_contract_mission(
        mission, token_budget=token_budget, tokens_used=_tokens_used(http_request, mission.id)
    )


async def _maybe_autorun(
    request: Request, *, tenant_id: str, mission: DomainMission
) -> DomainMission:
    """Advance the mission right away when ``mission_autorun`` is on.

    Off by default: the runner needs the browser worker (D5-01) and the DEV-3 engines, so with them missing
    every mission would fail at its first step. The flag makes turning it on a configuration change.
    """
    settings = getattr(request.app.state, "settings", None)
    services = getattr(request.app.state, "app_services", None)
    runner = getattr(services, "runner", None)
    if settings is None or runner is None or not settings.mission_autorun:
        return mission
    if mission.status is not MissionStatus.PLANNED:
        return mission
    result = await runner.run(tenant_id=tenant_id, mission_id=mission.id)
    advanced: DomainMission = result.mission
    return advanced


@router.get("/{id}", response_model=Mission, tags=["missions"])
async def get_mission(
    id: str,
    http_request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
    token_budget: Annotated[int, Depends(get_token_budget)],
) -> Mission:
    try:
        mission = await service.get_mission(tenant_id=tenant_id, mission_id=id)
    except MissionMissing as exc:
        raise Problem(404, "Mission not found", detail=f"mission {id} not found") from exc
    return to_contract_mission(
        mission, token_budget=token_budget, tokens_used=_tokens_used(http_request, mission.id)
    )


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
        mission = await service.get_mission(tenant_id=tenant_id, mission_id=id)
    except MissionMissing as exc:
        raise Problem(404, "Mission not found", detail=f"mission {id} not found") from exc
    after = _parse_last_event_id(last_event_id)
    return StreamingResponse(
        _stream(mission, bus, after_seq=after),
        media_type=SSE_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=MissionPage, tags=["missions"])
async def list_missions(
    http_request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
    token_budget: Annotated[int, Depends(get_token_budget)],
    cursor: str | None = None,
    limit: int = 25,
    state: str | None = None,
) -> MissionPage:
    """Missions of the tenant, newest first. Keyset cursor over ``(created_at, id)``."""
    limit = parse_limit(limit, default=25, maximum=100)
    rows = await service.list_missions(tenant_id=tenant_id)
    if state is not None:
        rows = [m for m in rows if mission_state(m.status).value == state]
    if cursor is not None:
        pos = Cursor.decode(cursor)
        key = (pos.get("at"), pos.get("id"))
        rows = [m for m in rows if (m.created_at.isoformat(), m.id) < key]
    page = rows[:limit]
    nxt = None
    if len(rows) > limit:
        nxt = Cursor.encode({"at": page[-1].created_at.isoformat(), "id": page[-1].id})
    return MissionPage(
        items=[
            to_contract_mission(
                m, token_budget=token_budget, tokens_used=_tokens_used(http_request, m.id)
            )
            for m in page
        ],
        next_cursor=nxt,
    )


async def _change(
    action: Callable[..., Awaitable[DomainMission]],
    id: str,
    http_request: Request,
    tenant_id: str,
    token_budget: int,
) -> Mission:
    try:
        mission = await action(tenant_id=tenant_id, mission_id=id)
    except MissionMissing as exc:
        raise Problem(404, "Mission not found", detail=f"mission {id} not found") from exc
    except InvalidMissionTransition as exc:
        raise Problem(409, "Mission cannot change", detail=str(exc)) from exc
    return to_contract_mission(
        mission, token_budget=token_budget, tokens_used=_tokens_used(http_request, mission.id)
    )


@router.post("/{id}/pause", response_model=Mission, tags=["missions"])
async def pause_mission(
    id: str,
    http_request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
    token_budget: Annotated[int, Depends(get_token_budget)],
) -> Mission:
    """Stop scheduling new work; running steps finish."""
    return await _change(service.pause, id, http_request, tenant_id, token_budget)


@router.post("/{id}/resume", response_model=Mission, tags=["missions"])
async def resume_mission(
    id: str,
    http_request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
    token_budget: Annotated[int, Depends(get_token_budget)],
) -> Mission:
    return await _change(service.resume, id, http_request, tenant_id, token_budget)


@router.post("/{id}/cancel", response_model=Mission, tags=["missions"])
async def cancel_mission(
    id: str,
    http_request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[SourcingService, Depends(get_sourcing_service)],
    token_budget: Annotated[int, Depends(get_token_budget)],
) -> Mission:
    """Cancel for good. Offers already in the gate stay there."""
    return await _change(service.cancel, id, http_request, tenant_id, token_budget)


@router.get("/{id}/offers")
async def list_mission_offers(id: str) -> None:
    """Offers with SellerConfidence, PriceSanityCheck and FinancialFit (D4-10)."""
    raise not_implemented("offers per mission arrive with D4-10")


@router.get("/{id}/recommendation")
async def get_mission_recommendation(id: str) -> None:
    """Explainable ranking (MCDA, D4-12)."""
    raise not_implemented("recommendation arrives with D4-12")


def get_recommendation_provider() -> RecommendationProvider:
    """Overridable dependency. The default refuses: the evaluator and the MCDA port are not wired to the app yet."""
    raise not_implemented("the recommendation is not wired into the app yet (D4-12)")


@router.get("/{id}/recommendation/export")
async def export_mission_recommendation(
    id: str,
    profile: str,
    format: ExportFormat,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    provider: Annotated[RecommendationProvider, Depends(get_recommendation_provider)],
) -> Response:
    """Download the recommendation as pdf, csv or json, built from the ranking numbers only."""
    try:
        rec = await provider.recommendation(tenant_id=tenant_id, mission_id=id, profile_id=profile)
    except LookupError as exc:
        raise Problem(404, "Mission not found", detail=f"mission {id} not found") from exc
    return Response(
        render(rec, format),
        media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="recommendation-{id}.{format}"'},
    )


async def _stream(mission: DomainMission, bus: Any, *, after_seq: int) -> AsyncIterator[bytes]:
    """Replay the mission's log, then follow the bus until the mission reaches a terminal status."""
    last = after_seq
    for event in mission.events:
        if event.seq > last:
            yield _sse(to_contract_event(mission, event))
            last = event.seq
    if mission.status in STREAM_ENDS_AT:
        return
    async for item in bus.stream(mission.id, after_seq=last, idle_timeout_s=HEARTBEAT_SECONDS):
        if item is None:
            yield b": heartbeat\n\n"
            continue
        yield _sse(to_contract_event(mission, item))
        last = item.seq
        if item.type.value in {"mission_failed", "mission_cancelled"}:
            return


def _sse(event: MissionEvent) -> bytes:
    payload = event.model_dump(mode="json")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.id}\nevent: {event.type.value}\ndata: {data}\n\n".encode()


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


def _llm_detail(exc: Exception) -> str:
    causes = getattr(exc, "causes", None)
    if causes:
        return str(causes)
    return f"{type(exc).__name__}: {exc}"


__all__ = ["get_event_bus", "get_token_budget", "router"]
