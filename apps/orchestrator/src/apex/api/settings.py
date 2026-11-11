"""Tenant LLM provider settings endpoints (dashboard settings page).

Mounted by ``api/__init__.py`` at ``/settings`` so the public paths are:

* ``GET    /v1/settings/llm-provider``       current settings, never the raw key
* ``PUT    /v1/settings/llm-provider``       replace base URL/model and optionally the key
* ``DELETE /v1/settings/llm-provider``       forget the tenant's provider
* ``POST   /v1/settings/llm-provider/test``  call ``{base_url}/v1/models`` with the stored key

The tenant comes from :func:`apex.tenant_config.deps.get_tenant_id` (the same dependency the config
router uses). The store is process-wide (:data:`apex.llm.provider_store.PROVIDER_STORE`) so the gateway
wiring sees writes immediately. The raw key is never returned, logged or included in an error message.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from apex.llm.provider_store import PROVIDER_STORE, LlmProviderSettings, TenantProviderStore
from apex.llm.transport import normalise_base_url
from apex.tenant_config.deps import get_tenant_id

router = APIRouter()

_TEST_TIMEOUT_S = 5.0


class LlmProviderSettingsOut(BaseModel):
    """The public view of a tenant's provider settings. The key is represented only by a boolean."""

    base_url: str | None
    model: str | None
    api_key_set: bool
    updated_at: datetime | None


class LlmProviderUpdate(BaseModel):
    """PUT body. ``api_key`` is tri-state: omitted/empty keeps the key, explicit ``null`` clears it."""

    model_config = ConfigDict(extra="forbid")

    base_url: str
    model: str
    api_key: str | None = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        candidate = value.strip()
        try:
            parsed = urlsplit(candidate)
        except ValueError as exc:
            raise ValueError("base_url must be an absolute http(s) URL") from exc
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")
        try:
            hostname = parsed.hostname
        except ValueError as exc:
            raise ValueError("base_url must be an absolute http(s) URL") from exc
        if not hostname:
            raise ValueError("base_url must be an absolute http(s) URL")
        return candidate

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("model must not be empty")
        return candidate


class LlmProviderTestOut(BaseModel):
    """Result of probing the configured provider. ``error`` is a human-readable reason, never a key."""

    ok: bool
    models: list[str]
    error: str | None


def get_provider_store() -> TenantProviderStore:
    """Overridable dependency returning the process-wide store shared with the gateway wiring."""
    return PROVIDER_STORE


def get_http_transport() -> httpx.AsyncBaseTransport | None:
    """Overridable dependency: tests inject an ``httpx.MockTransport`` here."""
    return None


def _to_out(settings: LlmProviderSettings | None) -> LlmProviderSettingsOut:
    if settings is None:
        return LlmProviderSettingsOut(
            base_url=None, model=None, api_key_set=False, updated_at=None
        )
    return LlmProviderSettingsOut(
        base_url=settings.base_url,
        model=settings.model,
        api_key_set=settings.api_key is not None,
        updated_at=settings.updated_at,
    )


def _api_key_for_update(
    body: LlmProviderUpdate, existing: LlmProviderSettings | None
) -> SecretStr | None:
    """Apply the tri-state ``api_key`` rule without ever exposing the stored value."""
    if "api_key" not in body.model_fields_set:
        return existing.api_key if existing is not None else None

    raw_key = body.api_key
    if raw_key is None:
        return None
    if raw_key == "":
        return existing.api_key if existing is not None else None
    return SecretStr(raw_key)


@router.get("/llm-provider", response_model=LlmProviderSettingsOut)
async def get_llm_provider(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    store: Annotated[TenantProviderStore, Depends(get_provider_store)],
) -> LlmProviderSettingsOut:
    """Current provider settings for the caller's tenant (empty shape when unset)."""
    return _to_out(store.get(tenant_id))


@router.put("/llm-provider", response_model=LlmProviderSettingsOut)
async def put_llm_provider(
    body: LlmProviderUpdate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    store: Annotated[TenantProviderStore, Depends(get_provider_store)],
) -> LlmProviderSettingsOut:
    """Create or replace the tenant's provider settings."""
    existing = store.get(tenant_id)
    settings = store.set(
        tenant_id,
        base_url=body.base_url,
        model=body.model,
        api_key=_api_key_for_update(body, existing),
    )
    return _to_out(settings)


@router.delete("/llm-provider", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_provider(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    store: Annotated[TenantProviderStore, Depends(get_provider_store)],
) -> Response:
    """Forget the tenant's provider settings. Idempotent: deleting nothing is still 204."""
    store.clear(tenant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/llm-provider/test", response_model=LlmProviderTestOut)
async def test_llm_provider(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    store: Annotated[TenantProviderStore, Depends(get_provider_store)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(get_http_transport)],
) -> LlmProviderTestOut:
    """Probe ``{base_url}/v1/models`` with the stored Bearer key and a 5-second timeout.

    Never raises for a provider failure: the dashboard needs the reason to show it. The key is only
    placed in the request header, never in the response or an error string.
    """
    settings = store.get(tenant_id)
    if settings is None:
        return LlmProviderTestOut(
            ok=False, models=[], error="LLM provider is not configured"
        )

    url = f"{normalise_base_url(settings.base_url)}/v1/models"
    headers: dict[str, str] = {}
    if settings.api_key is not None:
        headers["Authorization"] = f"Bearer {settings.api_key.get_secret_value()}"

    try:
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_S, transport=transport) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        return LlmProviderTestOut(
            ok=False, models=[], error="provider request timed out after 5 seconds"
        )
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        return LlmProviderTestOut(
            ok=False, models=[], error=f"provider request failed: {type(exc).__name__}"
        )

    if response.status_code >= 400:
        return LlmProviderTestOut(
            ok=False,
            models=[],
            error=f"provider returned HTTP {response.status_code}",
        )

    try:
        payload: Any = response.json()
    except ValueError:
        return LlmProviderTestOut(
            ok=False, models=[], error="provider returned invalid JSON"
        )

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return LlmProviderTestOut(
            ok=False, models=[], error="provider returned an invalid model list"
        )

    models = [
        str(item["id"])
        for item in data
        if isinstance(item, dict) and item.get("id") is not None
    ]
    return LlmProviderTestOut(ok=True, models=models, error=None)


__all__ = [
    "LlmProviderSettingsOut",
    "LlmProviderTestOut",
    "LlmProviderUpdate",
    "get_http_transport",
    "get_provider_store",
    "router",
]
