"""In-process test helpers for mounting the stub without a network socket.

Usage from another package's tests (D4-04 gateway tests)::

    from llm_stub.testing import StubClient

    async def test_something(llm_stub: StubClient) -> None:
        resp = await llm_stub.post("/v1/chat/completions", json=body,
                                   headers={"X-Stub-Scenario": "no-json-schema"})

The ``llm_stub`` fixture is provided by the ``llm_stub.testing`` pytest plugin. Register it with
``pytest_plugins = ["llm_stub.testing"]`` in a conftest, or install the package and use
``-p llm_stub.testing``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from llm_stub.app import create_app

DEFAULT_SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"


class StubClient:
    """Thin wrapper over ``httpx.AsyncClient`` bound to the in-process ASGI app.

    ``base_url`` is ``http://llm-stub`` (any host works; no socket is opened).
    """

    def __init__(self, client: httpx.AsyncClient, app: Any) -> None:
        self._client = client
        self.app = app

    @property
    def base_url(self) -> str:
        return str(self._client.base_url).rstrip("/")

    @property
    def http(self) -> httpx.AsyncClient:
        """The underlying client, for passing to code that expects an ``httpx.AsyncClient``."""
        return self._client

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._client.post(path, **kwargs)

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._client.get(path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._client.delete(path, **kwargs)

    async def reset(self) -> None:
        """Reset per-scenario counters and clear the call log (``POST /_stub/reset``)."""
        resp = await self._client.post("/_stub/reset")
        resp.raise_for_status()

    async def calls(self) -> list[dict[str, Any]]:
        """Return the received-request log (``GET /_stub/calls``)."""
        resp = await self._client.get("/_stub/calls")
        resp.raise_for_status()
        calls: list[dict[str, Any]] = resp.json()["calls"]
        return calls

    async def clear_calls(self) -> None:
        resp = await self._client.delete("/_stub/calls")
        resp.raise_for_status()


def mount_stub(scenarios_dir: str | Path | None = None) -> httpx.AsyncClient:
    """Build an ``httpx.AsyncClient`` whose transport calls the stub app in-process.

    Must be used inside an async context. Close with ``await client.aclose()``.
    """
    app = create_app(scenarios_dir if scenarios_dir is not None else DEFAULT_SCENARIOS_DIR)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://llm-stub", timeout=30.0)


@pytest.fixture
def llm_stub_scenarios_dir() -> Path:
    """Override this fixture in a test package to point at custom scenario fixtures."""
    return DEFAULT_SCENARIOS_DIR


@pytest_asyncio.fixture
async def llm_stub(llm_stub_scenarios_dir: Path) -> AsyncIterator[StubClient]:
    """In-process stub. Counters are fresh per test."""
    app = create_app(llm_stub_scenarios_dir)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://llm-stub", timeout=30.0
    )
    try:
        yield StubClient(client, app)
    finally:
        await client.aclose()
