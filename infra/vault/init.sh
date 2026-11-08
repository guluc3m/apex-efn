#!/bin/sh
# Dev bootstrap for Vault. Idempotent: safe to run again on an already initialised server.
# Run by the `vault-init` service of infra/docker-compose.yml, which mounts this directory read-only.
# SOLO DESARROLLO: dev-mode Vault only. Production uses sealed Vault with its own bootstrap (D1-09).
set -eu

: "${VAULT_ADDR:?VAULT_ADDR is not set}"
: "${VAULT_TOKEN:?VAULT_TOKEN is not set}"
# DEV DEFAULT. Which services get a signing key is owned by D2-07 (ADR-203 / service keys).
: "${VAULT_SERVICE_KEYS:=orchestrator,gate-agent,negotiator}"
POLICY_DIR="${POLICY_DIR:-/scripts/policies}"

log() {
  echo "[vault-init] $*"
}

attempts=0
until vault status >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if [ "$attempts" -ge 30 ]; then
    log "Vault is not reachable at $VAULT_ADDR"
    exit 1
  fi
  sleep 1
done
log "Vault reachable at $VAULT_ADDR"

mounts="$(vault secrets list | awk 'NR>2 {print $1}')"

if printf '%s\n' "$mounts" | grep -qx 'apex-kv/'; then
  kv_options="$(vault read -field=options sys/mounts/apex-kv)"
  case "$kv_options" in
    *version:2*) log "KV v2 mount apex-kv/ already enabled" ;;
    *)
      log "apex-kv/ exists but is not KV v2"
      exit 1
      ;;
  esac
else
  vault secrets enable -path=apex-kv -version=2 -description="APEX-EFN KV v2: credentials, browser sessions" kv
  log "enabled KV v2 at apex-kv/"
fi

if printf '%s\n' "$mounts" | grep -qx 'transit/'; then
  log "Transit mount transit/ already enabled"
else
  vault secrets enable -path=transit -description="APEX-EFN Transit: service signing keys" transit
  log "enabled Transit at transit/"
fi

for policy in orchestrator browser-worker; do
  vault policy write "$policy" "$POLICY_DIR/$policy.hcl" >/dev/null
  log "policy $policy written from $POLICY_DIR/$policy.hcl"
done

for name in $(printf '%s' "$VAULT_SERVICE_KEYS" | tr -d ' ' | tr ',' ' '); do
  case "$name" in
    '' | *[!a-z0-9-]* | [!a-z]*)
      log "invalid service key name: $name"
      exit 1
      ;;
  esac
  if vault read -field=type "transit/keys/$name" >/dev/null 2>&1; then
    key_type="$(vault read -field=type "transit/keys/$name")"
    exportable="$(vault read -field=exportable "transit/keys/$name")"
    if [ "$key_type" != "ed25519" ] || [ "$exportable" != "false" ]; then
      log "transit/keys/$name exists with type=$key_type exportable=$exportable (expected ed25519, false)"
      exit 1
    fi
    log "transit key $name already exists (ed25519, not exportable)"
  else
    vault write "transit/keys/$name" type=ed25519 exportable=false >/dev/null
    log "created transit key $name (ed25519, not exportable)"
  fi
done

log "done"
