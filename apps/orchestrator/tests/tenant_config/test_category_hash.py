"""Category overrides are part of the version identity (ADR-900, issue #96 item 2)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fakes import FakeDecisionPort

from apex.tenant_config.errors import ConfigValidationError, ContentHashMismatchError
from apex.tenant_config.service import TenantConfigService

CAT_PATCH = {"sanity": {"z_gate": "7.5"}}


async def _apply(
    service: TenantConfigService,
    port: FakeDecisionPort,
    patch: dict,
    *,
    base: int,
    category: str | None = None,
) -> int:
    did = await service.propose_change(
        "tenant-a", patch, base_config_version=base, category=category
    )
    port.sign(did)
    record = await service.apply_signed_change("tenant-a", did, patch, category=category)
    return record.config_version


async def test_a_category_patch_changes_the_content_hash(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    before = (await seeded_service.effective("tenant-a")).content_hash
    version = await _apply(seeded_service, port, CAT_PATCH, base=1, category="steel")
    after = (await seeded_service.effective("tenant-a")).content_hash
    assert version == 2
    assert after != before, "a category override must change the version's content hash"


async def test_effective_view_for_a_category_hashes_what_that_category_sees(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    await _apply(seeded_service, port, CAT_PATCH, base=1, category="steel")
    steel = await seeded_service.effective("tenant-a", "steel")
    wood = await seeded_service.effective("tenant-a", "wood")
    assert steel.config_version == wood.config_version == 2
    assert steel.typed.sanity.z_gate == Decimal("7.5")
    assert wood.typed.sanity.z_gate == Decimal("6.0")
    assert steel.content_hash != wood.content_hash


async def test_two_different_category_overrides_have_different_hashes(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    await _apply(seeded_service, port, {"sanity": {"z_gate": "7.5"}}, base=1, category="steel")
    first = (await seeded_service.effective("tenant-a")).content_hash
    await _apply(seeded_service, port, {"sanity": {"z_gate": "8.0"}}, base=2, category="steel")
    assert (await seeded_service.effective("tenant-a")).content_hash != first


async def test_stored_version_hash_verifies_including_categories(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    await _apply(seeded_service, port, CAT_PATCH, base=1, category="steel")
    await seeded_service.verify_version("tenant-a", 2)  # must not raise


async def test_tampering_with_a_stored_category_override_is_detected(
    seeded_service: TenantConfigService, port: FakeDecisionPort, repo
) -> None:
    await _apply(seeded_service, port, CAT_PATCH, base=1, category="steel")
    record = await repo.get_version("tenant-a", 2)
    record.values["categories"]["steel"]["sanity"]["z_gate"] = "99.0"  # type: ignore[index]
    with pytest.raises(ContentHashMismatchError):
        await seeded_service.verify_version("tenant-a", 2)


@pytest.mark.parametrize(
    "bad",
    [
        {"sanity": {"z_gate": "1.0"}},  # z_ok (3.5) must stay below z_gate
        {"sanity": {"min_sample": 0}},
        {"sanity": {"z_gate": "high"}},
        {"neg": {"max_rounds": -1}},
    ],
)
async def test_invalid_category_patch_is_rejected_at_propose_time(
    bad: dict, seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    with pytest.raises(ConfigValidationError):
        await seeded_service.propose_change(
            "tenant-a", bad, base_config_version=1, category="steel"
        )
    assert port.decisions == {}


async def test_category_patch_is_validated_again_at_apply_time(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    """A decision signed for a valid patch cannot be replayed against another category's shape or state."""
    patch = {"sanity": {"z_gate": "7.5"}}
    did = await seeded_service.propose_change(
        "tenant-a", patch, base_config_version=1, category="steel"
    )
    port.sign(did)
    # The signed payload says category=steel; applying it as another category must be refused.
    with pytest.raises(ConfigValidationError, match="category"):
        await seeded_service.apply_signed_change("tenant-a", did, patch, category="wood")
