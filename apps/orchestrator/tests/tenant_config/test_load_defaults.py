"""CLI: validates the v1 defaults for given tenants and is idempotent; persists nothing (no DB yet)."""

from __future__ import annotations

import pytest

from apex.tenant_config import load_defaults
from apex.tenant_config.repository import InMemoryConfigRepository


async def test_seed_writes_baseline_v1_and_is_idempotent() -> None:
    repo = InMemoryConfigRepository()
    first = await load_defaults.seed(["t1", "t2"], repo)
    second = await load_defaults.seed(["t1", "t2"], repo)
    assert [r.config_version for r in first] == [1, 1]
    assert second == []
    assert (await repo.latest_version("t1")).config_version == 1  # type: ignore[union-attr]


def test_main_with_args_returns_zero_and_warns_no_db(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        rc = load_defaults.main(["tenant-x"])
    assert rc == 0
    assert any("no database repository" in m for m in caplog.messages)


def test_main_reads_env_when_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX-EFN_TENANT_IDS", "a, b ,a")
    assert load_defaults._tenant_ids([]) == ["a", "b"]


def test_main_without_tenants_is_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX-EFN_TENANT_IDS", raising=False)
    assert load_defaults.main([]) == 2
