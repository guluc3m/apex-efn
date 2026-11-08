"""Tenant configuration endpoints (ADR-400, spec §7).

Exports ``router`` with paths relative to the ``/config`` prefix, which ``api/__init__.py`` mounts
(D4-01 owns that file). Endpoints:

- ``GET  /config/effective?category=``  effective config with ``config_version``, ``content_hash``
  and per-key provenance. Unset keys are returned explicitly as ``status: unset``.
- ``POST /config/proposals``              propose a change; creates a ``pending_signature`` decision and
  answers ``202`` with its id. The change is applied only after the decision is signed (not here).

The decision port defaults to ``UnwiredDecisionPort``, which refuses to create decisions (501) until
DEV-2's ``apex.signing.api`` is merged. Tests and the app override ``get_config_service``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field

from apex.common.clock import Clock, SystemClock
from apex.common.errors import Problem, not_implemented
from apex.tenant_config.deps import get_tenant_id
from apex.tenant_config.errors import (
    ConfigValidationError,
    NonConfigurableKeyError,
    StaleBaseVersionError,
)
from apex.tenant_config.ports import ConfigRepository, Decision, DecisionPort
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.resolver import EffectiveConfig
from apex.tenant_config.service import TenantConfigService

router = APIRouter()


class UnwiredDecisionPort:
    """Placeholder until DEV-2 ships ``apex.signing.api``. Refuses to create unsigned decisions."""

    async def create_decision(
        self, type: str, subject_ref: str, payload: dict[str, Any]
    ) -> Decision:
        raise NotImplementedError("signing is not wired yet (DEV-2 apex.signing.api pending)")

    async def require_signed(self, decision_id: str) -> Decision:
        raise NotImplementedError("signing is not wired yet (DEV-2 apex.signing.api pending)")


_repository: ConfigRepository = InMemoryConfigRepository()
_decisions: DecisionPort = UnwiredDecisionPort()
_clock: Clock = SystemClock()


def get_config_service() -> TenantConfigService:
    """Overridable dependency. Swap repository/decision port here when D2-05 and DEV-2 land."""
    return TenantConfigService(_repository, _decisions, _clock)


class EffectiveValueOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: Any
    status: str = Field(description="'set' or 'unset' ('sin definir')")
    layer: str = Field(description="global | tenant | category")


class EffectiveConfigOut(BaseModel):
    tenant_id: str
    category: str | None
    config_version: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    resolved_at: str
    values: dict[str, EffectiveValueOut]


class ConfigChangeIn(BaseModel):
    base_config_version: int = Field(ge=1)
    category: str | None = None
    patch: dict[str, Any] = Field(description="Deep-merge patch. Explicit null unsets a key.")


class DecisionAcceptedOut(BaseModel):
    decision_id: str
    status: str = "pending_signature"


def _to_out(eff: EffectiveConfig) -> EffectiveConfigOut:
    return EffectiveConfigOut(
        tenant_id=eff.tenant_id,
        category=eff.category,
        config_version=eff.config_version,
        content_hash=eff.content_hash,
        resolved_at=eff.resolved_at.isoformat(),
        values={
            path: EffectiveValueOut(
                value=rv.value,
                status="unset" if rv.unset else "set",
                layer=rv.layer.value,
            )
            for path, rv in eff.values.items()
        },
    )


@router.get("/effective", response_model=EffectiveConfigOut, tags=["config"])
async def get_effective(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TenantConfigService, Depends(get_config_service)],
    category: Annotated[str | None, Query(max_length=64)] = None,
) -> EffectiveConfigOut:
    eff = await service.effective(tenant_id, category)
    return _to_out(eff)


@router.post(
    "/proposals",
    response_model=DecisionAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["config"],
)
async def propose_change(
    body: ConfigChangeIn,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TenantConfigService, Depends(get_config_service)],
) -> DecisionAcceptedOut:
    try:
        decision_id = await service.propose_change(
            tenant_id,
            body.patch,
            base_config_version=body.base_config_version,
            category=body.category,
        )
    except NonConfigurableKeyError as exc:
        raise Problem(
            422, "Non-configurable key", detail=str(exc), reason="non_configurable_key"
        ) from exc
    except ConfigValidationError as exc:
        raise Problem(
            422, "Invalid configuration", detail=str(exc), reason="invalid_config"
        ) from exc
    except StaleBaseVersionError as exc:
        raise Problem(
            409, "Stale config version", detail=str(exc), reason="stale_config_version"
        ) from exc
    except NotImplementedError as exc:
        raise not_implemented(str(exc)) from exc
    return DecisionAcceptedOut(decision_id=decision_id)
