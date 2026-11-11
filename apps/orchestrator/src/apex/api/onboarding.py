"""Onboarding endpoints (owner: DEV-4, D4-07).

``POST /v1/onboarding/sessions`` starts a session. ``POST /{id}/financial-csv`` stores the original and
returns the import report; it **never activates** anything. ``POST /{id}/financial-csv/activate`` creates the
signed decision that activation requires; the snapshot only becomes active once that decision is signed.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from apex.agents.header_mapping import MappingError
from apex.agents.onboarding import (
    CompanyProfile,
    FinancialSnapshot,
    IntakeMessage,
    OnboardingService,
    OnboardingSession,
    SnapshotNotActivatable,
)
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_tenant_id
from apex.contracts.generated.models import (
    ActivateFinancialSnapshotRequest,
    SendIntakeMessageRequest,
)
from apex.llm.resilience import AllEndpointsUnavailableError
from apex.llm.structured import StructuredOutputError
from apex.llm.transport import LLMHTTPError, LLMTransportError

router = APIRouter()

MAX_CSV_BYTES = 5 * 1024 * 1024
"""A financial CSV is a few hundred rows. Anything bigger is a mistake or an attack."""


class SessionOut(BaseModel):
    id: str
    tenant_id: str
    status: str
    profile: dict[str, Any]
    company_profile: dict[str, Any]
    """Same as ``profile`` under the contract name (``OnboardingSession.company_profile``)."""
    created_at: str
    updated_at: str
    active_snapshot_id: str | None
    pending_snapshot_id: str | None

    @classmethod
    def of(cls, session: OnboardingSession) -> SessionOut:
        return cls(
            id=session.id,
            tenant_id=session.tenant_id,
            status=session.status.value,
            profile=session.profile.model_dump(mode="json"),
            company_profile=session.profile.model_dump(mode="json"),
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            active_snapshot_id=session.active_snapshot_id,
            pending_snapshot_id=session.pending_snapshot_id,
        )


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_name: str | None = Field(default=None, max_length=200)
    sector: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=2)
    base_currency: str | None = Field(default=None, pattern="^(EUR|USD|CNY)$")
    budget_eur_minor: int | None = Field(default=None, ge=0)


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
    body: ProfileIn,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[OnboardingService, Depends(get_onboarding)],
) -> SessionOut:
    """Progressive form backend: save whatever the buyer has filled in so far."""
    try:
        session = await service.update_profile(
            tenant_id=tenant_id, session_id=id, profile=CompanyProfile(**body.model_dump())
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
