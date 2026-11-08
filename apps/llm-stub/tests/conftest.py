"""Pytest configuration: the ``llm_stub`` fixture comes from the ``llm_stub.testing`` plugin."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import SCENARIOS_DIR

pytest_plugins = ["llm_stub.testing"]


@pytest.fixture
def scenarios_dir() -> Path:
    return SCENARIOS_DIR
