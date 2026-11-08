# Secrets: sops/age for the repo, Vault for runtime

Owner: DEV-1 (task D1-06). Related: `docs/runbooks/local-dev.md` (section 11), `.sops.yaml`,
`infra/vault/`, `apps/orchestrator/src/trato/platform/vault.py`, `apps/browser-worker/src/platform/vault.ts`.

Two stores, two purposes:

| Store                                  | What lives there                                                                                                         | Who reads it                                                       |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------ |
| **sops + age** (repo, encrypted files) | Secrets that must be versioned with the code (for example, CI or deployment values). Only `*.enc.*` files are committed. | Developers and CI runners whose age key is a recipient.            |
| **Vault** (runtime)                    | Marketplace credentials, browser session state, and ed25519 Transit keys for service signing.                            | The orchestrator and the browser worker, each with its own policy. |

Nothing in this document puts a secret value in the repo in plaintext. Private keys never enter the
repo, the logs, the LLM context or the browser.

## 1. sops + age (repository secrets)

### 1.1 Versions

Tested with **sops 3.10.2** and **age 1.2.1** (static binaries from the getsops and FiloSottile GitHub releases).
Use the same versions or newer. Install `age` and `age-keygen` from the same release.

### 1.2 Generate your key (once per developer)

```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt        # prints "Public key: age1..." on stderr
chmod 600 ~/.config/sops/age/keys.txt
age-keygen -y ~/.config/sops/age/keys.txt        # prints the PUBLIC key again
```

- `keys.txt` contains `AGE-SECRET-KEY-1...`. It is your **private** key. Never share it, paste it in chat,
  commit it or put it in a CI log. The repo ignores `keys.txt` and `*.agekey` as a safety net.
- Share **only the public key** (`age1...`) with the team, for example through a PR to `.sops.yaml`.

### 1.3 Become a recipient

1. Open a PR that adds your public key to the `age:` list in `/.sops.yaml` (both creation rules).
   Adding a recipient grants decryption, so the PR needs DEV-1 review and TL approval.
2. An existing recipient re-encrypts every existing file for the new recipient list:
   ```bash
   SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops updatekeys -y secrets/<file>.enc.yaml
   ```
   Commit `.sops.yaml` and the re-encrypted files together.

Removing a recipient: delete the key from `.sops.yaml`, run `sops updatekeys -y` on each file, and
**rotate the secret values** the removed person could read. Old git history stays decryptable by that key.

### 1.4 Encrypt and decrypt

```bash
# Encrypt a new file. The plaintext stays under a name that git ignores (secrets/*), and the
# encrypted output gets the .enc name. Delete the plaintext afterwards.
mkdir -p secrets
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt \
  sops --filename-override secrets/app.enc.yaml -e secrets/app.yaml > secrets/app.enc.yaml
rm secrets/app.yaml

# Edit: opens the decrypted content in $EDITOR and re-encrypts on save.
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops secrets/app.enc.yaml

# Decrypt to stdout (never redirect to a file inside the repo):
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops -d secrets/app.enc.yaml
```

- Path rules live in `/.sops.yaml`: `secrets/**/*.enc.{yaml,yml,json,env}` and `infra/**/*.enc.{yaml,yml,json,env}`.
  Other paths are not encrypted, so the rules must match the file name you use.
- `.gitignore` ignores `secrets/*` and re-includes only `secrets/*.enc.*`. A plaintext file in `secrets/`
  is ignored by git, but that is a safety net, not permission to leave one on disk.
- **Placeholder check.** The recipients in `.sops.yaml` are placeholders until the TL adds the real public
  keys. `sops -e` fails with `invalid recipient encoding: mixed case` until then. That is intended.
  Do not edit the rules to get around it.

### 1.5 Verified round trip (D1-06)

Run in a scratch directory with throwaway keys (`alice`, `bob`, `carol`), using the same `.sops.yaml` rules
and the commands above:

- encrypt with two recipients (`alice`, `bob`): the values are `ENC[AES256_GCM,...]`, and both keys decrypt them;
- `carol` (not a recipient) fails with "no identity matched any of the recipients";
- add `carol` to the recipient list, run `sops updatekeys -y`: `carol` now decrypts;
- the repo's placeholder config refuses to encrypt.

### 1.6 CI

CI decrypts with a dedicated age key stored as a CI secret (`SOPS_AGE_KEY`). The job exports it to a file
inside the runner's temporary directory, sets `SOPS_AGE_KEY_FILE`, and never echoes it. The CI key is a recipient
like any other and is added with the same process (1.3).

## 2. Vault (runtime secrets)

### 2.1 Dev bootstrap

`infra/docker-compose.yml` runs two services:

- `vault`: `hashicorp/vault:1.21.4` in **dev mode**. It is in memory, and the root token
  `trato-dev-root-token` is public. Local only.
- `vault-init`: the same image, `restart: 'no'`, `depends_on: vault (service_healthy)`. It runs
  `infra/vault/init.sh`, which is mounted read-only from `infra/vault/` and is idempotent.

`init.sh` does the following on every run:

1. Waits for `vault status` (30 s maximum).
2. Enables KV v2 at **`trato-kv/`** if it is missing. Fails if the mount exists but is not v2.
3. Enables **Transit** at **`transit/`** if it is missing.
4. Writes the policies `orchestrator` and `browser-worker` from `infra/vault/policies/*.hcl`.
5. For each name in **`VAULT_SERVICE_KEYS`** (comma-separated, default `orchestrator,gate-agent,negotiator`),
   creates a Transit key with `type=ed25519, exportable=false`, or verifies the existing one.

`VAULT_SERVICE_KEYS` is a **dev default owned by D2-07**. The production list of signing services is decided
there. Key names must match `[a-z][a-z0-9-]{1,62}`.

Dev mode forgets everything when the container stops, and `dev:down` removes containers, so `vault-init`
re-bootstraps on every `dev:up`.

### 2.2 KV v2 layout

Mount `trato-kv/`. Paths are built from validated identifiers only:

| Data                                                           | Path (KV v2 data API)                                             | Written by                                  | Read by                                |
| -------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------- | -------------------------------------- |
| Marketplace credential                                         | `trato-kv/data/tenants/<tenant_id>/credentials/<credential_ref>`  | orchestrator (onboarding, `put_credential`) | browser worker only (`get_credential`) |
| Browser session state (cookies, storage state) for one account | `trato-kv/data/tenants/<tenant_id>/browser-sessions/<account_id>` | browser worker                              | browser worker                         |

- `tenant_id`: `^[a-z0-9][a-z0-9-]{0,62}$`.
- `credential_ref`: `cred_` plus 16 to 64 URL-safe characters. It is generated with `secrets.token_urlsafe`
  in the orchestrator and is not derived from the tenant or the content.
- `account_id`: `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`.
- Anything that does not match is rejected **before** any request (path traversal such as `..`, `/` or a newline).

Deleting a credential removes all versions through the metadata path (`trato-kv/metadata/...`, `delete`
capability for the orchestrator).

### 2.3 Transit keys (service signing)

- Keys are `ed25519`, **`exportable=false`**. Private material never leaves Vault. The clients have no export
  operation, and a test asserts that.
- Signing is **pure ed25519** over the raw bytes (`prehashed=false`, which Vault requires for ed25519). The
  canonical payload (RFC 8785, D2-06) is what gets signed.
- `transit/sign/<key>` returns `vault:v<N>:<base64>`. The client exposes the Vault form and the raw 64-byte
  signature. Verify with `transit/verify/<key>`, or independently with the public key from `transit/keys/<key>`
  (`cryptography` in Python, WebCrypto or `node:crypto` in TS).
- Vault's `verify` returns `valid=false` for a tampered payload. It returns an HTTP error only for malformed input.

### 2.4 Policies (least privilege)

| Policy                                                       | KV                                                                                       | Transit                                                        | Notes                                                                               |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `orchestrator` (`infra/vault/policies/orchestrator.hcl`)     | credentials `data`: `create`, `update`. credentials `metadata`: `read`, `list`, `delete` | `transit/keys/*`: `create`, `read`. `sign`, `verify`: `update` | Stores credentials but **cannot read their values**. No access to browser sessions. |
| `browser-worker` (`infra/vault/policies/browser-worker.hcl`) | credentials `data`: `read`. browser sessions `data`: `create`, `read`, `update`          | none                                                           | Cannot sign, cannot write credentials, cannot list or delete.                       |

The `default` policy is attached as usual. Mint a dev token with one policy:

```bash
VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=trato-dev-root-token \
  vault token create -policy=browser-worker -ttl=1h
```

Real services receive short-lived tokens (or AppRole/Kubernetes auth in production). Dev uses the root token
only in compose.

**Known limits (follow-up, not MVP):**

- The policies are per **service**, not per tenant. A `+` wildcard covers every tenant. Tenant isolation inside
  Vault needs per-tenant entities or templated policies. Application code enforces tenant scope with the
  validated `tenant_id` in every path.
- `transit/keys/*` and `transit/sign/*` cover every key. Restrict them to the key list once D2-07 fixes it.

## 3. Client APIs

### 3.1 Python: `trato.platform.vault`

- `VaultClient(base_url, token, *, transport=None, timeout=10, ref_token_source=...)`, or
  `VaultClient.from_env()` (reads `VAULT_ADDR` and `VAULT_TOKEN`). The token is held as `SecretStr`, and `repr`
  shows `token=<redacted>`.
- KV: `put_credential(tenant_id, payload) -> CredentialRef`, `get_credential(tenant_id, ref) -> SecretPayload`,
  `delete_credential(tenant_id, ref)` (idempotent), `put_session_state(tenant_id, account_id, state)`,
  `get_session_state(tenant_id, account_id) -> SecretPayload`.
- Transit: `ensure_signing_key(name)`, `get_public_key(name) -> TransitPublicKey(raw)`,
  `sign(name, data) -> TransitSignature`, `verify(name, data, signature) -> bool`.
- `SecretPayload` redacts `repr`, `str` and format. It cannot be JSON-serialised or pickled. Only `reveal()`
  returns the values, and only trusted backend code may call it.
- Errors: `VaultError(operation, status_code)` and `VaultNotFoundError`. Messages contain only the operation name
  and the HTTP status. They never contain the token, the payload or Vault's response body.
- Identifiers are validated with `fullmatch`, so a trailing newline does not pass.

### 3.2 TypeScript: `apps/browser-worker/src/platform/vault.ts`

- `new VaultClient({ addr, token, fetchImpl?, timeoutMs? })`, or `VaultClient.fromEnv()`.
- `getCredential(tenantId, ref)`, `getSessionState(tenantId, accountId)`, `putSessionState(tenantId, accountId, state)`.
- Secret values are wrapped in `RedactedSecret`. It returns `[REDACTED]` from `toJSON`, `toString` and
  `util.inspect`, and only `reveal()` returns the value. Responses are validated with zod.
- The global `fetch` is resolved on each call, so test doubles apply.

## 4. CredentialRef rule (AGENTS.md section 3.8, PROMPT §3.1)

1. Marketplace credentials are referenced **only** by `CredentialRef` (an opaque `cred_...` ID) and an
   `account_id`. The orchestrator stores them and cannot read them back. The browser worker reads them inside
   the worker process.
2. Credential values never go into LLM prompts, LLM context, tool results, transcripts, screenshots, logs,
   traces, database rows, error messages or the browser page. The LLM only sees the account reference.
3. `SecretPayload` and `RedactedSecret` exist so that a value which reaches a log, a trace or a JSON response
   prints as `[REDACTED]`. They are a last line of defence, not permission to pass values around.
4. CI leak test (D1-07, criterion 29): canary secrets are injected and the build fails if they show up in logs or traces.

## 5. What must never reach logs, fixtures, the LLM or the repo

- Vault tokens and `VAULT_TOKEN` values (the dev root token is a public placeholder, but the rule applies anyway).
- age private keys (`AGE-SECRET-KEY-1...`), Transit private material (impossible by design), and any decrypted sops output.
- Marketplace credentials and session state (cookies, storage state).
- Financial values from the CSV import (spec §3.1.1), which are not secrets but follow the same redaction rules.
