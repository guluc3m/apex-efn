"""Tenant LLM provider store and gateway overlays (dashboard settings backend).

The store tests pin the version semantics and the "key never in repr" rule. The provider tests pin the
overlay the gateway sees: base URL/model/api-key ref/endpoint id, the defaults when unset, and the
resolver fallback. The last test drives a real :class:`LLMGateway` to prove the settings are read at
call time and that a version bump rebuilds the cached transport.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from apex.common.clock import FixedClock
from apex.llm.accounting import InMemorySink
from apex.llm.budget import InMemoryBudgetStore, TokenBudget
from apex.llm.config import (
    LLMRole,
    LLMRolesConfig,
    RoleEndpointConfig,
    StaticRoleConfigProvider,
    StaticSecretResolver,
)
from apex.llm.gateway import LLMGateway
from apex.llm.provider_config import TenantRoleConfigProvider, TenantSecretResolver
from apex.llm.provider_store import TenantProviderStore

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
SECRET = "sk-tenant-SECRET-0123456789"
ENV_SECRET = "sk-env-SECRET-9876543210"


def _default_roles() -> LLMRolesConfig:
    extractor = RoleEndpointConfig(
        endpoint_id="default-extractor",
        base_url="http://env-default.local",
        api_key_ref="env:key",
        model="env-model",
        max_output_tokens=64,
    )
    narrator = RoleEndpointConfig(
        endpoint_id="default-narrator",
        base_url="http://env-default.local",
        api_key_ref="env:key",
        model="env-model",
        max_output_tokens=128,
    )
    return LLMRolesConfig(
        roles={LLMRole.EXTRACTOR: extractor, LLMRole.NARRATOR: narrator},
        endpoints={extractor.endpoint_id: extractor, narrator.endpoint_id: narrator},
    )


def _provider(store: TenantProviderStore) -> TenantRoleConfigProvider:
    return TenantRoleConfigProvider(StaticRoleConfigProvider(_default_roles()), store)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def test_store_set_get_clear() -> None:
    store = TenantProviderStore(clock=FixedClock(NOW))
    assert store.get(TENANT) is None

    settings = store.set(
        TENANT,
        base_url="https://api.example.com",
        model="deepseek-chat",
        api_key=SecretStr(SECRET),
    )
    assert settings.base_url == "https://api.example.com"
    assert settings.model == "deepseek-chat"
    assert settings.version == 1
    assert settings.updated_at == NOW
    assert store.get(TENANT) is settings

    assert store.clear(TENANT) is True
    assert store.get(TENANT) is None
    assert store.clear(TENANT) is False


def test_store_versions_are_monotonic_and_survive_clear() -> None:
    store = TenantProviderStore(clock=FixedClock(NOW))
    first = store.set(TENANT, base_url="https://one.example", model="m1", api_key=None)
    second = store.set(
        TENANT,
        base_url="https://two.example",
        model="m2",
        api_key=SecretStr(SECRET),
        now=NOW + timedelta(minutes=5),
    )
    assert (first.version, second.version) == (1, 2)
    assert second.updated_at == NOW + timedelta(minutes=5)

    store.clear(TENANT)
    third = store.set(TENANT, base_url="https://three.example", model="m3", api_key=None)
    assert third.version == 3, "a cleared tenant must not reuse an endpoint version"


def test_store_keeps_tenants_isolated() -> None:
    store = TenantProviderStore(clock=FixedClock(NOW))
    store.set(TENANT, base_url="https://a.example", model="a", api_key=SecretStr(SECRET))
    assert store.get("tenant-b") is None


def test_key_never_appears_in_repr() -> None:
    store = TenantProviderStore(clock=FixedClock(NOW))
    settings = store.set(
        TENANT,
        base_url="https://api.example.com",
        model="m",
        api_key=SecretStr(SECRET),
    )
    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    assert SECRET not in repr(store)


# ---------------------------------------------------------------------------
# TenantRoleConfigProvider
# ---------------------------------------------------------------------------


def test_no_settings_returns_the_defaults_untouched() -> None:
    defaults = _default_roles()
    provider = TenantRoleConfigProvider(
        StaticRoleConfigProvider(defaults), TenantProviderStore(clock=FixedClock(NOW))
    )
    assert provider.llm_roles(TENANT) is defaults


def test_tenant_settings_override_every_role_and_the_endpoint_registry() -> None:
    store = TenantProviderStore(clock=FixedClock(NOW))
    store.set(
        TENANT,
        base_url="https://tenant.example/v1",
        model="tenant-model",
        api_key=SecretStr(SECRET),
    )
    roles = _provider(store).llm_roles(TENANT)

    assert set(roles.roles) == {LLMRole.EXTRACTOR, LLMRole.NARRATOR}
    for role_config in roles.roles.values():
        assert role_config.base_url == "https://tenant.example/v1"
        assert role_config.model == "tenant-model"
        assert role_config.api_key_ref == f"tenant:{TENANT}"
        assert role_config.endpoint_id == f"tenant-{TENANT}-v1"
        assert role_config.fallback == []

    assert set(roles.endpoints) == {f"tenant-{TENANT}-v1"}
    endpoint = roles.endpoints[f"tenant-{TENANT}-v1"]
    assert endpoint.base_url == "https://tenant.example/v1"
    assert endpoint.model == "tenant-model"
    assert endpoint.api_key_ref == f"tenant:{TENANT}"


def test_a_new_version_changes_the_endpoint_id() -> None:
    store = TenantProviderStore(clock=FixedClock(NOW))
    provider = _provider(store)
    store.set(TENANT, base_url="https://one.example", model="m1", api_key=None)
    first = provider.llm_roles(TENANT).roles[LLMRole.EXTRACTOR].endpoint_id

    store.set(TENANT, base_url="https://two.example", model="m2", api_key=None)
    second = provider.llm_roles(TENANT).roles[LLMRole.EXTRACTOR].endpoint_id

    assert first == f"tenant-{TENANT}-v1"
    assert second == f"tenant-{TENANT}-v2"
    assert first != second


def test_other_tenants_keep_the_defaults() -> None:
    defaults = _default_roles()
    store = TenantProviderStore(clock=FixedClock(NOW))
    store.set(TENANT, base_url="https://tenant.example", model="tenant-model", api_key=None)
    provider = TenantRoleConfigProvider(StaticRoleConfigProvider(defaults), store)
    assert provider.llm_roles("tenant-b") is defaults


# ---------------------------------------------------------------------------
# TenantSecretResolver
# ---------------------------------------------------------------------------


def test_resolver_resolves_tenant_refs_and_falls_back() -> None:
    store = TenantProviderStore(clock=FixedClock(NOW))
    store.set(
        TENANT,
        base_url="https://tenant.example",
        model="m",
        api_key=SecretStr(SECRET),
    )
    resolver = TenantSecretResolver(store, StaticSecretResolver({"env:key": ENV_SECRET}))

    assert resolver.resolve(f"tenant:{TENANT}").get_secret_value() == SECRET
    assert resolver.resolve("env:key").get_secret_value() == ENV_SECRET


def test_resolver_raises_for_unknown_tenant_or_missing_key() -> None:
    store = TenantProviderStore(clock=FixedClock(NOW))
    resolver = TenantSecretResolver(store, StaticSecretResolver({"env:key": ENV_SECRET}))

    with pytest.raises(KeyError):
        resolver.resolve("tenant:unknown")
    with pytest.raises(KeyError):
        resolver.resolve("tenant:")

    store.set(TENANT, base_url="https://tenant.example", model="m", api_key=None)
    with pytest.raises(KeyError):
        resolver.resolve(f"tenant:{TENANT}")


# ---------------------------------------------------------------------------
# Gateway integration: settings are read at call time
# ---------------------------------------------------------------------------


def _chat_body() -> dict[str, object]:
    return {
        "id": "x",
        "object": "chat.completion",
        "model": "provider-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "ok"},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


async def test_gateway_uses_tenant_settings_at_call_time() -> None:
    store = TenantProviderStore(clock=FixedClock(NOW))
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_chat_body())

    def factory(cfg: RoleEndpointConfig) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    gateway = LLMGateway(
        config_provider=_provider(store),
        secrets=TenantSecretResolver(
            store, StaticSecretResolver({"env:key": ENV_SECRET})
        ),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=100_000),
        sink=InMemorySink(),
        clock=FixedClock(NOW),
        http_client_factory=factory,
    )
    messages = [{"role": "user", "content": "hola"}]
    try:
        store.set(
            TENANT,
            base_url="https://tenant.example/v1",
            model="tenant-model",
            api_key=SecretStr(SECRET),
        )
        first = await gateway.chat(
            LLMRole.EXTRACTOR,
            messages,
            mission_id="m1",
            tenant_id=TENANT,
            prompt_version="v1",
        )
        assert first.model == "tenant-model"
        assert str(seen[0].url) == "https://tenant.example/v1/chat/completions"
        assert seen[0].headers["authorization"] == f"Bearer {SECRET}"

        # A settings change bumps the version -> new endpoint id -> the transport cache rebuilds.
        store.set(
            TENANT,
            base_url="https://new.example",
            model="new-model",
            api_key=SecretStr("sk-new-SECRET"),
        )
        second = await gateway.chat(
            LLMRole.EXTRACTOR,
            messages,
            mission_id="m2",
            tenant_id=TENANT,
            prompt_version="v1",
        )
        assert second.model == "new-model"
        assert str(seen[1].url) == "https://new.example/v1/chat/completions"
        assert seen[1].headers["authorization"] == "Bearer sk-new-SECRET"

        # No tenant settings: the env/default role configuration is the fallback.
        third = await gateway.chat(
            LLMRole.EXTRACTOR,
            messages,
            mission_id="m3",
            tenant_id="tenant-b",
            prompt_version="v1",
        )
        assert third.model == "env-model"
        assert str(seen[2].url) == "http://env-default.local/v1/chat/completions"
        assert seen[2].headers["authorization"] == f"Bearer {ENV_SECRET}"
    finally:
        await gateway.close()
