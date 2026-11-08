"""Plain helpers shared across test modules (in-process mounting, request bodies)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from llm_stub.app import create_app

SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "scenarios"


def mount_stub(scenarios_dir: str | Path | None = None) -> httpx.AsyncClient:
    """httpx client over the in-process stub app. Close with ``await client.aclose()``."""
    app = create_app(scenarios_dir if scenarios_dir is not None else SCENARIOS_DIR)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://llm-stub", timeout=30.0
    )


def chat_body(
    *,
    model: str = "stub-model",
    content: str = "hello",
    role: str = "user",
    system: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    messages.append({"role": role, "content": content})
    return {"model": model, "messages": messages, **extra}
