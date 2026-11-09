"""The D5-04 mock marketplace as a subprocess, and a ``ChatTransport`` over its mock-a JSON chat API.

Only for tests: the production transport is the browser worker (D5-01). The mock is started from the
TypeScript sources with ``tsx``. When Node or the workspace dependencies are missing the suite is skipped,
unless ``APEX_REQUIRE_MOCK_MARKETPLACE=1`` turns the skip into a failure (for the CI job that runs it).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from apex.negotiation.ports import ChatLine

REPO_ROOT = Path(__file__).resolve().parents[5]
MOCK_DIR = REPO_ROOT / "apps" / "mock-marketplace"
TSX = MOCK_DIR / "node_modules" / ".bin" / "tsx"
STARTUP_TIMEOUT_S = 30.0
SEED = 7


def _unavailable(reason: str) -> None:
    if os.environ.get("APEX_REQUIRE_MOCK_MARKETPLACE") == "1":
        pytest.fail(f"mock marketplace required but unavailable: {reason}")
    pytest.skip(f"mock marketplace unavailable: {reason}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@dataclass(frozen=True)
class MockMarketplace:
    base_url: str

    def control(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=5.0)

    def reset(self, *, persona: str, seller_id: str) -> None:
        with self.control() as c:
            c.post("/__control/reset", json={"seed": SEED}).raise_for_status()
            c.put(
                f"/__control/sellers/{seller_id}/persona", json={"persona": persona}
            ).raise_for_status()

    def chat(self, chat_id: str) -> dict[str, Any]:
        """Ground truth recorded by the mock: transcript, floor, last quote, agreement and flags."""
        with self.control() as c:
            r = c.get(f"/__control/chats/{chat_id}")
            r.raise_for_status()
            snapshot: dict[str, Any] = r.json()
            return snapshot


def start_mock_marketplace() -> Iterator[MockMarketplace]:
    node = shutil.which("node")
    if node is None:
        _unavailable("node is not installed")
    if not TSX.exists():
        _unavailable(f"{TSX.relative_to(REPO_ROOT)} is missing (run pnpm install)")

    port = _free_port()
    env = {
        **os.environ,
        "PORT": str(port),
        "HOST": "127.0.0.1",
        "MOCK_MARKETPLACE_SEED": str(SEED),
    }
    proc = subprocess.Popen(
        [str(TSX), "src/index.ts"],
        cwd=MOCK_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        while True:
            if proc.poll() is not None:
                err = proc.stderr.read().decode(errors="replace")[-2000:] if proc.stderr else ""
                _unavailable(f"process exited with {proc.returncode}: {err}")
            try:
                if httpx.get(f"{base_url}/healthz", timeout=1.0).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if time.monotonic() > deadline:
                _unavailable(f"no /healthz answer within {STARTUP_TIMEOUT_S:.0f}s")
            time.sleep(0.2)
        yield MockMarketplace(base_url)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


class MockAChatTransport:
    """``ChatTransport`` over ``/mock-a/api/conversations``. The account id is not sent to the mock."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self.chat_ids: list[str] = []

    async def open(self, *, platform: str, seller_id: str, product_id: str, account_id: str) -> str:
        assert platform == "mock-a", "this transport only speaks the mock-a JSON chat"
        r = await self._client.post(
            "/mock-a/api/conversations", json={"vendor_id": seller_id, "listing_id": product_id}
        )
        r.raise_for_status()
        chat_id: str = r.json()["conversation_id"]
        self.chat_ids.append(chat_id)
        return chat_id

    async def send(self, chat_id: str, text: str) -> None:
        r = await self._client.post(
            f"/mock-a/api/conversations/{chat_id}/messages", json={"body": text}
        )
        r.raise_for_status()

    async def read(self, chat_id: str, *, after_seq: int) -> Sequence[ChatLine]:
        r = await self._client.get(
            f"/mock-a/api/conversations/{chat_id}/messages", params={"after": after_seq}
        )
        r.raise_for_status()
        return [
            ChatLine(
                seq=m["id"],
                role="seller" if m["from"] == "vendor" else "buyer",
                text=m["body"],
            )
            for m in r.json()["messages"]
        ]
