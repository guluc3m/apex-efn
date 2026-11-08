"""Global → tenant → category resolution, deep-merge semantics and provenance."""

from __future__ import annotations

from decimal import Decimal

from apex.tenant_config.resolver import Layer, deep_merge
from apex.tenant_config.service import TenantConfigService


async def test_global_defaults_resolve_with_global_provenance(
    seeded_service: TenantConfigService,
) -> None:
    eff = await seeded_service.effective("tenant-a")
    assert eff.typed.sanity.z_gate == Decimal("6.0")
    assert eff.get("sanity.z_gate").layer is Layer.GLOBAL


async def test_tenant_override_wins_and_is_tagged_tenant(
    seeded_service: TenantConfigService,
) -> None:
    from apex.tenant_config.ports import PendingSignature  # noqa: F401

    decision_id = await seeded_service.propose_change(
        "tenant-a", {"fx": {"max_age_hours": 48}}, base_config_version=1
    )
    # Sign and apply via the fake port used by the fixture.
    port = seeded_service._decisions  # type: ignore[attr-defined]
    port.sign(decision_id)
    await seeded_service.apply_signed_change("tenant-a", decision_id, {"fx": {"max_age_hours": 48}})

    eff_a = await seeded_service.effective("tenant-a")
    eff_b = await seeded_service.effective("tenant-b")
    assert eff_a.require("fx.max_age_hours") == 48
    assert eff_a.get("fx.max_age_hours").layer is Layer.TENANT
    assert eff_b.require("fx.max_age_hours") == 36  # other tenant untouched


async def test_deep_merge_only_replaces_the_nested_key() -> None:
    base = {"sanity": {"z_ok": "3.5", "z_gate": "6.0"}, "fx": {"pivot": "EUR"}}
    out = deep_merge(base, {"sanity": {"z_gate": "7.0"}})
    assert out == {"sanity": {"z_ok": "3.5", "z_gate": "7.0"}, "fx": {"pivot": "EUR"}}
    assert base["sanity"]["z_gate"] == "6.0"  # not mutated


async def test_arrays_are_replaced_not_merged() -> None:
    out = deep_merge({"money": {"supported_currencies": ["EUR"]}}, {})
    assert out["money"]["supported_currencies"] == ["EUR"]


async def test_explicit_null_unsets_a_lower_layer_value() -> None:
    out = deep_merge(
        {"sanity": {"floor_per_unit": {"amount_minor": 1000, "currency": "EUR"}}},
        {"sanity": {"floor_per_unit": None}},
    )
    assert out["sanity"]["floor_per_unit"] is None


async def test_category_override_applies_only_to_that_category(
    seeded_service: TenantConfigService,
) -> None:
    port = seeded_service._decisions  # type: ignore[attr-defined]
    patch = {"sanity": {"min_sample": 8}}
    did = await seeded_service.propose_change(
        "tenant-a", patch, base_config_version=1, category="steel"
    )
    port.sign(did)
    await seeded_service.apply_signed_change("tenant-a", did, patch, category="steel")

    steel = await seeded_service.effective("tenant-a", "steel")
    other = await seeded_service.effective("tenant-a", "plastics")
    assert steel.require("sanity.min_sample") == 8
    assert steel.get("sanity.min_sample").layer is Layer.CATEGORY
    assert other.require("sanity.min_sample") == 5
