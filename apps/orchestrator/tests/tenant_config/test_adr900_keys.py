"""ADR-900 decisions for tenant config: no hidden defaults, Phase 1 counterparts, decimals, demo seed."""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import pytest
from fakes import FakeDecisionPort
from pydantic import ValidationError

from apex.tenant_config.defaults import load_global_layer
from apex.tenant_config.errors import ConfigValidationError
from apex.tenant_config.load_defaults import DEMO_VALUES, seed
from apex.tenant_config.models import Money, TenantConfig
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.resolver import deep_merge
from apex.tenant_config.service import TenantConfigService


def _global() -> dict[str, Any]:
    return load_global_layer()[1]


def _drop(path: str) -> dict[str, Any]:
    data = copy.deepcopy(_global())
    *parents, leaf = path.split(".")
    node = data
    for part in parents:
        node = node[part]
    del node[leaf]
    return data


# ----- a missing key fails loudly: nothing in the model supplies a default ---------------------------


@pytest.mark.parametrize(
    "path",
    [
        "fx.pivot",
        "sanity.on_insufficient_reference",
        "sanity.reference_weights",
        "seller.min_accepted_band",
        "seller.escalate_cheap_low_confidence",
        "money.supported_currencies",
        "neg.allowed_counterparts",
        "neg.max_tokens_per_conversation",
        "neg.max_messages_per_hour_per_account",
        "neg.max_message_chars",
        "constraints.require_escrow",
        "supervisor.stuck_after_minutes",
        "supervisor.degrade_on_budget_exhausted",
        "finance.stale_after_days",
    ],
)
def test_a_missing_key_is_an_error_not_a_silent_default(path: str) -> None:
    with pytest.raises(ValidationError, match=path.split(".")[-1]):
        TenantConfig.from_mapping(_drop(path))


def test_a_missing_section_is_an_error() -> None:
    for section in ("landed", "constraints", "supervisor"):
        data = _global()
        del data[section]
        with pytest.raises(ValidationError):
            TenantConfig.from_mapping(data)


# ----- Q12: insufficient_reference always goes to the gate -------------------------------------------


@pytest.mark.parametrize("value", ["negotiate", "", "GATE", None])
def test_on_insufficient_reference_only_accepts_gate(value: Any) -> None:
    data = deep_merge(_global(), {"sanity": {"on_insufficient_reference": value}})
    with pytest.raises(ValidationError):
        TenantConfig.from_mapping(data)


# ----- Q15: Phase 1 counterparts -----------------------------------------------------------------------


def test_phase1_counterparts_are_allowed() -> None:
    cfg = TenantConfig.from_mapping(
        deep_merge(
            _global(), {"neg": {"allowed_counterparts": ["higher_volume", "framework_contract"]}}
        )
    )
    assert [c.value for c in cfg.neg.allowed_counterparts] == [
        "higher_volume",
        "framework_contract",
    ]


@pytest.mark.parametrize("value", ["prepayment", "payment_terms", "guarantee", "penalty"])
def test_later_phase_counterparts_cannot_be_enabled(value: str) -> None:
    data = deep_merge(_global(), {"neg": {"allowed_counterparts": ["higher_volume", value]}})
    with pytest.raises(ValidationError, match="Phase 2"):
        TenantConfig.from_mapping(data)


def test_counterparts_default_to_none_and_cannot_repeat() -> None:
    assert TenantConfig.from_mapping(_global()).neg.allowed_counterparts == ()
    data = deep_merge(
        _global(), {"neg": {"allowed_counterparts": ["higher_volume", "higher_volume"]}}
    )
    with pytest.raises(ValidationError, match="repeat"):
        TenantConfig.from_mapping(data)


# ----- ADR-900 defaults ----------------------------------------------------------------------------------


def test_adr900_defaults() -> None:
    cfg = TenantConfig.from_mapping(_global())
    assert cfg.supervisor.stuck_after_minutes == 30
    assert cfg.supervisor.degrade_on_budget_exhausted is True
    assert cfg.neg.max_tokens_per_conversation == 20000
    assert cfg.neg.max_messages_per_hour_per_account == 20
    assert cfg.neg.max_message_chars == 1200
    assert cfg.constraints.require_escrow is False
    ref = cfg.sanity.reference_weights
    assert (ref.mission, ref.history, ref.benchmark) == (
        Decimal("0.5"),
        Decimal("0.3"),
        Decimal("0.2"),
    )
    assert sorted(cfg.llm.roles or {}) == [
        "embedder",
        "extractor",
        "narrator",
        "negotiator",
        "planner",
    ]


def test_reference_weights_must_sum_to_one() -> None:
    data = deep_merge(_global(), {"sanity": {"reference_weights": {"mission": "0.6"}}})
    with pytest.raises(ValidationError, match="sum to 1"):
        TenantConfig.from_mapping(data)


def test_landed_cost_inputs_and_cost_of_capital_start_unset_not_zero() -> None:
    cfg = TenantConfig.from_mapping(_global())
    assert cfg.landed.duty_rate is None
    assert cfg.landed.import_vat_rate is None
    assert cfg.finance.cost_of_capital_rate is None


# ----- decimals and money: no floats ----------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0.08, 0.5, True])
def test_a_float_is_rejected_for_a_rate(bad: Any) -> None:
    with pytest.raises(ValidationError, match="never a float"):
        TenantConfig.from_mapping(deep_merge(_global(), {"neg": {"max_discount": bad}}))


def test_rates_are_parsed_as_exact_decimals() -> None:
    cfg = TenantConfig.from_mapping(
        deep_merge(_global(), {"neg": {"target_discount": "0.08", "max_discount": "0.15"}})
    )
    assert cfg.neg.target_discount == Decimal("0.08")
    assert cfg.neg.max_discount == Decimal("0.15")
    assert isinstance(cfg.neg.max_discount, Decimal)


def test_a_rate_serializes_as_a_string_not_a_float() -> None:
    cfg = TenantConfig.from_mapping(deep_merge(_global(), {"neg": {"max_discount": "0.15"}}))
    assert cfg.model_dump(mode="json")["neg"]["max_discount"] == "0.15"


@pytest.mark.parametrize("bad", ["nan", "inf", "abc", "", "1,5"])
def test_malformed_decimals_are_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        TenantConfig.from_mapping(deep_merge(_global(), {"neg": {"max_discount": bad}}))


def test_money_is_integer_minor_units_with_a_closed_currency() -> None:
    assert Money(amount_minor=500_000, currency="EUR").amount_minor == 500_000
    for bad in (
        {"amount_minor": 5000.5, "currency": "EUR"},
        {"amount_minor": 5000.0, "currency": "EUR"},
        {"amount_minor": -1, "currency": "EUR"},
        {"amount_minor": 1, "currency": "GBP"},
        {"amount_minor": 1},
        {"amount_minor": 1, "currency": "EUR", "extra": 1},
    ):
        with pytest.raises(ValidationError):
            Money.model_validate(bad)


def test_a_bare_number_is_not_accepted_where_money_is_expected() -> None:
    for path in (
        {"approval": {"threshold": 5000}},
        {"signing": {"high_value_reauth_above": 10000.0}},
        {"sanity": {"floor_per_unit": 1.5}},
    ):
        with pytest.raises(ValidationError):
            TenantConfig.from_mapping(deep_merge(_global(), path))


def test_floor_and_ceiling_are_eur_and_ordered() -> None:
    ok = {
        "floor_per_unit": {"amount_minor": 100, "currency": "EUR"},
        "ceiling_per_unit": {"amount_minor": 900, "currency": "EUR"},
    }
    TenantConfig.from_mapping(deep_merge(_global(), {"sanity": ok}))
    with pytest.raises(ValidationError, match="<="):
        TenantConfig.from_mapping(
            deep_merge(
                _global(),
                {
                    "sanity": {
                        "floor_per_unit": {"amount_minor": 900, "currency": "EUR"},
                        "ceiling_per_unit": {"amount_minor": 100, "currency": "EUR"},
                    }
                },
            )
        )
    with pytest.raises(ValidationError, match="EUR"):
        TenantConfig.from_mapping(
            deep_merge(
                _global(), {"sanity": {"floor_per_unit": {"amount_minor": 100, "currency": "USD"}}}
            )
        )


def test_approval_amounts_must_share_a_currency_and_be_ordered() -> None:
    with pytest.raises(ValidationError, match="currency"):
        TenantConfig.from_mapping(
            deep_merge(
                _global(),
                {
                    "approval": {
                        "threshold": {"amount_minor": 1, "currency": "EUR"},
                        "dual_control_above": {"amount_minor": 2, "currency": "USD"},
                    }
                },
            )
        )
    with pytest.raises(ValidationError, match=">="):
        TenantConfig.from_mapping(
            deep_merge(
                _global(),
                {
                    "approval": {
                        "threshold": {"amount_minor": 500, "currency": "EUR"},
                        "dual_control_above": {"amount_minor": 100, "currency": "EUR"},
                    }
                },
            )
        )


async def test_a_float_patch_is_rejected_before_any_decision_exists(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    with pytest.raises(ConfigValidationError, match="float"):
        await seeded_service.propose_change(
            "tenant-a", {"neg": {"max_discount": 0.15}}, base_config_version=1
        )
    assert port.decisions == {}


# ----- demo seed (Q7) ----------------------------------------------------------------------------------------


async def test_demo_values_are_seeded_for_the_two_demo_tenants_only(
    clock: Any, port: FakeDecisionPort
) -> None:
    repo = InMemoryConfigRepository()
    await seed(["tenant-a", "tenant-b", "tenant-c"], repo, demo_values=True)
    service = TenantConfigService(repo, port, clock)

    for tenant in ("tenant-a", "tenant-b"):
        eff = await service.effective(tenant)
        assert eff.typed.neg.target_discount == Decimal("0.08")
        assert eff.typed.neg.max_discount == Decimal("0.15")
        assert eff.typed.approval.threshold == Money(amount_minor=500_000, currency="EUR")
        assert eff.typed.approval.dual_control_above == Money(
            amount_minor=2_000_000, currency="EUR"
        )
        assert eff.typed.signing.high_value_reauth_above == Money(
            amount_minor=1_000_000, currency="EUR"
        )

    other = await service.effective("tenant-c")
    assert other.typed.neg.max_discount is None  # a real tenant must set it in onboarding
    assert other.typed.approval.threshold is None
    assert other.get("neg.max_discount").unset


async def test_demo_values_are_off_unless_asked_for(clock: Any, port: FakeDecisionPort) -> None:
    repo = InMemoryConfigRepository()
    await seed(["tenant-a"], repo)
    eff = await TenantConfigService(repo, port, clock).effective("tenant-a")
    assert eff.typed.neg.max_discount is None


async def test_seeded_versions_verify_with_their_hash(clock: Any, port: FakeDecisionPort) -> None:
    repo = InMemoryConfigRepository()
    await seed(["tenant-a", "tenant-c"], repo, demo_values=True)
    service = TenantConfigService(repo, port, clock)
    await service.verify_version("tenant-a", 1)
    await service.verify_version("tenant-c", 1)
    a = (await service.effective("tenant-a")).content_hash
    c = (await service.effective("tenant-c")).content_hash
    assert a != c  # the demo values are part of tenant-a's identity


def test_demo_values_are_valid_and_decimal_only() -> None:
    from apex.tenant_config.resolver import assert_no_floats

    assert_no_floats(DEMO_VALUES)
    TenantConfig.from_mapping(deep_merge(_global(), copy.deepcopy(DEMO_VALUES)))  # type: ignore[arg-type]
