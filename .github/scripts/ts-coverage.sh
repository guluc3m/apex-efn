#!/usr/bin/env bash
# Coverage gate (D1-04, criterion list §9 / AGENTS.md 5 D1-04) for the TypeScript packages that
# own deterministic business logic. Thresholds are passed as CLI flags so no package file is edited.
# Run from the repository root after `pnpm install`.
set -euo pipefail

THRESHOLD=80
PACKAGES=(money scoring crypto-client)

failures=0
for pkg in "${PACKAGES[@]}"; do
  dir="packages/${pkg}"
  if [ ! -f "${dir}/package.json" ]; then
    echo "ERROR: ${dir}/package.json not found; the coverage gate expects this package to exist"
    exit 1
  fi
  name="$(node -p "require('./${dir}/package.json').name")"
  echo "::group::coverage ${name} (threshold ${THRESHOLD}%)"
  if pnpm --filter "${name}" exec vitest run \
    --coverage.enabled \
    --coverage.provider=v8 \
    --coverage.include='src/**' \
    --coverage.exclude='src/**/*.test.ts' \
    --coverage.thresholds.lines="${THRESHOLD}" \
    --coverage.thresholds.functions="${THRESHOLD}" \
    --coverage.thresholds.branches="${THRESHOLD}" \
    --coverage.thresholds.statements="${THRESHOLD}"; then
    echo "PASS ${name}"
  else
    echo "FAIL ${name}: coverage below ${THRESHOLD}% or tests failed"
    failures=$((failures + 1))
  fi
  echo "::endgroup::"
done

if [ "${failures}" -gt 0 ]; then
  echo "TS coverage gate FAILED for ${failures} package(s)"
  exit 1
fi
echo "TS coverage gate passed for: ${PACKAGES[*]}"
