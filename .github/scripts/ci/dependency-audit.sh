#!/usr/bin/env bash
# Dependency audit (D1-04): pnpm audit (high and critical) and pip-audit on the locked Python environment.
# Advisory by default: findings are printed and the script exits 0 (see docs/runbooks/branch-protection.md,
# "Current audit findings"). Set AUDIT_MODE=blocking to fail on findings once the list there is empty.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

PIP_AUDIT_VERSION=2.10.1
mode="${AUDIT_MODE:-advisory}"
findings=0

note_finding() {
  findings=$((findings + 1))
  echo "FINDING: $*"
}

require_cmd pnpm "install pnpm 9 and run pnpm install --frozen-lockfile"
if ! pnpm audit --audit-level=high; then
  note_finding "pnpm audit reported high or critical advisories (or could not reach the registry)"
fi

require_cmd uv "install uv and run uv sync --locked --dev in apps/orchestrator"
requirements="$(mktemp "${TMPDIR:-/tmp}/apex-requirements.XXXXXX")"
trap 'rm -f "${requirements}"' EXIT
(cd apps/orchestrator && uv export --locked --no-hashes --no-emit-project --format requirements-txt >"${requirements}")
if ! uvx "pip-audit==${PIP_AUDIT_VERSION}" --progress-spinner off -r "${requirements}"; then
  note_finding "pip-audit reported vulnerable Python packages"
fi

if [ "${findings}" -gt 0 ] && [ "${mode}" = "blocking" ]; then
  fail "${findings} audit tool(s) reported findings and AUDIT_MODE=blocking"
fi
if [ "${findings}" -gt 0 ]; then
  echo "ADVISORY: ${findings} audit tool(s) reported findings; the job passes until the findings are fixed"
fi
