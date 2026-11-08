"""Run the stub with uvicorn: ``python -m llm_stub`` (port 8001 by default)."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "llm_stub.server:app",
        host=os.environ.get("LLM_STUB_HOST", "0.0.0.0"),  # noqa: S104 - container-internal stub
        port=int(os.environ.get("LLM_STUB_PORT", "8001")),
    )


if __name__ == "__main__":
    main()
