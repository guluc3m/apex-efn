#!/usr/bin/env bash
# Playwright E2E (D1-04, activates with D6-08). SKIP until an e2e spec exists under apps/web.
#
# The suite starts the web app itself: apps/web/playwright.config.ts declares a `webServer`
# (`pnpm dev`, port 3000). The specs that exist today use Playwright's `request` fixture against the
# web app, so they need no backend and no Docker. A full-stack, browser-driven suite (mission, gate,
# negotiation) will need the compose stack, but this job must not boot it: it only runs Playwright's
# `webServer` against the dev server (D6-08 adds the full-stack suite).
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [ -z "$(find apps/web -path '*/node_modules' -prune -o -path '*e2e*' -name '*.spec.ts' -print -quit)" ]; then
  skip "no Playwright e2e specs under apps/web yet (activates with D6-08)"
fi

require_cmd pnpm "install pnpm 9 and run pnpm install --frozen-lockfile"

# `--with-deps` installs system libraries with apt and needs root: only on a GitHub runner. Locally the
# specs must not require a browser binary (they use the `request` fixture), because a developer machine
# may not have libnss/libnspr.
playwright_flags=()
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  playwright_flags=(--with-deps)
fi

pnpm --filter @apex/web exec playwright install "${playwright_flags[@]}" chromium
pnpm --filter @apex/web test:e2e
