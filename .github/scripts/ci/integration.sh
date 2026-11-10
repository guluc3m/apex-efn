#!/usr/bin/env bash
# Integration tests (D1-04, D1-06). Two phases, each one skipped with its own reason when its target does not exist.
#   A. Vault (no Docker): tests marked vault_integration and the real-Vault block of the browser worker. Starts the
#      pinned dev Vault (tools.sh) on a free local port, bootstraps it with infra/vault/init.sh, stops it afterwards.
#   B. Testcontainers (Docker): tests marked integration. Once such a test exists, Docker is required: no Docker = FAIL.
# Result: FAIL if any phase fails. PASS if at least one phase ran and none failed. SKIP only if both phases skip.
# pytest exit code 5 ("no tests collected") counts as a skip for that pytest run; any other non-zero exit is a failure.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=tools.sh
source "$(dirname "${BASH_SOURCE[0]}")/tools.sh"

# One -o per run: a second "-o markers=" would replace the first, not add to it.
markers_ini=$'markers=\n  integration: Testcontainers, needs Docker\n  vault_integration: real Vault dev server, no Docker'

ran=()
failed=()
notes=()
vault_pid=""
vault_log=""

stop_vault() {
  if [ -n "$vault_pid" ] && kill -0 "$vault_pid" 2>/dev/null; then
    kill "$vault_pid" 2>/dev/null || true
    for _ in $(seq 1 10); do
      kill -0 "$vault_pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$vault_pid" 2>/dev/null; then
      echo "dev Vault (pid ${vault_pid}) ignored SIGTERM for 10 s; sending SIGKILL" >&2
      kill -9 "$vault_pid" 2>/dev/null || true
    fi
  fi
  if [ -n "$vault_pid" ]; then
    wait "$vault_pid" 2>/dev/null || true
    vault_pid=""
  fi
}

# True when nothing accepts TCP connections on 127.0.0.1:<port>.
port_free() {
  ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

# The dev server also binds port+1 (cluster address), so both must be free.
pick_free_port() {
  local port
  for _ in $(seq 1 50); do
    port=$((20000 + RANDOM % 20000))
    if port_free "$port" && port_free "$((port + 1))"; then
      echo "$port"
      return 0
    fi
  done
  return 1
}

show_vault_log() {
  if [ -n "$vault_log" ] && [ -f "$vault_log" ]; then
    echo "--- last lines of the Vault log (root token redacted; full log: $vault_log)" >&2
    tail -n 20 "$vault_log" | sed 's/Root Token: .*/Root Token: [redacted]/' >&2
  fi
}

# Bootstrap and the two real-Vault test runs. Records results in ran/failed/notes, never exits.
run_vault_checks() {
  local vault_dir=$1 addr=$2 token=$3 status

  set +e
  PATH="${vault_dir}:${PATH}" VAULT_ADDR="$addr" VAULT_TOKEN="$token" POLICY_DIR="$PWD/infra/vault/policies" \
    sh infra/vault/init.sh
  status=$?
  set -e
  if [ "$status" -ne 0 ]; then
    show_vault_log
    failed+=("Vault bootstrap (infra/vault/init.sh)")
    return 0
  fi

  if grep -rqE "mark\.vault_integration" --include='*.py' apps/orchestrator/tests; then
    if ! command -v uv >/dev/null 2>&1; then
      failed+=("Vault pytest (uv is required: uv sync --locked --dev in apps/orchestrator)")
    else
      set +e
      (cd apps/orchestrator && VAULT_INTEGRATION_ADDR="$addr" VAULT_TOKEN="$token" \
        uv run pytest -m vault_integration -o "$markers_ini")
      status=$?
      set -e
      if [ "$status" -eq 0 ]; then
        ran+=("Vault pytest (vault_integration)")
      elif [ "$status" -eq 5 ]; then
        notes+=("Vault pytest: pytest collected no vault_integration tests (exit 5)")
      else
        failed+=("Vault pytest (vault_integration)")
      fi
    fi
  fi

  if grep -rqE "VAULT_INTEGRATION_ADDR" --include='*.ts' apps/browser-worker/src; then
    if ! command -v pnpm >/dev/null 2>&1; then
      notes+=("browser-worker real-Vault test not run: pnpm is not on PATH")
    else
      set +e
      VAULT_INTEGRATION_ADDR="$addr" VAULT_TOKEN="$token" \
        pnpm --filter @apex/browser-worker exec vitest run src/platform/vault.test.ts
      status=$?
      set -e
      if [ "$status" -eq 0 ]; then
        ran+=("browser-worker vitest (real Vault)")
      else
        failed+=("browser-worker vitest (real Vault)")
      fi
    fi
  fi
}

phase_vault() {
  if ! grep -rqE "mark\.vault_integration|VAULT_INTEGRATION_ADDR" --include='*.py' --include='*.ts' \
    apps/orchestrator/tests apps/browser-worker/src; then
    notes+=("Vault phase: no real-Vault test exists yet")
    return 0
  fi

  local vault_bin vault_dir port addr token attempts
  vault_bin="$(ensure_tool vault)"
  vault_dir="$(dirname "$vault_bin")"
  if ! port="$(pick_free_port)"; then
    failed+=("Vault phase: no free port pair found for the dev Vault")
    return 0
  fi
  addr="http://127.0.0.1:${port}"
  token="apex-ci-root-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
  vault_log="$(mktemp "${TMPDIR:-/tmp}/apex-vault-dev.XXXXXX")"

  echo "starting the pinned dev Vault on ${addr} (cluster port $((port + 1)))"
  "$vault_bin" server -dev -dev-root-token-id="$token" -dev-listen-address="127.0.0.1:${port}" >"$vault_log" 2>&1 &
  vault_pid=$!

  attempts=0
  until VAULT_ADDR="$addr" VAULT_TOKEN="$token" "$vault_bin" status >/dev/null 2>&1; do
    if ! kill -0 "$vault_pid" 2>/dev/null; then
      show_vault_log
      failed+=("Vault phase: dev Vault exited during startup (port ${port} may be taken)")
      break
    fi
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 60 ]; then
      show_vault_log
      failed+=("Vault phase: dev Vault did not answer on ${addr} within 60 s")
      break
    fi
    sleep 1
  done

  if [ "${#failed[@]}" -eq 0 ]; then
    echo "dev Vault is up (pid ${vault_pid})"
    run_vault_checks "$vault_dir" "$addr" "$token"
  fi

  stop_vault
  if [ "${#failed[@]}" -eq 0 ]; then
    rm -f "$vault_log"
  fi
  vault_log=""
}

phase_testcontainers() {
  if ! grep -rqE "mark\.integration([^A-Za-z0-9_]|\$)" --include='*.py' apps/orchestrator/tests; then
    notes+=("Testcontainers phase: no test is marked integration yet")
    return 0
  fi

  if ! command -v uv >/dev/null 2>&1; then
    failed+=("Testcontainers phase: uv is required (uv sync --locked --dev in apps/orchestrator)")
    return 0
  fi
  if ! docker info >/dev/null 2>&1; then
    failed+=("Testcontainers phase: requires Docker (not running or not installed)")
    return 0
  fi

  local status
  set +e
  (cd apps/orchestrator && uv run pytest -m integration -o "$markers_ini")
  status=$?
  set -e

  if [ "$status" -eq 0 ]; then
    ran+=("Testcontainers pytest (integration)")
  elif [ "$status" -eq 5 ]; then
    notes+=("Testcontainers phase: pytest collected no integration tests (exit 5)")
  else
    failed+=("Testcontainers pytest (integration)")
  fi
}

# Phase C — adversarial negotiation suite (D5-09, issue #240). It boots the mock marketplace with tsx and
# drives the negotiation engine over HTTP. APEX_REQUIRE_MOCK_MARKETPLACE=1 turns a missing Node/mock into a
# failure, so the suite cannot silently disappear from CI.
phase_adversarial() {
  local tests_dir="apps/orchestrator/tests/negotiation/adversarial"
  if [ ! -d "$tests_dir" ]; then
    notes+=("adversarial phase: ${tests_dir} does not exist yet (activates with D5-09)")
    return
  fi
  if [ ! -x "apps/mock-marketplace/node_modules/.bin/tsx" ]; then
    fail "adversarial suite requires apps/mock-marketplace dependencies (pnpm install) and Node"
  fi
  local status=0
  set +e
  (cd apps/orchestrator && APEX_REQUIRE_MOCK_MARKETPLACE=1 uv run pytest tests/negotiation/adversarial -q)
  status=$?
  set -e
  if [ "$status" -eq 0 ]; then
    ran+=("adversarial negotiation pytest (mock marketplace)")
  elif [ "$status" -eq 5 ]; then
    notes+=("adversarial phase: pytest collected no tests (exit 5)")
  else
    failed+=("adversarial negotiation pytest (mock marketplace)")
  fi
}

trap 'stop_vault' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

phase_vault
phase_testcontainers
phase_adversarial

for note in ${notes[@]+"${notes[@]}"}; do
  echo "NOTE: ${note}"
done
if [ "${#failed[@]}" -gt 0 ]; then
  fail "integration failed: $(IFS='; '; echo "${failed[*]}")"
fi
if [ "${#ran[@]}" -eq 0 ]; then
  skip "no integration target exists yet ($(IFS='; '; echo "${notes[*]:-none}"))"
fi
echo "PASS: ran $(IFS='; '; echo "${ran[*]}")"
