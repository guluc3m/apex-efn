"""Onboarding endpoints (owner: DEV-4, D4-07).

``POST /v1/onboarding/sessions`` starts a session. ``POST /{id}/financial-csv`` stores the original and
returns the import report; it **never activates** anything. ``POST /{id}/financial-csv/activate`` creates the
signed decision that activation requires; the snapshot only becomes active once that decision is signed.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from pydantic import BaseModel

from apex.agents.header_mapping import MappingError
from apex.agents.onboarding import (
    CompanyProfile,
    FinancialSnapshot,
    IntakeMessage,
    OnboardingService,
    OnboardingSession,
    OnboardingStatus,
    SnapshotNotActivatable,
    StepProgress,
)
from apex.api.config import _to_out, get_config_service
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_tenant_id
from apex.contracts.generated.models import (
    ActivateFinancialSnapshotRequest,
    EffectiveConfig,
    SendIntakeMessageRequest,
    UpdateOnboardingSessionRequest,
)
from apex.domain.finance.csv_import import CsvImportError
from apex.llm.resilience import AllEndpointsUnavailableError
from apex.llm.structured import StructuredOutputError
from apex.llm.transport import LLMHTTPError, LLMTransportError
from apex.tenant_config.service import TenantConfigService

router = APIRouter()

MAX_CSV_BYTES = 5 * 1024 * 1024
"""A financial CSV is a few hundred rows. Anything bigger is a mistake or an attack."""


_STATUS = {
    OnboardingStatus.STARTED: "profiling",
    OnboardingStatus.PROFILED: "profiling",
    OnboardingStatus.AWAITING_SNAPSHOT_ACTIVATION: "financials_imported",
    OnboardingStatus.COMPLETE: "completed",
}
"""Internal state machine -> the contract's ``OnboardingStatus``."""


def _company_profile(profile: CompanyProfile) -> dict[str, Any]:
    out = profile.model_dump(mode="json", exclude={"budget_minor"})
    out["budget"] = (
        {"amount_minor": profile.budget_minor, "currency": profile.base_currency}
        if profile.budget_minor is not None and profile.base_currency
        else None
    )
    return out


class SessionOut(BaseModel):
    id: str
    tenant_id: str
    status: str
    company_profile: dict[str, Any]
    created_at: str
    updated_at: str
    active_financial_snapshot_id: str | None
    pending_snapshot_id: str | None
    steps: list[dict[str, Any]] | None = None
    effective_config: dict[str, Any] | None = None

    @classmethod
    def of(
        cls,
        session: OnboardingSession,
        *,
        steps: list[StepProgress] | None = None,
        effective_config: EffectiveConfig | None = None,
    ) -> SessionOut:
        return cls(
            id=session.id,
            tenant_id=session.tenant_id,
            status=_STATUS[session.status],
            company_profile=_company_profile(session.profile),
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            active_financial_snapshot_id=session.active_snapshot_id,
            pending_snapshot_id=session.pending_snapshot_id,
            steps=[asdict(x) for x in steps] if steps is not None else None,
            effective_config=effective_config.model_dump(mode="json") if effective_config else None,
        )


async def _full(
    session: OnboardingSession,
    tenant_id: str,
    service: OnboardingService,
    config: TenantConfigService,
) -> SessionOut:
    """The contract's ``OnboardingSession``: with per-step progress and the effective config."""
    return SessionOut.of(
        session,
        steps=await service.step_progress(session),
        effective_config=_to_out(await config.effective(tenant_id)),
    )


class SnapshotOut(BaseModel):
    id: str
    status: str
    stored_object: str
    report: dict[str, Any]
    config_version: str
    imported_at: str
    activated_at: str | None
    activation_decision_id: str | None

    @classmethod
    def of(cls, snapshot: FinancialSnapshot) -> SnapshotOut:
        return cls(
            id=snapshot.id,
            status=snapshot.status.value,
            stored_object=snapshot.stored_object,
            report=snapshot.report,
            config_version=snapshot.config_version,
            imported_at=snapshot.imported_at.isoformat(),
            activated_at=snapshot.activated_at.isoformat() if snapshot.activated_at else None,
            activation_decision_id=snapshot.activation_decision_id,
        )


class ActivationAcceptedOut(BaseModel):
    decision_id: str
    status: str = "pending_signature"


def get_onboarding() -> OnboardingService:
    """Overridable dependency. The default refuses: the importer and object storage are not wired yet."""
    raise not_implemented(
        "onboarding needs the CSV importer (D3-04) and object storage; wire OnboardingService in the app"
    )


@router.post(
    "/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED, tags=["onboarding"]
)
async def create_onboarding_session(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
) -> SessionOut:
    """Start a conversational profiling session."""
    return SessionOut.of(await service.start_session(tenant_id=tenant_id))


@router.get("/sessions", tags=["onboarding"])
async def list_onboarding_sessions(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
    config: Annotated[TenantConfigService, Depends(get_config_service)],
    session_status: Annotated[list[str] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, list[SessionOut]]:
    """The tenant's sessions, newest first. ``status`` filters by the contract status."""
    sessions = await service.list_sessions(tenant_id=tenant_id)
    if session_status:
        sessions = [x for x in sessions if _STATUS[x.status] in session_status]
    return {"items": [await _full(x, tenant_id, service, config) for x in sessions[:limit]]}


@router.get("/sessions/{id}", response_model=SessionOut, tags=["onboarding"])
async def get_onboarding_session(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
    config: Annotated[TenantConfigService, Depends(get_config_service)],
) -> SessionOut:
    """One session with per-step progress, so the wizard restores its draft after a reload."""
    try:
        session = await service.get_session(tenant_id=tenant_id, session_id=id)
    except LookupError as exc:
        raise Problem(404, "Session not found", detail=str(exc)) from exc
    return await _full(session, tenant_id, service, config)


def _message_out(m: IntakeMessage) -> dict[str, str]:
    return {"id": m.id, "role": m.role, "text": m.text, "created_at": m.created_at.isoformat()}


@router.get("/sessions/{id}/messages", tags=["onboarding"])
async def list_intake_messages(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
) -> dict[str, list[dict[str, str]]]:
    """IntakeAgent conversation history, oldest first."""
    try:
        messages = await service.list_messages(tenant_id=tenant_id, session_id=id)
    except LookupError as exc:
        raise Problem(404, "Session not found", detail=str(exc)) from exc
    return {"items": [_message_out(m) for m in messages]}


@router.post("/sessions/{id}/messages", tags=["onboarding"])
async def send_intake_message(
    id: str,
    body: SendIntakeMessageRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
) -> dict[str, Any]:
    """One chat turn: the user message, the agent reply and the session with any profile fields filled in."""
    try:
        messages, session = await service.send_message(
            tenant_id=tenant_id, session_id=id, text=body.text
        )
    except LookupError as exc:
        raise Problem(404, "Session not found", detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise not_implemented("the IntakeAgent needs an LLM gateway; wire it in the app") from exc
    except StructuredOutputError as exc:
        raise Problem(
            502,
            "Model output unusable",
            detail="the intake model did not return a valid reply",
            reason="structured_output_failed",
        ) from exc
    except (AllEndpointsUnavailableError, LLMTransportError, LLMHTTPError) as exc:
        raise Problem(
            502,
            "Model endpoint unavailable",
            detail="the extractor endpoint could not be reached",
            reason="llm_unavailable",
        ) from exc
    return {
        "messages": [_message_out(m) for m in messages],
        "session": SessionOut.of(session).model_dump(),
    }


@router.patch("/sessions/{id}", response_model=SessionOut, tags=["onboarding"])
async def update_profile(
    id: str,
    body: UpdateOnboardingSessionRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
) -> SessionOut:
    """Progressive form backend: save whatever the buyer has filled in so far. Omitted fields keep their value."""
    fields = body.company_profile.model_dump(mode="json", exclude_unset=True)
    budget = fields.pop("budget", None)
    if budget is not None:
        fields["budget_minor"] = budget["amount_minor"]
    try:
        session = await service.update_profile(
            tenant_id=tenant_id, session_id=id, profile=CompanyProfile(**fields)
        )
    except LookupError as exc:
        raise Problem(404, "Session not found", detail=str(exc)) from exc
    return SessionOut.of(session)


@router.post(
    "/{id}/financial-csv",
    response_model=SnapshotOut,
    status_code=status.HTTP_201_CREATED,
    tags=["onboarding"],
)
async def upload_financial_csv(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
    file: Annotated[UploadFile, File(description="Financial CSV (long format, UTF-8)")],
    base_currency: Annotated[str, Form(pattern="^(EUR|USD|CNY)$")] = "EUR",
    column_mapping: Annotated[str | None, Form()] = None,
) -> SnapshotOut:
    """Store the original, import it and return the report. Nothing is activated here."""
    content = await _read_csv(file)
    try:
        mapping = json.loads(column_mapping) if column_mapping else None
        if mapping is not None and not (
            isinstance(mapping, dict) and all(isinstance(v, str) for v in mapping.values())
        ):
            raise ValueError("column_mapping must be a JSON object of strings")
    except ValueError as exc:
        raise Problem(422, "Invalid column_mapping", detail=str(exc)) from exc
    try:
        snapshot = await service.upload_financial_csv(
            tenant_id=tenant_id,
            session_id=id,
            content=content,
            filename=file.filename or "financial.csv",
            base_currency=base_currency,
            column_mapping=mapping,
        )
    except LookupError as exc:
        raise Problem(404, "Session not found", detail=str(exc)) from exc
    except MappingError as exc:
        raise Problem(422, "Invalid column_mapping", detail=str(exc)) from exc
    except CsvImportError as exc:
        raise Problem(422, "Unreadable financial CSV", detail=str(exc)) from exc
    except NotImplementedError as exc:
        # The importer or object storage is not wired yet: say so instead of failing with a 500.
        raise not_implemented(str(exc)) from exc
    return SnapshotOut.of(snapshot)


async def _read_csv(file: UploadFile) -> bytes:
    content = await file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise Problem(
            413, "File too large", detail=f"the CSV must be at most {MAX_CSV_BYTES} bytes"
        )
    return content


@router.post("/{id}/financial-csv/mapping", tags=["onboarding"])
async def suggest_financial_csv_mapping(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
    file: Annotated[UploadFile, File(description="Financial CSV; only its header row is read")],
) -> dict[str, Any]:
    """Suggest header -> canonical column. The buyer confirms it as ``column_mapping`` on the upload."""
    content = await _read_csv(file)
    try:
        return await service.suggest_header_mapping(
            tenant_id=tenant_id, session_id=id, content=content
        )
    except LookupError as exc:
        raise Problem(404, "Session not found", detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise not_implemented("the header mapper needs an LLM gateway; wire it in the app") from exc
    except StructuredOutputError as exc:
        raise Problem(
            502,
            "Model output unusable",
            detail="the extractor model did not return a valid mapping",
            reason="structured_output_failed",
        ) from exc
    except (AllEndpointsUnavailableError, LLMTransportError, LLMHTTPError) as exc:
        raise Problem(
            502,
            "Model endpoint unavailable",
            detail="the extractor endpoint could not be reached",
            reason="llm_unavailable",
        ) from exc


@router.get("/{id}/financial-csv/{import_id}", response_model=SnapshotOut, tags=["onboarding"])
async def get_financial_import(
    id: str,
    import_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
) -> SnapshotOut:
    """One import with its report (the report page is addressed by import id)."""
    try:
        return SnapshotOut.of(
            await service.get_import(tenant_id=tenant_id, session_id=id, import_id=import_id)
        )
    except LookupError as exc:
        raise Problem(404, "Import not found", detail=str(exc)) from exc


@router.post(
    "/{id}/financial-csv/activate",
    response_model=ActivationAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["onboarding"],
)
async def activate_financial_snapshot(
    id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
    body: ActivateFinancialSnapshotRequest,
) -> ActivationAcceptedOut:
    """Create the signed decision that activation requires. The snapshot is not active until it is signed."""
    try:
        decision = await service.request_activation(
            tenant_id=tenant_id, session_id=id, snapshot_id=body.import_id
        )
    except LookupError as exc:
        raise Problem(404, "Snapshot not found", detail=str(exc)) from exc
    except SnapshotNotActivatable as exc:
        raise Problem(409, "Snapshot not activatable", detail=exc.detail) from exc
    return ActivationAcceptedOut(decision_id=decision.id)


__all__ = ["get_onboarding", "router"]
