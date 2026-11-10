#!/usr/bin/env bash
# Local CI runner (D1-04): runs every job of .github/workflows/ci.yml in CI order, with the scope CI uses on
# main, and prints a summary. Each job is the same script CI calls: .github/scripts/ci/<job>.sh.
# See docs/runbooks/local-ci.md.
#
#   pnpm ci:local                       every job, keep going, report all results
#   bash .github/scripts/ci-local.sh --job python --job secret-scan
#   bash .github/scripts/ci-local.sh --fail-fast
#   bash .github/scripts/ci-local.sh --list
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR" || exit 1

JOBS=(workflow-lint typescript python llm-stub integration secret-scan dependency-audit llm-portability contracts-drift migration-drift e2e)

describe() {
  case "$1" in
    workflow-lint) echo "actionlint on workflows, shellcheck on scripts" ;;
    typescript) echo "turbo build/lint/typecheck/test (full), coverage ratchet" ;;
    python) echo "ruff, mypy, pytest with coverage gate" ;;
    llm-stub) echo "apps/llm-stub: ruff, format, mypy, pytest (own uv project)" ;;
    integration) echo "real Vault (pinned dev server, no Docker) + pytest -m integration (needs Docker once tests exist)" ;;
    secret-scan) echo "TruffleHog, verified secrets, pinned version" ;;
    dependency-audit) echo "pnpm audit + pip-audit (advisory)" ;;
    llm-portability) echo "criterion 25 deny-list (self-test and scan)" ;;
    contracts-drift) echo "root script contracts:check (activates with D2-01)" ;;
    migration-drift) echo "prisma migrate diff (activates with D2-03, needs Docker)" ;;
    e2e) echo "Playwright E2E on the compose stack (activates with D6-08, needs Docker)" ;;
    *) return 1 ;;
  esac
}

usage() {
  cat <<'USAGE'
Usage: pnpm ci:local | bash .github/scripts/ci-local.sh [options]
Runs every CI job script in CI order (full scope) and prints a summary. See docs/runbooks/local-ci.md.

Options:
USAGE
  echo "  --job NAME     run only this job (repeatable). Names: ${JOBS[*]}"
  echo "  --list         print the job names and exit"
  echo "  --keep-going   run every job even after a failure (default)"
  echo "  --fail-fast    stop after the first failing job"
  echo "  --no-fetch     do not run 'git fetch origin' first"
  echo "  -h, --help     show this help"
}

selected=()
keep_going=1
fetch=1
while [ "$#" -gt 0 ]; do
  case "$1" in
    --job)
      [ "$#" -ge 2 ] || { echo "ERROR: --job needs a name" >&2; exit 2; }
      if ! describe "$2" >/dev/null; then
        echo "ERROR: unknown job '$2'. Known: ${JOBS[*]}" >&2
        exit 2
      fi
      selected+=("$2")
      shift 2
      ;;
    --list)
      for job in "${JOBS[@]}"; do printf '%-18s %s\n' "$job" "$(describe "$job")"; done
      exit 0
      ;;
    --keep-going) keep_going=1; shift ;;
    --fail-fast) keep_going=0; shift ;;
    --no-fetch) fetch=0; shift ;;
    -h | --help) usage; exit 0 ;;
    *) echo "ERROR: unknown option '$1'" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "${#selected[@]}" -eq 0 ]; then
  selected=("${JOBS[@]}")
fi

# Same scope CI uses on main: full TypeScript run, and secret scan from merge-base(origin/main, HEAD).
export CI_TS_SCOPE=full
export CI_BASE_REF=origin/main
unset CI_BASE_SHA

if [ "$fetch" -eq 1 ]; then
  if git fetch origin --quiet 2>/dev/null; then
    echo "fetched origin"
  else
    echo "WARNING: git fetch origin failed (offline?); using the local origin/main"
  fi
fi

log_dir="$(mktemp -d "${TMPDIR:-/tmp}/apex-ci-local.XXXXXX")"
names=()
results=()
seconds=()
notes=()
overall=0
stopped=0

for job in "${selected[@]}"; do
  if [ "$stopped" -eq 1 ]; then
    names+=("$job"); results+=("NOT RUN"); seconds+=("-"); notes+=("stopped by --fail-fast")
    continue
  fi

  echo ""
  echo "================================================================"
  echo "== ${job}: $(describe "$job")"
  echo "================================================================"
  log="${log_dir}/${job}.log"
  start=$(date +%s)
  (set -o pipefail; bash ".github/scripts/ci/${job}.sh" 2>&1 | tee "$log")
  status=$?
  elapsed=$(( $(date +%s) - start ))

  note=""
  if [ "$status" -ne 0 ]; then
    result="FAIL"
    overall=1
    note="exit ${status}; log: ${log}"
  elif grep -q '^SKIP:' "$log"; then
    result="SKIP"
    note="$(grep -m1 '^SKIP:' "$log" | sed 's/^SKIP: //')"
  elif grep -q '^ADVISORY:' "$log"; then
    result="PASS"
    note="$(grep -m1 '^ADVISORY:' "$log")"
  else
    result="PASS"
  fi

  names+=("$job"); results+=("$result"); seconds+=("$elapsed"); notes+=("$note")

  if [ "$result" = "FAIL" ] && [ "$keep_going" -eq 0 ]; then
    stopped=1
  fi
done

echo ""
echo "================================================================"
echo "Summary"
echo "================================================================"
printf '%-18s %-8s %8s  %s\n' "job" "result" "seconds" "note"
printf '%-18s %-8s %8s  %s\n' "------------------" "--------" "--------" "----"
for i in "${!names[@]}"; do
  printf '%-18s %-8s %8s  %s\n' "${names[$i]}" "${results[$i]}" "${seconds[$i]}" "${notes[$i]}"
done
echo ""
if [ "$overall" -eq 0 ]; then
  echo "ci:local passed (logs: ${log_dir})"
else
  echo "ci:local FAILED (logs: ${log_dir})"
fi
exit "$overall"
