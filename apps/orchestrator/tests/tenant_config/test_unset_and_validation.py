"""Unset ("sin definir") keys are loud; invalid patches are rejected before any decision exists."""

from __future__ import annotations

import pytest
from fakes import FakeDecisionPort

from apex.tenant_config.errors import (
    ConfigKeyUnset,
    ConfigValidationError,
    NonConfigurableKeyError,
)
from apex.tenant_config.models import TenantConfig
from apex.tenant_config.service import TenantConfigService


@pytest.mark.parametrize(
    "path",
    [
        "sanity.floor_per_unit",
        "sanity.ceiling_per_unit",
        "neg.target_discount",
        "neg.max_discount",
        "approval.threshold",
        "approval.dual_control_above",
        "signing.high_value_reauth_above",
        "seller.weights",
    ],
)
async def test_unset_keys_are_marked_unset_and_raise_loudly(
    seeded_service: TenantConfigService, path: str
) -> None:
    eff = await seeded_service.effective("tenant-a")
    rv = eff.get(path)
    assert rv.unset is True
    with pytest.raises(ConfigKeyUnset) as exc:
        eff.require(path)
    assert path in str(exc.value)


async def test_unset_key_is_never_replaced_by_a_default(
    seeded_service: TenantConfigService,
) -> None:
    eff = await seeded_service.effective("tenant-a", "steel")
    assert eff.get("neg.max_discount").value is None
    with pytest.raises(ConfigKeyUnset):
        eff.require("neg.max_discount")


async def test_currency_enum_is_not_configurable(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    with pytest.raises(NonConfigurableKeyError):
        await seeded_service.propose_change(
            "tenant-a", {"money": {"supported_currencies": ["EUR", "JPY"]}}, base_config_version=1
        )
    assert port.created == []  # no decision created for a rejected patch


async def test_band_ordering_is_enforced(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    with pytest.raises(ConfigValidationError):
        await seeded_service.propose_change(
            "tenant-a", {"seller": {"band_low": 60}}, base_config_version=1
        )
    assert port.created == []


async def test_z_ok_must_be_below_z_gate(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    with pytest.raises(ConfigValidationError):
        await seeded_service.propose_change(
            "tenant-a", {"sanity": {"z_ok": "7.0"}}, base_config_version=1
        )


async def test_on_insufficient_reference_enum_rejects_other_values(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    with pytest.raises(ConfigValidationError):
        await seeded_service.propose_change(
            "tenant-a", {"sanity": {"on_insufficient_reference": "auto"}}, base_config_version=1
        )


async def test_unknown_section_is_rejected(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    with pytest.raises(ConfigValidationError):
        await seeded_service.propose_change("tenant-a", {"bogus": {"x": 1}}, base_config_version=1)


def test_typed_model_accepts_the_shipped_defaults() -> None:
    from apex.tenant_config.defaults import load_global_layer

    _, values = load_global_layer()
    TenantConfig.from_mapping(values)


def test_seller_weights_must_sum_to_one_when_set() -> None:
    from pydantic import ValidationError

    from apex.tenant_config.defaults import load_global_layer

    _, values = load_global_layer()
    values["seller"]["weights"] = {"a": 0.5, "b": 0.6}
    with pytest.raises(ValidationError):
        TenantConfig.from_mapping(values)


@pytest.mark.parametrize(
    "patch",
    [
        {"sanity": None},
        {"llm": None},
        {"fx": None},
        {"seller": {"band_low": {"x": 1}}},  # a leaf turned into an object
        {"sanity": 5},  # a section replaced by a scalar
        {"categories": {"x": {}}},  # reserved key
        {"nonexistent": {"a": 1}},
    ],
)
async def test_patches_that_change_shape_are_rejected_before_any_decision_exists(
    patch: dict, seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    """ADR-900: only leaves may be null, never a whole section. Rejected at propose time."""
    with pytest.raises(ConfigValidationError):
        await seeded_service.propose_change("tenant-a", patch, base_config_version=1)
    assert port.decisions == {}


def test_the_real_global_layer_accepts_null_only_on_leaves() -> None:
    """Guards the test above: ``_validate_merged`` alone does NOT reject ``llm.roles: null``."""
    from apex.tenant_config.defaults import load_global_layer
    from apex.tenant_config.service import _require_shape_consistent

    _, base = load_global_layer()
    _require_shape_consistent(base, {"sanity": {"floor_per_unit": None}})
    _require_shape_consistent(base, {"seller": {"weights": None}})  # unset leaf, may stay unset
    with pytest.raises(ConfigValidationError):
        _require_shape_consistent(base, {"seller": None})
