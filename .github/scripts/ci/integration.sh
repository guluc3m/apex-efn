#!/usr/bin/env bash
# Integration tests (Testcontainers: Postgres, Redis, ...) for the orchestrator (D1-04).
# SKIP until a test is marked integration. Once one exists, Docker is required: no Docker means FAIL.
# pytest exit code 5 ("no tests collected") counts as a skip; any other non-zero exit code is a failure.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if ! grep -rqE "mark\.integration" apps/orchestrator/tests; then
  skip "no test under apps/orchestrator/tests is marked integration yet"
fi

require_cmd uv "install uv and run uv sync --locked --dev in apps/orchestrator"
require_docker "Testcontainers integration tests"

cd apps/orchestrator
set +e
uv run pytest -m integration -o markers=integration
status=$?
set -e

if [ "${status}" -eq 5 ]; then
  skip "pytest collected no integration tests (exit 5)"
fi
exit "${status}"
