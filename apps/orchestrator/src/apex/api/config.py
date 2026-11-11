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

from apex.common.clock import Clock, SystemClock
from apex.common.errors import Problem, not_implemented
from apex.common.pagination import Cursor
from apex.contracts.generated.models import (
    ConfigChangeRequest,
    ConfigLayer,
    ConfigValueStatus,
    ConfigVersionPage,
    ConfigVersionSummary,
    DecisionAccepted,
    DecisionStatus,
    EffectiveConfig,
    EffectiveConfigValue,
)
from apex.tenant_config.deps import get_tenant_id
from apex.tenant_config.errors import (
    ConfigValidationError,
    NonConfigurableKeyError,
    StaleBaseVersionError,
)
from apex.tenant_config.ports import ConfigRepository, Decision, DecisionPort
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.resolver import EffectiveConfig as DomainEffectiveConfig
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


def _to_out(eff: DomainEffectiveConfig) -> EffectiveConfig:
    """Domain resolution -> the contract's ``EffectiveConfig`` (``contracts/openapi.yaml``).

    The shapes are the generated models, so the frontend's generated client matches the server (spec §5.1).
    """
    return EffectiveConfig(
        tenant_id=eff.tenant_id,
        category=eff.category,
        config_version=eff.config_version,
        content_hash=eff.content_hash,
        resolved_at=eff.resolved_at,
        values={
            path: EffectiveConfigValue(
                value=rv.value,
                status=ConfigValueStatus.unset if rv.unset else ConfigValueStatus.set,
                layer=ConfigLayer(rv.layer.value),
            )
            for path, rv in eff.values.items()
        },
    )


@router.get("/effective", response_model=EffectiveConfig, tags=["config"])
async def get_effective(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TenantConfigService, Depends(get_config_service)],
    category: Annotated[str | None, Query(max_length=64)] = None,
) -> EffectiveConfig:
    eff = await service.effective(tenant_id, category)
    return _to_out(eff)


@router.post(
    "/proposals",
    response_model=DecisionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["config"],
)
async def propose_change(
    body: ConfigChangeRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TenantConfigService, Depends(get_config_service)],
) -> DecisionAccepted:
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
    return DecisionAccepted(decision_id=decision_id, status=DecisionStatus.pending_signature)


def _changed_keys(prev: dict[str, Any], cur: dict[str, Any]) -> list[str]:
    from apex.tenant_config.resolver import flatten

    before, after = flatten(prev), flatten(cur)
    return sorted(k for k in {*before, *after} if before.get(k) != after.get(k))


@router.get("/versions", response_model=ConfigVersionPage, tags=["config"])
async def list_config_versions(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TenantConfigService, Depends(get_config_service)],
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
) -> ConfigVersionPage:
    """Config version history, newest first. The cursor is the last ``config_version`` returned."""
    rows = await service.history(tenant_id)
    by_version = {r.config_version: r for r in rows}
    if cursor is not None:
        before = Cursor.decode(cursor).get("v")
        if not isinstance(before, int):
            raise Problem(400, "Invalid cursor", detail="The pagination cursor is malformed.")
        rows = [r for r in rows if r.config_version < before]
    page = rows[:limit]
    items = [
        ConfigVersionSummary(
            config_version=r.config_version,
            created_at=r.created_at,
            decision_id=r.decision_id,
            summary=_changed_keys(
                by_version[r.config_version - 1].values
                if r.config_version - 1 in by_version
                else {},
                r.values,
            )
            or None,
        )
        for r in page
    ]
    nxt = Cursor.encode({"v": page[-1].config_version}) if len(rows) > limit else None
    return ConfigVersionPage(items=items, next_cursor=nxt)
