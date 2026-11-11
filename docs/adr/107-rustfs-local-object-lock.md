# ADR-107: RustFS as the local S3 Object Lock backend (supersedes ADR-900 #81 option B)

## Status

Accepted, 2026-11-11. Author: DEV-1 (task D1-03). Supersedes option B of the local-S3 decision in
ADR-900 (issue #81): "mirror the last MinIO images to GHCR".

## Context

The local stack needs an S3-compatible object store with **Object Lock in COMPLIANCE mode** to exercise
the audit chain and evidence storage (D2-10, D4-07) without touching real AWS.

MinIO is no longer usable for this:

- The project is archived. Upstream Docker Hub images were removed, and `dl.min.io` answers `410 Gone`
  (the old `mc` download path).
- Quay answers `401` for anonymous pulls of the last community tags, so `docker compose up` cannot pull
  `quay.io/minio/minio` or `quay.io/minio/mc` on a clean machine without registry credentials.
- The workaround in ADR-900 #81 option B (mirroring the last MinIO images to GHCR) depends on a personal
  namespace (`ghcr.io/guluc3m/...`), is archival-only and gets no security fixes. It also cannot be
  verified from this repo.

Issue #286 tracks the replacement.

## Decision

1. **Local development backend: RustFS `rustfs/rustfs:1.0.5`** (Apache-2.0, released 2026-11-10). It
   replaces the `minio` service on the existing host ports (9000 S3 API, 9001 console), with the
   `rustfs_data` volume. Dev credentials are `apex-dev` / `apex-dev-secret`; the default `rustfsadmin`
   account is not used (RustFS warns about it).
2. **Bootstrap with `amazon/aws-cli:2.40.0`** in the one-shot `rustfs-init` service, which runs
   `infra/rustfs/init-buckets.sh`: it creates `apex-attachments`, `apex-csv` and `apex-audit` with
   `--object-lock-enabled-for-bucket` (which also enables versioning) and sets a default `COMPLIANCE`
   retention of `RUSTFS_AUDIT_RETENTION_DAYS` (default 1 day) on `apex-audit` only. The script is
   POSIX `sh`, idempotent, and validates the retention value as a positive integer. The orchestrator
   waits for `rustfs-init` with `condition: service_completed_successfully`.
3. **Production stays on AWS S3** with Object Lock in COMPLIANCE mode, provisioned by Terraform
   (`infra/terraform`). RustFS is a local-only component and is never deployed.
4. **Development credentials only.** `apex-dev` / `apex-dev-secret` are public placeholders; they are
   used consistently by compose, `.env.example` and the orchestrator defaults, and never outside a
   developer machine.

## Evidence (spike run on a machine with a Docker daemon)

- `rustfs/rustfs:1.0.5` pulls anonymously, runs as user `rustfs`, ships `curl`, and its readiness
  endpoint (`/health/ready`) returns `200` in about 2 seconds; the compose healthcheck goes `healthy`.
- `amazon/aws-cli:2.40.0` runs against it. All three buckets are created with Object Lock;
  `get-bucket-versioning` reports `Enabled` on each; `apex-audit` reports a default retention of
  `COMPLIANCE` 1 day.
- Deleting a retained object version returns `403 AccessDenied` and the version remains readable.
- Rerunning `rustfs-init` prints `already exists` for every bucket, exits 0 and changes nothing
  (idempotent).
- `docker compose -f infra/docker-compose.yml config -q` exits 0 with the new services.

## Consequences

- **A local `rustfs_data` volume is not MinIO data.** Existing developers must run `pnpm dev:reset`
  (`docker compose down -v`); the old `minio_data` volume is orphaned and can be removed by hand.
- RustFS is a **new component with a short track record** (the 1.0.x line started in September 2026;
  1.0.5 is one day old at the time of writing). Pin the exact tag, review upgrades in a PR, and treat a
  local incompatibility as a bug to report, not as a reason to weaken Object Lock. The alternative if it
  fails is a new ADR (see below).
- Apache-2.0 keeps the repo's licence obligations simple (no AGPL-style service boundary questions).
- The dev retention (1 day) must never be copied to production; production retention is a TL decision
  (ADR-900: 6 years for audit under Spanish Commercial Code art. 30).
- `AGENTS.md`, `PROMPT-IMPLEMENTACION.md` and ADR-900 still say MinIO. They are Tech-Lead-owned
  documents, so this change does not edit them; the TL needs a follow-up edit to point at this ADR.

## Alternatives considered

- **SeaweedFS**: credible S3 gateway with Object Lock support, but a much larger surface (master/volume/
  filer) and more moving parts than a single dev process; ADR-900 #81 already relegated it to a Phase 2
  spike. Rejected for now.
- **LocalStack**: broad AWS emulation (including Object Lock), but heavy, licence-gated for parts of the
  feature set, and it emulates more than this repo needs. Rejected: a large dependency to test one
  feature.
- **Bitnami / Coollabs MinIO community images**: continue the archived line without upstream fixes and rely
  on third-party rebuilds that have already started disappearing. Rejected: same dead end as option B.
- **No WORM locally** (plain S3-compatible store): would remove the ability to test the COMPLIANCE
  behaviour that the audit chain depends on (criterion 23). Rejected: the gate would only be exercised in
  production.

## Related

- Issue #286 (replace the archived MinIO local backend with RustFS).
- `docs/runbooks/local-dev.md` section 6 ("Object Lock and RustFS buckets") and section 4 (services and
  credentials).
- ADR-900 (Tech Lead decisions, issue #81), ADR-100 (AWS deployment target), ADR-210 (GDPR retention).
- Task D1-03 (`infra/docker-compose.yml`, `infra/rustfs/init-buckets.sh`).
