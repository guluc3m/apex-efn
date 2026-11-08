#!/usr/bin/env bash
# Playwright E2E (D1-04, activates with D6-08): starts the compose stack, runs the tests, stops the stack.
# SKIP until an e2e spec exists under apps/web. Once one exists, Docker is required: no Docker means FAIL.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [ -z "$(find apps/web -path '*/node_modules' -prune -o -path '*e2e*' -name '*.spec.ts' -print -quit)" ]; then
  skip "no Playwright e2e specs under apps/web yet (activates with D6-08)"
fi

require_cmd pnpm "install pnpm 9 and run pnpm install --frozen-lockfile"
require_docker "the E2E stack is started with docker compose"

cleanup() {
  docker compose down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose up -d --wait

playwright_flags=()
if [ "${CI:-}" = "true" ]; then
  playwright_flags=(--with-deps)
fi
pnpm --filter @apex/web exec playwright install "${playwright_flags[@]}" chromium
pnpm --filter @apex/web test:e2e
