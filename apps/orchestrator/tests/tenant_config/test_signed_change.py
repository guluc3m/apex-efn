"""Changes are signed decisions: propose → pending → applied only after signature (fake port)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fakes import FakeDecisionPort

from apex.tenant_config.errors import ConfigValidationError
from apex.tenant_config.ports import PendingSignature
from apex.tenant_config.service import DECISION_TYPE_CONFIG_CHANGE, TenantConfigService


async def test_propose_creates_pending_decision_without_writing_version(
    seeded_service: TenantConfigService, port: FakeDecisionPort, repo
) -> None:
    did = await seeded_service.propose_change(
        "tenant-a", {"sanity": {"z_gate": "7.0"}}, base_config_version=1
    )
    assert port.decisions[did].status == "pending_signature"
    assert port.created[0]["type"] == DECISION_TYPE_CONFIG_CHANGE
    versions = await repo.list_versions("tenant-a")
    assert [v.config_version for v in versions] == [1]  # only the seed; nothing appended


async def test_payload_binds_candidate_version_and_hash(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    did = await seeded_service.propose_change(
        "tenant-a", {"sanity": {"z_gate": "7.0"}}, base_config_version=1
    )
    payload = port.decisions[did].payload
    assert payload["candidate_config_version"] == 2
    assert payload["candidate_content_hash"].startswith("sha256:")
    assert payload["patch"] == {"sanity": {"z_gate": "7.0"}}


async def test_apply_is_blocked_until_signed(
    seeded_service: TenantConfigService, port: FakeDecisionPort, repo
) -> None:
    patch = {"sanity": {"z_gate": "7.0"}}
    did = await seeded_service.propose_change("tenant-a", patch, base_config_version=1)
    with pytest.raises(PendingSignature):
        await seeded_service.apply_signed_change("tenant-a", did, patch)
    assert [v.config_version for v in await repo.list_versions("tenant-a")] == [1]


async def test_applied_after_signature(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    patch = {"sanity": {"z_gate": "7.0"}}
    did = await seeded_service.propose_change("tenant-a", patch, base_config_version=1)
    port.sign(did)
    rec = await seeded_service.apply_signed_change("tenant-a", did, patch)
    assert rec.config_version == 2
    assert rec.decision_id == did


async def test_tampered_patch_is_rejected_even_after_signature(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    did = await seeded_service.propose_change(
        "tenant-a", {"sanity": {"z_gate": "7.0"}}, base_config_version=1
    )
    port.sign(did)
    with pytest.raises(ConfigValidationError):
        await seeded_service.apply_signed_change("tenant-a", did, {"sanity": {"z_gate": "9.0"}})


async def test_decision_for_other_tenant_is_rejected(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    patch = {"sanity": {"z_gate": "7.0"}}
    did = await seeded_service.propose_change("tenant-a", patch, base_config_version=1)
    port.sign(did)
    with pytest.raises(ConfigValidationError):
        await seeded_service.apply_signed_change("tenant-b", did, patch)


async def test_criterion_5_config_half_z_gate_change_changes_classification_without_deploy(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    """Criterion 5 (config half): z_gate changes the effective value and produces a signed decision.

    The sanity engine's classification itself is DEV-3's (D3-07); here we assert the config side:
    the new effective z_gate is visible to consumers, under a new config_version, through a signed
    decision, with no code change.
    """
    before = await seeded_service.effective("tenant-a")
    patch = {"sanity": {"z_gate": "7.5"}}
    did = await seeded_service.propose_change("tenant-a", patch, base_config_version=1)
    assert port.decisions[did].type == DECISION_TYPE_CONFIG_CHANGE
    port.sign(did)
    await seeded_service.apply_signed_change("tenant-a", did, patch)
    after = await seeded_service.effective("tenant-a")
    assert before.typed.sanity.z_gate == Decimal("6.0")
    assert after.typed.sanity.z_gate == Decimal("7.5")
    assert after.config_version == before.config_version + 1
    assert after.content_hash != before.content_hash
