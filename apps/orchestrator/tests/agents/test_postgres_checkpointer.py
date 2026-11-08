"""The graph resumes from a real Postgres checkpoint (needs Docker; skipped when unavailable)."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from typing import Any

import pytest

from apex.agents.checkpointer import postgres_checkpointer
from apex.agents.offer_graph import build_offer_graph, initial_state, thread_id
from tests.agents.fakes import TENANT, make_rig


def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="docker not available")


@pytest.fixture(scope="module")
def dsn() -> Iterator[str]:
    from testcontainers.postgres import PostgresContainer  # noqa: I001

    with PostgresContainer("postgres:16-alpine", driver=None) as pg:
        yield pg.get_connection_url()


async def test_resume_from_postgres_after_a_new_graph_instance(dsn: str) -> None:
    from langgraph.types import Command

    rig = make_rig()
    config: Any = {"configurable": {"thread_id": thread_id("m-pg", "o-pg")}}
    state = initial_state(mission_id="m-pg", offer_id="o-pg", tenant_id=TENANT, offer={})

    async with postgres_checkpointer(dsn, setup=True) as saver:
        first = await build_offer_graph(rig.deps, checkpointer=saver).ainvoke(state, config)
        assert first["__interrupt__"]

    rig.decisions.sign(rig.decisions.pending_id(), action="approve")
    async with postgres_checkpointer(dsn) as saver:
        final = await build_offer_graph(rig.deps, checkpointer=saver).ainvoke(
            Command(resume=True), config
        )
    assert final["status"] == "purchased"
    assert rig.calls["negotiation"] == 1
