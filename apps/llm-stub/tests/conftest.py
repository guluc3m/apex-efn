"""Pytest fixtures for the stub core tests (in-process via httpx.ASGITransport)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from helpers import SCENARIOS_DIR, mount_stub


@pytest.fixture
def scenarios_dir() -> Path:
    return SCENARIOS_DIR


@pytest_asyncio.fixture
async def llm_stub() -> AsyncIterator[httpx.AsyncClient]:
    client = mount_stub()
    try:
        yield client
    finally:
        await client.aclose()
