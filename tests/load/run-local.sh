#!/usr/bin/env bash
# Local runner for the APEX-EFN k6 load tests (task D1-10, owner DEV-1).
#
# Usage:
#   bash tests/load/run-local.sh                          # read-heavy orchestrator API
#   bash tests/load/run-local.sh --script mission-queue.js
#   bash tests/load/run-local.sh --script gate-queue.js --base-url http://127.0.0.1:8000
#
# The orchestrator must be running with the development tenant header enabled (local only):
#   APEX_ALLOW_TENANT_HEADER=true
#
# k6 runs from the pinned `grafana/k6` image, so no local k6 install is needed. Linux is assumed for
# `--network host`; on macOS the script rewrites `localhost` to `host.docker.internal` and drops the flag.
# Results are written to `tests/load/results/` (git-ignored).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

K6_IMAGE="${K6_IMAGE:-grafana/k6:0.54.0}"
SCRIPT_NAME="orchestrator.js"
BASE_URL="${BASE_URL:-http://localhost:8000}"

usage() {
  cat <<'USAGE'
Usage: bash tests/load/run-local.sh [options]

Options:
  --script NAME     orchestrator.js (default) | mission-queue.js | gate-queue.js
  --base-url URL    Orchestrator base URL (default http://localhost:8000)
  -h, --help        Show this help

Environment:
  BASE_URL          Same as --base-url
  K6_PROFILE        load (default) or smoke, for a shorter ramp
  K6_TENANT_ID      Tenant sent in X-Tenant-Id (default tenant-a)
  K6_IMAGE          k6 image (default grafana/k6:0.54.0)
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --script)
      [ "$#" -ge 2 ] || {
        echo "ERROR: --script needs a name" >&2
        exit 2
      }
      SCRIPT_NAME="$2"
      shift 2
      ;;
    --base-url)
      [ "$#" -ge 2 ] || {
        echo "ERROR: --base-url needs a URL" >&2
        exit 2
      }
      BASE_URL="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# Only the scripts shipped here; never an arbitrary path from a caller.
SCRIPT_NAME="${SCRIPT_NAME##*/}"
case "${SCRIPT_NAME}" in
  orchestrator.js | mission-queue.js | gate-queue.js) ;;
  *)
    echo "ERROR: unknown script '${SCRIPT_NAME}'. Use orchestrator.js, mission-queue.js or gate-queue.js." >&2
    exit 2
    ;;
esac
[ -f "${SCRIPT_DIR}/${SCRIPT_NAME}" ] || {
  echo "ERROR: ${SCRIPT_DIR}/${SCRIPT_NAME} does not exist" >&2
  exit 2
}

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: docker is required to run the pinned k6 image." >&2
  exit 1
}
command -v curl >/dev/null 2>&1 || {
  echo "ERROR: curl is required for the health check." >&2
  exit 1
}

BASE_URL="${BASE_URL%/}"

echo "Checking ${BASE_URL}/health ..."
if ! curl -fsS -m 5 "${BASE_URL}/health" >/dev/null; then
  echo "ERROR: ${BASE_URL}/health is not answering." >&2
  echo "Start the orchestrator with APEX_ALLOW_TENANT_HEADER=true, then retry." >&2
  exit 1
fi

RESULTS_DIR="${SCRIPT_DIR}/results"
mkdir -p "${RESULTS_DIR}"

NETWORK_ARGS=(--network host)
if [ "$(uname -s)" = "Darwin" ]; then
  NETWORK_ARGS=()
  BASE_URL="${BASE_URL/localhost/host.docker.internal}"
fi

echo "Running ${SCRIPT_NAME} against ${BASE_URL} (profile ${K6_PROFILE:-load}) ..."
# The k6 image runs as a non-root user, so run it as the caller: otherwise the JSON summary cannot be
# written into the bind-mounted results directory.
docker run --rm "${NETWORK_ARGS[@]}" \
  --user "$(id -u):$(id -g)" \
  -e "BASE_URL=${BASE_URL}" \
  -e "K6_PROFILE=${K6_PROFILE:-load}" \
  -e "K6_TENANT_ID=${K6_TENANT_ID:-tenant-a}" \
  -e "K6_SUMMARY_DIR=/scripts/results" \
  -v "${SCRIPT_DIR}:/scripts" \
  "${K6_IMAGE}" run "/scripts/${SCRIPT_NAME}"

echo "Summary written to ${RESULTS_DIR}/k6-${SCRIPT_NAME%.js}-summary.{json,txt}"
