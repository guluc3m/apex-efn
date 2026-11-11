"""Ranking profiles (issue #306): the tenant's ``scoring.profiles`` from its effective config.

A profile is listed only when it carries the negotiation params and hard constraints the contract requires;
nothing is filled in here (AGENTS.md rule 0.6).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from apex.api.config import get_config_service
from apex.contracts.generated.models import ProfileList, UserProfilePreference
from apex.tenant_config.deps import get_tenant_id
from apex.tenant_config.service import TenantConfigService

router = APIRouter()


@router.get("", response_model=ProfileList, tags=["config"])
async def list_profiles(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    config: Annotated[TenantConfigService, Depends(get_config_service)],
) -> ProfileList:
    profiles = (await config.effective(tenant_id)).typed.scoring.profiles or {}
    return ProfileList(
        items=[
            UserProfilePreference(
                id=pid,
                name=p.name,
                weights={c.value: float(w) for c, w in p.weights.items()},
                negotiation=p.negotiation,
                hard_constraints=p.hard_constraints,
            )
            for pid, p in sorted(profiles.items())
            if p.negotiation is not None and p.hard_constraints is not None
        ]
    )
