"""Fixtures for tenant_config tests. Fakes live in ``fakes.py``."""

from __future__ import annotations

import pytest
from fakes import FakeDecisionPort, FixedClock

from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.service import TenantConfigService


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def port() -> FakeDecisionPort:
    return FakeDecisionPort()


@pytest.fixture
def repo() -> InMemoryConfigRepository:
    return InMemoryConfigRepository()


@pytest.fixture
def service(
    repo: InMemoryConfigRepository, port: FakeDecisionPort, clock: FixedClock
) -> TenantConfigService:
    return TenantConfigService(repo, port, clock)


@pytest.fixture
async def seeded_service(
    service: TenantConfigService, repo: InMemoryConfigRepository
) -> TenantConfigService:
    from apex.tenant_config.load_defaults import seed

    await seed(["tenant-a", "tenant-b"], repo)
    return service
