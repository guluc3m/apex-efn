#!/usr/bin/env bash
# LLM stub job (D4-02): the OpenAI-compatible stub in apps/llm-stub is its own uv project, separate
# from the orchestrator. Lint, format, types and tests. No coverage gate: the stub is test
# infrastructure, not product code (its tests already cover the scenarios, matching and endpoints).
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_cmd uv "install uv ${UV_VERSION:-0.13.7} (https://docs.astral.sh/uv/)"

cd apps/llm-stub

uv sync --locked --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
