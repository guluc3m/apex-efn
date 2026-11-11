"""Category suggestions (issue #378): the categories already present in the tenant's config overrides."""

from typing import Annotated

from fastapi import APIRouter, Depends

from apex.api.config import get_config_service
from apex.contracts.generated.models import CategoryList, Item
from apex.tenant_config.deps import get_tenant_id
from apex.tenant_config.service import TenantConfigService

router = APIRouter()


@router.get("", response_model=CategoryList, tags=["config"])
async def list_categories(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TenantConfigService, Depends(get_config_service)],
) -> CategoryList:
    return CategoryList(items=[Item(id=c) for c in await service.categories(tenant_id)])
