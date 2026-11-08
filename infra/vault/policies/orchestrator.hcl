# Policy for the orchestrator (DEV-4 services). Least privilege, DEV-only layout.
# Dev bootstrap: infra/vault/init.sh. KV layout: docs/security/secrets.md.

# Marketplace credentials: the orchestrator stores them at onboarding. It does NOT read values back.
# Values are read only by the browser-worker (policies/browser-worker.hcl).
path "trato-kv/data/tenants/+/credentials/*" {
  capabilities = ["create", "update"]
}

# Metadata only (versions, timestamps). `delete` removes every version of a credential.
path "trato-kv/metadata/tenants/+/credentials/*" {
  capabilities = ["read", "list", "delete"]
}

# Service signing keys (ed25519, exportable=false). The orchestrator signs and verifies.
# It may read key metadata and public keys. There is no export path.
path "transit/keys/*" {
  capabilities = ["create", "read"]
}

path "transit/sign/*" {
  capabilities = ["update"]
}

path "transit/verify/*" {
  capabilities = ["update"]
}
