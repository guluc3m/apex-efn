#!/usr/bin/env bash
# One-command demo (D5-11): LLM + fake marketplace + the AI-buyer simulation UI.
#
#   ./apps/orchestrator/src/apex/negotiation/sim/demo.sh            # local LLM stub
#   DEEPSEEK_API_KEY=sk-... ./…/demo.sh                            # real model, both sides
#
# Real provider (prices are still decided in code; the model only words the messages):
#   export SIM_LLM_URL=https://api.deepseek.com
#   export DEEPSEEK_API_KEY=sk-...
#   export SIM_LLM_MODEL=deepseek-chat        # optional, this is the default with a key
#   export SIM_LLM_TIMEOUT_MS=8000            # optional, a real reply is slower than the stub
#   ./apps/orchestrator/src/apex/negotiation/sim/demo.sh
#
# Everything else is local: no marketplace, no database, no Docker. Ctrl-C stops all the processes.
set -euo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SIM_DIR/../../../../../.." && pwd)"

# Local secrets, already gitignored: put `DEEPSEEK_API_KEY=...` in .env.local at the repo root.
if [ -f "$ROOT/.env.local" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ROOT/.env.local"
  set +a
fi

API_KEY="${SIM_LLM_API_KEY:-${DEEPSEEK_API_KEY:-}}"
if [ -n "$API_KEY" ]; then
  export SIM_LLM_API_KEY="${SIM_LLM_API_KEY:-$API_KEY}"
  export SIM_LLM_URL="${SIM_LLM_URL:-https://api.deepseek.com}"
  export SIM_LLM_MODEL="${SIM_LLM_MODEL:-deepseek-chat}"
  export SIM_LLM_TIMEOUT_MS="${SIM_LLM_TIMEOUT_MS:-8000}"
  unset SIM_LLM_SCENARIO || true
else
  export SIM_LLM_URL="${SIM_LLM_URL:-http://127.0.0.1:8001}"
  export SIM_LLM_SCENARIO="${SIM_LLM_SCENARIO:-sim-negotiation}"
fi

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

if [ -n "$API_KEY" ]; then
  echo "     LLM                   $SIM_LLM_URL  (model $SIM_LLM_MODEL, key loaded)"
else
  echo "     LLM stub              :8001"
  (cd "$ROOT/apps/llm-stub" && exec uv run python -m llm_stub) &
  wait_for "http://127.0.0.1:8001/v1/models" "LLM stub"
fi

echo "     fake marketplace      :8002  (mock-a, mock-b, mock-c)"
(cd "$ROOT/apps/mock-marketplace" && exec pnpm dev) &
wait_for "http://127.0.0.1:8002/healthz" "fake marketplace"

echo "     simulation UI         :8003"
(cd "$ROOT/apps/orchestrator" && exec uv run python -m apex.negotiation.sim.server) &
wait_for "http://127.0.0.1:8003/api/config" "simulation UI"

echo ""
echo "ready -> http://127.0.0.1:8003"
echo "press Ctrl-C to stop everything."
wait
