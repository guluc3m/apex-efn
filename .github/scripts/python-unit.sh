#!/usr/bin/env bash
# Unit tests and coverage gate for the orchestrator (D1-04).
# Integration tests (Testcontainers) are excluded here and run by python-integration.sh.
# Coverage targets are added only when their code exists, so the gate switches on by itself.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../../apps/orchestrator"

THRESHOLD=80
# "<module to measure>|<glob that activates the target>"
# A target activates when a real module exists, not just the empty __init__.py that creates the package.
# negotiation/guardrails* is a set of files, not a package: the whole negotiation package is measured
# once any guardrail file exists (the gate is coarser than specified; see the D1-04 report).
TARGETS=(
  "apex.domain|src/apex/domain/*.py"
  "apex.signing|src/apex/signing/*.py"
  "apex.negotiation|src/apex/negotiation/guardrails*.py"
)

cov_args=()
for target in "${TARGETS[@]}"; do
  module="${target%%|*}"
  glob="${target#*|}"
  if [ -n "$(compgen -G "${glob}" | grep -vE '/__init__\.py$' || true)" ]; then
    cov_args+=("--cov=${module}")
  else
    echo "SKIP coverage for ${module}: no module matching ${glob} (other than __init__.py) exists yet"
  fi
done

pytest_args=(-m "not integration" -o markers=integration)
if [ "${#cov_args[@]}" -gt 0 ]; then
  pytest_args+=("${cov_args[@]}" --cov-report=term-missing "--cov-fail-under=${THRESHOLD}")
else
  echo "SKIP coverage gate: no domain, signing or negotiation guardrail code exists yet"
fi

uv run pytest "${pytest_args[@]}"
