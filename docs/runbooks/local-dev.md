# Runbook: local development environment

Owner: DEV-1 (task D1-03). Entry point: `compose.yaml` at the repo root, which `include:`s
`infra/docker-compose.yml`. The compose project name is pinned to `apex` in both files.

> **Dev only.** Every password, token and client secret in this runbook and in `infra/` is a public
> placeholder. Never reuse them outside a local machine.

## 1. Prerequisites

- Docker Engine with Docker Compose v2 (`docker compose version`). The repo is validated with Compose
  v5.7, but a daemon has not been run from this repo yet (see section 9).
- Node 22 and pnpm 9 (`.nvmrc`, `packageManager`), uv for Python (`.python-version`).
- Free host ports listed in section 4. Port 3000 is reserved for `pnpm dev` (Next.js) on the host.
- RAM: the stack runs about 15 containers. Expect several GB free. The exact figure has not been measured.

## 2. Scripts (root `package.json`)

| Command                                          | What it does                                                                                                                                                                                                           |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm dev:up`                                    | `docker compose up -d --wait`: starts everything, waits for healthy services.                                                                                                                                          |
| `pnpm dev:down`                                  | `docker compose down`: stops containers, **keeps volumes** (data survives).                                                                                                                                            |
| `pnpm dev:reset`                                 | Runs `infra/scripts/dev-reset.sh`: `down -v` (wipes all volumes), `up -d --wait`, then migrations and seed **only if they exist** (Prisma from D2-03, `load_defaults` from D4-03). It prints a skip message otherwise. |
| `pnpm docker:up` / `docker:down` / `docker:logs` | Legacy aliases, kept.                                                                                                                                                                                                  |

Start the app services too (not buildable yet, see section 7):

```bash
docker compose --profile apps up -d --build
```

## 3. Cold start

- Target from spec §11: `docker compose up` in under 10 minutes on a clean machine.
- **Not measured yet.** The authoring environment had no Docker daemon. Measure it on a clean machine with
  `time pnpm dev:up`. Run it twice: the first run includes image pulls, the second is a warm start.
  Record both numbers here before claiming the target is met.

## 4. Services, ports and dev credentials

| Service                           | Host URL / port                                  | Image (pinned)                                     | Dev credentials / notes                                                                                                                                              |
| --------------------------------- | ------------------------------------------------ | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Postgres 16 + pgvector            | `localhost:5432`                                 | `pgvector/pgvector:0.8.7-pg16-bookworm`            | user `apex` / `apex`. DBs: `apex` (app, `vector` extension), `keycloak`, `langfuse`, `unleash`.                                                                      |
| Redis                             | `localhost:6379`                                 | `redis:7.4.12-alpine`                              | no auth                                                                                                                                                              |
| MinIO API                         | `http://localhost:9000`                          | `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` | `minioadmin` / `minioadmin`                                                                                                                                          |
| MinIO console                     | `http://localhost:9001`                          | (same)                                             | `minioadmin` / `minioadmin`                                                                                                                                          |
| minio-init (one-shot)             | n/a                                              | `quay.io/minio/mc:RELEASE.2025-08-13T08-35-41Z`    | creates buckets, see section 6                                                                                                                                       |
| Keycloak (OIDC)                   | `http://localhost:8080`                          | `quay.io/keycloak/keycloak:26.0`                   | admin console: `admin` / `admin` (master realm). Realm `apex`, see section 5.                                                                                        |
| Vault (dev mode)                  | `http://localhost:8200`                          | `hashicorp/vault:1.21.4`                           | root token `apex-dev-root-token`. In-memory: everything is lost on restart.                                                                                          |
| Unleash                           | `http://localhost:4242`                          | `unleashorg/unleash-server:8.3.1`                  | client API token `default:development.apex-dev-unleash-client`, admin API token `*:*.apex-dev-unleash-admin`. UI login: Unleash bootstrap admin (not verified here). |
| Langfuse v2                       | `http://localhost:3001`                          | `langfuse/langfuse:2.95.11`                        | no seeded user: sign up locally on first visit                                                                                                                       |
| Grafana                           | `http://localhost:3002`                          | `grafana/grafana:12.4.14`                          | `admin` / `admin`. Datasources (Prometheus, Loki, Tempo) are provisioned. No dashboards yet (D1-07).                                                                 |
| Prometheus                        | `http://localhost:9090`                          | `prom/prometheus:v3.16.0`                          | no auth. Scrapes the OTel collector.                                                                                                                                 |
| Loki                              | `http://localhost:3100`                          | `grafana/loki:3.6.20`                              | no auth. Receives logs via OTLP at `/otlp`.                                                                                                                          |
| Tempo                             | `http://localhost:3200`                          | `grafana/tempo:2.10.10`                            | no auth. Receives traces from the collector.                                                                                                                         |
| OTel Collector                    | `localhost:4317` (gRPC), `localhost:4318` (HTTP) | `otel/opentelemetry-collector-contrib:0.165.0`     | apps send OTLP here (`OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`)                                                                                            |
| LLM stub (OpenAI-compatible)      | `http://localhost:8001/v1`                       | built from `apps/llm-stub` (`apex/llm-stub:dev`)   | no auth. Scenarios are baked into the image; select one with `X-Stub-Scenario`. See "LLM stub" below.                                                                |
| Orchestrator (profile `apps`)     | `http://localhost:8000`                          | built from `apps/orchestrator`                     | not buildable until D1-09                                                                                                                                            |
| Mock marketplace (profile `apps`) | `http://localhost:8002`                          | built from `apps/mock-marketplace`                 | port is provisional. Not buildable until D5-04.                                                                                                                      |
| Web (profile `apps`)              | no host port                                     | built from `apps/web`                              | run `pnpm dev` on the host, which uses `http://localhost:3000`                                                                                                       |

### LLM stub

The stub is built from source (`apps/llm-stub`, image `apex/llm-stub:dev`); Mockoon and the
`infra/mocks/openai-stub.json` fixture are gone. It speaks only the OpenAI wire format and needs no network.

- Build or rebuild after changing `src/` or `scenarios/` (both are copied into the image):
  `docker compose build llm-stub`, then `docker compose up -d llm-stub`.
- Health: `curl -m 2 http://localhost:8001/health` → `{"status":"ok"}`. `docker compose ps llm-stub`
  shows the container as healthy.
- Scenario selection: send `X-Stub-Scenario: <name>` (for example `no-json-schema`, `flaky-5xx`,
  `always-malformed`). Without the header the stub matches by model/role/prompt hash and falls back to
  `default`. The names and their behaviour are listed in `apps/llm-stub/README.md`, and the loaded set is
  visible at `GET http://localhost:8001/_stub/scenarios`.
- Gateway config: `LLM_GATEWAY_URL=http://localhost:8001/v1` from the host (already in `.env.example`),
  or `http://llm-stub:8001/v1` from another compose service.
- The container is non-root (UID 10001) and the same image is what the `llm-stub` CI job tests.

Keycloak test users (realm `apex`, password `apex-dev` for all, MFA enrolment on first login):

| Tenant   | Users (username = email)                                                                                        |
| -------- | --------------------------------------------------------------------------------------------------------------- |
| tenant-a | `owner-a@apex.local`, `admin-a@apex.local`, `buyer-a@apex.local`, `finance-a@apex.local`, `viewer-a@apex.local` |
| tenant-b | `owner-b@apex.local`, `admin-b@apex.local`, `buyer-b@apex.local`, `finance-b@apex.local`, `viewer-b@apex.local` |

## 5. Keycloak realm and MFA

- File: `infra/keycloak/realm-apex.json`. It is imported with `start-dev --import-realm` **only when the
  realm does not exist yet** (on an empty Keycloak database). Changing the file later does nothing on a
  running stack. Use `pnpm dev:reset`, or change the realm in the admin console and export it.
- Clients: `apex-web` (confidential, standard flow, redirect `http://localhost:3000/*`, PKCE S256, dev
  secret `apex-dev-web-secret`). Its tokens carry the claims `tenant_id` (user attribute), `roles` (realm
  roles) and the audience `apex-orchestrator`. `apex-orchestrator` is the resource server: a confidential
  client with every flow disabled, dev secret `apex-dev-orchestrator-secret`.
- Roles: `owner`, `admin`, `buyer`, `finance`, `viewer`. `viewer` never signs (see `docs/security/rbac.md`, D1-05).
- Tenants: groups `/tenant-a` and `/tenant-b`, each with a `tenant_id` attribute. Users carry the same
  `tenant_id` attribute, which is what the claim mapper reads.
- `tenant_id` is declared in the realm's user profile with **view and edit restricted to admins**, so a
  user can never change their own tenant from the account console. Unmanaged attributes stay disabled.
  Any new user attribute must be declared there too.
- **MFA:** the realm sets `CONFIGURE_TOTP` as a default required action, and every test user has it in
  `requiredActions`. The first login forces OTP enrolment. The file keeps this on. Do not change it there.
- **Disable MFA locally only** (for example for automated UI tests you control). In the admin console
  (`http://localhost:8080`, `admin`/`admin`) either remove `CONFIGURE_TOTP` from a user's "Required user
  actions", or switch off "Set as default action" under Authentication, then Required actions. Do this in
  the running instance. Do not commit it. `pnpm dev:reset` restores the file's behaviour.

### 5.1 Logging in to the web app locally

1. Start Keycloak (and its database): `docker compose up -d postgres keycloak`, then wait for
   `curl -m 5 -s http://localhost:8080/realms/apex/.well-known/openid-configuration` to answer.
   `pnpm dev:up` also works and starts the whole stack.
2. Copy `.env.example` to `apps/web/.env.local` (or export the same variables) and check the web block:
   `AUTH_SECRET` (any dev-only string; generate one with `openssl rand -base64 32`),
   `AUTH_KEYCLOAK_ID=apex-web`, `AUTH_KEYCLOAK_SECRET=apex-dev-web-secret`,
   `AUTH_KEYCLOAK_ISSUER=http://localhost:8080/realms/apex`, `AUTH_URL=http://localhost:3000`.
   `.env.local` is gitignored; never commit the secret.
3. Run `pnpm --filter @apex/web dev` and open `http://localhost:3000`. The root redirects to `/es`; the
   landing and `/{locale}/acceso` are public, every other app route sends you to Keycloak through
   `/api/auth/signin?callbackUrl=…`.
4. Sign in with a test user from the table above (for example `owner-a@apex.local` / `apex-dev`).
   **First login forces OTP enrolment** (`CONFIGURE_TOTP`): follow the Keycloak screen, scan the QR with
   any TOTP app and enter the 6-digit code. The OTP is stored per user in the Keycloak database, so it
   survives `dev:down` but not `dev:reset`.
5. To skip OTP while testing, remove `CONFIGURE_TOTP` from that user's "Required user actions" in the
   admin console (section 5). If the user already enrolled, also delete the OTP credential there.
6. Log out from the app clears the Auth.js cookie; the Keycloak SSO session stays alive until it expires
   (RP-initiated logout is not wired yet). Use a private window or the admin console to force a fresh
   login.

## 6. Object Lock and MinIO buckets

- `minio-init` runs `infra/minio/init-buckets.sh` once. It creates `apex-attachments`, `apex-csv` and
  `apex-audit`, all with Object Lock (`mc mb --with-lock`, `--ignore-existing`, so it is safe to rerun).
- On `apex-audit` it sets a **default retention in COMPLIANCE mode**. The dev value is
  `MINIO_AUDIT_RETENTION` (default `1d`).
- **Production retention is a TL decision.** The spec does not define it. Do not copy the dev value.
- **Caveat:** in COMPLIANCE mode, locked object versions cannot be deleted by anyone, root included, until
  retention expires. A normal `mc rm` will fail. The way out locally is to wipe the volume:
  `pnpm dev:reset` (`docker compose down -v`), which deletes the volume directly.
- Upstream MinIO images were removed from Docker Hub in 2026. The pinned Quay tags are the last community
  releases. Quay may require authentication for anonymous pulls. If a pull fails, override the images
  (`MINIO_IMAGE`, `MC_IMAGE` environment variables) with an accessible mirror and report it. Choosing a
  replacement is a TL decision.

## 7. Init SQL and empty volumes

- `infra/postgres/init-databases.sql` runs **only when the Postgres data volume is empty** (first start).
  Changing it later does nothing on an existing volume. Run `pnpm dev:reset`, or
  `docker compose down -v` and then `up`.
- It creates the `keycloak`, `langfuse` and `unleash` databases and enables `vector` (pgvector) in `apex`.
- Keycloak, Langfuse and Unleash each have their own database. Langfuse and Prisma migrations do not share
  one.

## 8. Reset and day-to-day

- Stop, keep data: `pnpm dev:down`.
- Start again: `pnpm dev:up`.
- Full reset (wipes Postgres, Redis, MinIO, Grafana, Loki, Tempo, Prometheus data, and re-imports Keycloak):
  `pnpm dev:reset`.
- Logs: `pnpm docker:logs`, or `docker compose logs -f <service>`.

### 8.1 Feature flags (Unleash)

Naming, defaults (everything off) and client usage: `docs/observability/flags.md`.

- Seed the known flags once the stack is healthy (idempotent, creates disabled flags only):
  `node infra/unleash/seed-flags.mjs`. Extra flag names can be passed as arguments. Set `UNLEASH_URL` (default
  `http://localhost:4242/api`) and `UNLEASH_ADMIN_TOKEN` (default: the dev admin token) if they differ.
- Unleash UI: `http://localhost:4242`. UI login is separate from the API tokens. The API tokens are for
  the apps and the seed script only.
- `pnpm dev:reset` wipes the Unleash database, so run the seed script again afterwards.

## 9. Validation status (what has and has not been verified)

Verified on the authoring machine (no Docker daemon):

- `docker compose config -q` from the repo root and from `infra/`: exit 0, empty stderr. Also with
  `--profile apps`.
- Host port collisions in the resolved config: none, with and without the `apps` profile.
- Every bind-mount source exists. No image uses `latest`.
- The Keycloak realm JSON parses and passes a structural check: roles, users, tenant attributes, MFA
  required action, clients and mappers.
- **Keycloak 26.0.8 (native distribution, dev H2 database) imports the realm successfully.** Via the admin
  API, for a tenant-a and a tenant-b user: the `tenant_id` attribute is persisted, the example access token
  carries `tenant_id`, `roles` and audience `apex-orchestrator`, `CONFIGURE_TOTP` is a required action,
  `tenant_id` is admin-only in the user profile, and the password grant is disabled on `apex-web`.
- **Observability configs, with the pinned upstream binaries run natively:** `otelcol-contrib validate`
  (0.165.0), `promtool check config` (3.16.0) and `loki -verify-config` (3.6.20) all pass. End to end, an OTLP
  trace, log and metric sent to the collector arrive in Tempo (trace found by ID), Loki (LogQL query) and the
  collector's Prometheus exporter.
- Every pinned image tag exists in its registry (anonymous manifest lookup), except the MinIO images (section 6).

Verified separately, on a machine with a Docker daemon, while wiring the LLM stub (D1-03):

- `docker build -t apex/llm-stub:dev apps/llm-stub` succeeds from the lockfile with uv 0.13.7.
- The container runs as UID/GID 10001, reports `healthy`, answers `GET /health` with
  `{"status":"ok"}`, and returns scenario content from `POST /v1/chat/completions`.
- `docker compose up -d --wait llm-stub` (on a remapped host port) starts it and reaches healthy.

**Not verified** (needs a machine with Docker):

- Starting the stack in containers, service health, and whether every healthcheck command works inside its
  image (Grafana, Loki, Prometheus, Langfuse, Unleash, Vault).
- The first interactive login forces OTP enrolment in the browser (the required action is verified, the UI
  flow is not).
- `minio-init` creates the buckets with Object Lock, and `up --wait` treats the completed one-shot correctly.
- Pulls of the MinIO Quay images (see section 6).
- Cold-start time (section 3).

## 10. Environment variables

`.env.example` documents the dev values for apps (`DATABASE_URL`, `REDIS_URL`, `S3_*`, `AUTH_*`,
`VAULT_*`, `UNLEASH_*`, `OTEL_*`). Copy it to `.env.local`. Compose itself does not read `.env.local`: the
services in `infra/docker-compose.yml` use hardcoded dev values, except the MinIO image variables above.

## 11. Vault (dev secrets bootstrap)

Owner: DEV-1 (task D1-06). Full layout, policies and client APIs: `docs/security/secrets.md`.

- `vault` runs in dev mode (in memory, root token `apex-dev-root-token`, `http://localhost:8200`). `vault-init`
  runs once per `dev:up` and bootstraps it: KV v2 at `apex-kv/`, Transit at `transit/`, the `orchestrator` and
  `browser-worker` policies, and one non-exportable ed25519 Transit key per name in `VAULT_SERVICE_KEYS`
  (default `orchestrator,gate-agent,negotiator`, a dev default owned by D2-07).
- Check it: `docker compose logs vault-init` should end with `[vault-init] done`. From the host:
  `VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=apex-dev-root-token vault secrets list`.
- Rerun the bootstrap without restarting Vault (idempotent):
  `docker compose run --rm vault-init`. Changing `VAULT_SERVICE_KEYS` adds keys and never deletes them.
- Dev data is lost whenever the Vault container stops. `dev:down` and `dev:reset` both recreate it, and
  `vault-init` runs again on the next `dev:up`.
- Local tests that need a real Vault (not part of normal `pytest`, which stays hermetic):
  `VAULT_INTEGRATION_ADDR=http://localhost:8200 VAULT_TOKEN=apex-dev-root-token uv run pytest -q -m vault_integration -o markers=vault_integration`
  (run from `apps/orchestrator`), and `VAULT_INTEGRATION_ADDR=... pnpm --filter @apex/browser-worker exec vitest run`.
  To run them without this compose stack, use `pnpm ci:local --job integration` (see `docs/security/secrets.md` section 2.5).
