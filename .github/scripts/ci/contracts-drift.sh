#!/usr/bin/env bash
# Contract drift (D1-04, activates with D2-01): the root script `contracts:check` must pass.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if ! node -e "process.exit(require('./package.json').scripts?.['contracts:check'] ? 0 : 1)"; then
  skip "root script 'contracts:check' is not defined yet (activates with D2-01)"
fi

require_cmd pnpm "install pnpm 9 and run pnpm install --frozen-lockfile"
pnpm run contracts:check
