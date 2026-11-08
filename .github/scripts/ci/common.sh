#!/usr/bin/env bash
# Shared helpers for the job scripts in .github/scripts/ci (D1-04). Sourced, never executed.
# Every job script runs the same way in CI and in `pnpm ci:local`, so the logic lives here and in the scripts.
#
# Result convention read by ci-local.sh: exit 0 with a line starting "SKIP:" means skipped; exit 0 without it
# means PASS; any non-zero exit means FAIL.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT_DIR" || exit 1

skip() {
  echo "SKIP: $*"
  exit 0
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required ($2)"
}

# A target exists but Docker is not running: fail loudly, never pass silently.
require_docker() {
  docker info >/dev/null 2>&1 || fail "requires Docker (not running or not installed): $1"
}
