"""``NegotiationParamsResolver``: the caller's half of the negotiation contract (D5-07b).

Every limit comes from the tenant's effective config; an unset key raises instead of defaulting, which is
ADR-900 Q7. The discounts are converted with the engine's own ``fraction_to_bp`` so the guardrail can never be
looser than the configured limit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from apex.agents.negotiation_params import (
    DbAccountResolver,
    NegotiationNotConfigured,
    NegotiationParamsResolver,
    UnwiredAccountResolver,
)
from apex.agents.offers import InMemoryOfferStore, Offer
from apex.common.clock import FixedClock
from apex.negotiation.node import OfferInput
from apex.negotiation.text import Counterpart
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.service import TenantConfigService

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"


class _Accounts:
    def __init__(self, account_id: str = "acct-1") -> None:
        self.account_id = account_id
        self.calls: list[dict[str, str]] = []

    async def account_for(self, *, tenant_id: str, platform: str) -> str:
        self.calls.append({"tenant_id": tenant_id, "platform": platform})
        return self.account_id


async def _seed_config(service: TenantConfigService, port: Any, patch: dict[str, Any]) -> None:
    """Give the tenant a stored baseline with the negotiation keys set (they are unset by default)."""
    from apex.tenant_config.load_defaults import seed

    await seed([TENANT], service._repo)  # type: ignore[attr-defined]
    decision = await service.propose_change(TENANT, patch, base_config_version=1)
    port.sign(decision)
    await service.apply_signed_change(TENANT, decision, patch)


def _service() -> tuple[TenantConfigService, Any]:
    from fakes import FakeDecisionPort

    port = FakeDecisionPort()
    return (
        TenantConfigService(InMemoryConfigRepository(), port, FixedClock(NOW)),  # type: ignore[arg-type]
        port,
    )


def _offer(**overrides: Any) -> Offer:
    base: dict[str, Any] = {
        "id": "mock-a:a-1",
        "tenant_id": TENANT,
        "mission_id": "m-1",
        "platform_id": "mock-a",
        "seller_id": "s-1",
        "product_id": "p-1",
        "unit_price_eur_minor": 445,
        "list_price_eur_minor": None,
        "currency": "EUR",
        "quantity": 500,
        "collected_at": NOW,
        "raw_signals": {"title": "Nitrile Gloves Size M"},
    }
    return Offer(**{**base, **overrides})


def _input() -> OfferInput:
    return OfferInput(
        offer_id="mock-a:a-1", platform="mock-a", seller_id="s-1", platform_offer_id="a-1"
    )


async def _resolver(
    *, patch: dict[str, Any] | None = None, offer: Offer | None = None
) -> tuple[NegotiationParamsResolver, _Accounts]:
    config, port = _service()
    await _seed_config(
        config,
        port,
        patch
        or {
            "neg": {
                "target_discount": "0.08",
                "max_discount": "0.15",
                "allowed_counterparts": ["higher_volume"],
            }
        },
    )
    offers = InMemoryOfferStore()
    await offers.add(offer or _offer())
    accounts = _Accounts()
    return NegotiationParamsResolver(config=config, offers=offers, accounts=accounts), accounts


# ----- the happy path ----------------------------------------------------------------------------


async def test_every_limit_comes_from_the_tenant_config() -> None:
    resolver, _ = await _resolver()
    params, version, account_id = await resolver(_input(), TENANT)
    assert params.currency == "EUR"
    assert params.reference_price_minor == 445
    assert params.quantity == 500
    assert params.target_discount_bp == 800  # 0.08
    assert params.max_discount_bp == 1500  # 0.15
    assert params.max_rounds == 6
    assert params.max_tokens == 20_000
    assert params.max_messages_per_hour == 20
    assert params.max_message_chars == 1200
    assert params.allowed_counterparts == {Counterpart.HIGHER_VOLUME}
    assert params.supported_currencies == {"EUR", "USD", "CNY"}
    assert account_id == "acct-1"
    assert version.startswith("v2:sha256:")


async def test_phase1_is_semi_automatic_by_default() -> None:
    """Spec §10: every drafted message waits for a human in Phase 1."""
    resolver, _ = await _resolver()
    params, _, _ = await resolver(_input(), TENANT)
    assert params.semi_automatic is True


async def test_the_context_carries_the_product_title_and_no_financial_data() -> None:
    resolver, _ = await _resolver()
    params, _, _ = await resolver(_input(), TENANT)
    assert params.context.product_title == "Nitrile Gloves Size M"
    dumped = params.context.model_dump()
    assert "price" not in str(dumped).lower()


async def test_the_account_is_resolved_per_platform() -> None:
    resolver, accounts = await _resolver()
    await resolver(_input(), TENANT)
    assert accounts.calls == [{"tenant_id": TENANT, "platform": "mock-a"}]


# ----- loud failures -----------------------------------------------------------------------------


async def test_an_unset_discount_is_a_loud_error_not_a_default() -> None:
    """ADR-900 Q7: neg.* stays unset in /config/defaults and a mission cannot negotiate without it."""
    config, _ = _service()
    from apex.tenant_config.load_defaults import seed

    await seed([TENANT], config._repo)  # type: ignore[attr-defined]
    offers = InMemoryOfferStore()
    await offers.add(_offer())
    resolver = NegotiationParamsResolver(config=config, offers=offers, accounts=_Accounts())
    with pytest.raises(NegotiationNotConfigured, match="neg.target_discount"):
        await resolver(_input(), TENANT)


async def test_a_target_above_the_maximum_is_refused_before_it_reaches_the_engine() -> None:
    """The config model already rejects it, so the resolver's own check is defence in depth."""
    from apex.tenant_config.errors import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="target_discount must be <= neg.max_discount"):
        await _resolver(patch={"neg": {"target_discount": "0.20", "max_discount": "0.10"}})


async def test_an_unknown_offer_is_refused() -> None:
    resolver, _ = await _resolver()
    with pytest.raises(NegotiationNotConfigured, match="not stored"):
        await resolver(
            OfferInput(offer_id="nope", platform="mock-a", seller_id="s-1", platform_offer_id="x"),
            TENANT,
        )


async def test_an_unwired_account_resolver_fails_loudly() -> None:
    config, port = _service()
    await _seed_config(config, port, {"neg": {"target_discount": "0.08", "max_discount": "0.15"}})
    offers = InMemoryOfferStore()
    await offers.add(_offer())
    resolver = NegotiationParamsResolver(
        config=config, offers=offers, accounts=UnwiredAccountResolver()
    )
    with pytest.raises(NotImplementedError, match="no account resolver"):
        await resolver(_input(), TENANT)


async def test_the_discount_is_rounded_down_so_the_guardrail_is_never_looser() -> None:
    """0.085 must not become 850 bp if that would be looser than the config; fraction_to_bp floors."""
    resolver, _ = await _resolver(
        patch={"neg": {"target_discount": "0.085", "max_discount": "0.155"}}
    )
    params, _, _ = await resolver(_input(), TENANT)
    assert params.target_discount_bp == 850
    assert params.max_discount_bp == 1550


# ----- autonomous mode (D5-11) -------------------------------------------------------------------


class _Flags:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.calls: list[tuple[str, dict[str, str]]] = []

    def is_enabled(self, name: str, context: dict[str, str] | None = None) -> bool:
        self.calls.append((name, dict(context or {})))
        return self.enabled

    def is_platform_enabled(self, platform_id: str) -> bool:
        return True


async def test_phase_1_is_semi_automatic_when_the_flag_is_absent() -> None:
    """Spec §10: every drafted message waits for a human unless the tenant opts in."""
    resolver, _ = await _resolver()
    params, _, _ = await resolver(_input(), TENANT)
    assert params.semi_automatic is True


async def test_the_autonomous_send_flag_turns_off_the_approval_step() -> None:
    config, port = _service()
    await _seed_config(config, port, {"neg": {"target_discount": "0.08", "max_discount": "0.15"}})
    offers = InMemoryOfferStore()
    await offers.add(_offer())
    flags = _Flags(enabled=True)
    resolver = NegotiationParamsResolver(
        config=config, offers=offers, accounts=_Accounts(), flags=flags
    )
    params, _, _ = await resolver(_input(), TENANT)
    assert params.semi_automatic is False
    assert flags.calls == [("negotiation.autonomous_send", {"tenant_id": TENANT})]


# ----- DbAccountResolver (issue #370) --------------------------------------------------------------


class _Session:
    def __init__(self, found: str | None) -> None:
        self.found = found
        self.statement: object = None

    async def scalar(self, statement: object) -> str | None:
        self.statement = statement
        return self.found


def _scope(session: _Session) -> Callable[[str], AbstractAsyncContextManager[Any]]:
    @asynccontextmanager
    async def scope(tenant_id: str) -> AsyncIterator[Any]:
        yield session

    return scope


async def test_db_account_resolver_returns_the_active_account_id() -> None:
    session = _Session("acc-1")
    resolver = DbAccountResolver(_scope(session))
    assert await resolver.account_for(tenant_id="t1", platform="mock-a") == "acc-1"
    sql = str(session.statement)
    assert "connected_accounts.platform" in sql and "connected_accounts.status" in sql


async def test_db_account_resolver_fails_loudly_without_an_account() -> None:
    resolver = DbAccountResolver(_scope(_Session(None)))
    with pytest.raises(NegotiationNotConfigured, match="mock-a"):
        await resolver.account_for(tenant_id="t1", platform="mock-a")
