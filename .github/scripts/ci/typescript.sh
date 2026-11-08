#!/usr/bin/env bash
# TypeScript job (D1-04): build, lint, typecheck and test with turbo, then the coverage ratchet.
# CI_TS_SCOPE=affected: only packages changed against CI_BASE_REF (default origin/main), used on pull requests.
# CI_TS_SCOPE=full (default): everything, used on main and by `pnpm ci:local`.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_cmd pnpm "install pnpm 9 and run pnpm install --frozen-lockfile"

case "${CI_TS_SCOPE:-full}" in
  affected)
    base="${CI_BASE_REF:-origin/main}"
    echo "Affected packages only (compared with ${base})"
    pnpm exec turbo run build lint typecheck test --filter="...[${base}]"
    ;;
  full)
    echo "Full run"
    pnpm exec turbo run build lint typecheck test
    ;;
  *) fail "CI_TS_SCOPE must be 'affected' or 'full', got '${CI_TS_SCOPE}'" ;;
esac

node .github/scripts/ci/ts-coverage.mjs
