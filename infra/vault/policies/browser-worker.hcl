# Policy for the browser worker (DEV-5). Least privilege, DEV-only layout.
# The worker never receives an orchestrator or LLM-facing token. It uses opaque account_id values only.

# Read marketplace credentials. It cannot write, list or delete them.
path "trato-kv/data/tenants/+/credentials/*" {
  capabilities = ["read"]
}

# Encrypted browser session state (cookies and storage state per account).
path "trato-kv/data/tenants/+/browser-sessions/*" {
  capabilities = ["create", "read", "update"]
}

# No Transit access: the browser worker never signs. No metadata or delete access either.
