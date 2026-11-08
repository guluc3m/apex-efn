#!/usr/bin/env bash
# Integration tests (Testcontainers: Postgres, Redis, ...) for the orchestrator (D1-04).
# Runs only when at least one test is marked integration. pytest exit code 5 ("no tests
# collected") is a skip; any other non-zero exit code is a failure.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../../apps/orchestrator"

if ! grep -rqE "mark\.integration" tests; then
  echo "SKIP: no test under apps/orchestrator/tests is marked integration yet"
  exit 0
fi

set +e
uv run pytest -m integration -o markers=integration
status=$?
set -e

if [ "${status}" -eq 5 ]; then
  echo "SKIP: pytest collected no integration tests (exit 5)"
  exit 0
fi
exit "${status}"
