"""Monotonic config_version, append-only history and content hash reproducibility."""

from __future__ import annotations

import pytest
from fakes import FakeDecisionPort

from apex.tenant_config.errors import (
    ContentHashMismatchError,
    StaleBaseVersionError,
    TenantConfigError,
)
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.service import TenantConfigService


async def _change(
    svc: TenantConfigService, port: FakeDecisionPort, tenant: str, base: int, patch: dict
) -> int:
    did = await svc.propose_change(tenant, patch, base_config_version=base)
    port.sign(did)
    rec = await svc.apply_signed_change(tenant, did, patch)
    return rec.config_version


async def test_versions_are_monotonic_by_one(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    v2 = await _change(seeded_service, port, "tenant-a", 1, {"fx": {"max_age_hours": 40}})
    v3 = await _change(seeded_service, port, "tenant-a", 2, {"fx": {"max_age_hours": 41}})
    assert (v2, v3) == (2, 3)


async def test_stale_base_version_is_rejected(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    await _change(seeded_service, port, "tenant-a", 1, {"fx": {"max_age_hours": 40}})
    with pytest.raises(StaleBaseVersionError):
        await seeded_service.propose_change(
            "tenant-a", {"fx": {"max_age_hours": 41}}, base_config_version=1
        )


async def test_history_is_append_only(
    seeded_service: TenantConfigService, port: FakeDecisionPort, repo: InMemoryConfigRepository
) -> None:
    await _change(seeded_service, port, "tenant-a", 1, {"fx": {"max_age_hours": 40}})
    versions = await repo.list_versions("tenant-a")
    assert [v.config_version for v in versions] == [1, 2]
    with pytest.raises(TenantConfigError):  # non-monotonic append rejected
        await repo.append_version(versions[0])


async def test_hash_is_reproducible_for_same_effective_values(
    seeded_service: TenantConfigService,
) -> None:
    a = await seeded_service.effective("tenant-a")
    b = await seeded_service.effective("tenant-a")
    assert a.content_hash == b.content_hash
    assert a.content_hash.startswith("sha256:") and len(a.content_hash) == len("sha256:") + 64


async def test_hash_changes_when_effective_value_changes(
    seeded_service: TenantConfigService, port: FakeDecisionPort
) -> None:
    before = await seeded_service.effective("tenant-a")
    await _change(seeded_service, port, "tenant-a", 1, {"sanity": {"z_gate": 7.0}})
    after = await seeded_service.effective("tenant-a")
    assert before.content_hash != after.content_hash
    assert after.config_version == 2


async def test_stored_version_hash_verifies(
    seeded_service: TenantConfigService, port: FakeDecisionPort, repo: InMemoryConfigRepository
) -> None:
    await _change(seeded_service, port, "tenant-a", 1, {"sanity": {"z_gate": 7.0}})
    await seeded_service.verify_version("tenant-a", 2)


async def test_tampered_stored_hash_is_detected(
    seeded_service: TenantConfigService, port: FakeDecisionPort, repo: InMemoryConfigRepository
) -> None:
    from dataclasses import replace

    await _change(seeded_service, port, "tenant-a", 1, {"sanity": {"z_gate": 7.0}})
    rows = repo._versions["tenant-a"]  # type: ignore[attr-defined]
    rows[-1] = replace(rows[-1], values={"sanity": {"z_gate": 9.0}})
    with pytest.raises(ContentHashMismatchError):
        await seeded_service.verify_version("tenant-a", 2)
