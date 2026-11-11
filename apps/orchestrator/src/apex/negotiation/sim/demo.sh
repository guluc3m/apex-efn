#!/usr/bin/env bash
# One-command demo (D5-11): LLM stub + fake marketplace + the AI-buyer simulation UI.
#
#   ./apps/orchestrator/src/apex/negotiation/sim/demo.sh
#   open http://127.0.0.1:8003
#
# Everything is local: no Docker, no database, no network. Ctrl-C stops all three processes.
set -euo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SIM_DIR/../../../../../.." && pwd)"

cleanup() {
  echo ""
  echo "stopping…"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait_for() {
  local url="$1" name="$2"
  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  echo "ERROR: $name did not answer on $url" >&2
  exit 1
}

echo "1/3  LLM stub            :8001"
(cd "$ROOT/apps/llm-stub" && exec uv run python -m llm_stub) &
wait_for "http://127.0.0.1:8001/v1/models" "LLM stub"

echo "2/3  fake marketplace    :8002  (mock-a, mock-b, mock-c)"
(cd "$ROOT/apps/mock-marketplace" && exec pnpm dev) &
wait_for "http://127.0.0.1:8002/healthz" "fake marketplace"

echo "3/3  simulation UI       :8003"
(cd "$ROOT/apps/orchestrator" && exec uv run python -m apex.negotiation.sim.server) &
wait_for "http://127.0.0.1:8003/api/config" "simulation UI"

echo ""
echo "ready -> http://127.0.0.1:8003"
echo "press Ctrl-C to stop everything."
wait
