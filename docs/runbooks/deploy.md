# Deploy runbook (staging on AWS)

Decision and rationale: [ADR-100](../adr/100-aws-deployment-target.md). Status of the target: **nothing is
applied yet**. This runbook is for the first bootstrap and for day-to-day operation after it.

## 1. Prerequisites

| Item                                                                                                                              | Who                       | Notes                                                                                                                                                                                                                                                                     |
| --------------------------------------------------------------------------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AWS account for staging                                                                                                           | Human (TL)                | Separate from production.                                                                                                                                                                                                                                                 |
| Region (EU, GDPR)                                                                                                                 | TL decision               | Variable `region`. No default.                                                                                                                                                                                                                                            |
| Audit Object Lock retention, in days                                                                                              | TL decision (ADR-900 #81) | Variable `audit_object_lock_retention_days`. Default **2190 (6 years)**, Spanish Commercial Code art. 30. COMPLIANCE mode: cannot be shortened after the first write.                                                                                                     |
| Public API CIDRs for EKS                                                                                                          | Human                     | Variable `eks_public_access_cidrs`. Must not include `0.0.0.0/0`.                                                                                                                                                                                                         |
| Terraform remote state (S3 bucket + lock table)                                                                                   | Human                     | Created outside this repo. Then uncomment `backend.tf`.                                                                                                                                                                                                                   |
| GitHub OIDC identity provider + deploy role                                                                                       | Human                     | Trust only `repo:guluc3m/apex-efn:ref:refs/heads/main` (and the `staging` environment). Permissions: ECR not needed; GHCR is used. Needs `eks:DescribeCluster` for `update-kubeconfig`. Its ARN goes in `deploy_role_arn` and in the repo variable `AWS_DEPLOY_ROLE_ARN`. |
| GHCR packages                                                                                                                     | Human                     | Packages are private by default. Either make them public, or create a `kubernetes.io/dockerconfigjson` Secret (read:packages token) and set `imagePullSecrets` in the Helm values.                                                                                        |
| EKS add-ons: External Secrets Operator (>= 0.16, API `external-secrets.io/v1`), an ingress controller (only if `ingress.enabled`) | Human                     | Installed in the cluster after Terraform.                                                                                                                                                                                                                                 |
| ClusterSecretStore `aws-secrets-manager`                                                                                          | Human                     | Backed by AWS Secrets Manager with IRSA for ESO. The name must match `externalSecrets.storeName`.                                                                                                                                                                         |

## 2. Terraform variables that must be set

`infra/terraform/environments/staging/terraform.tfvars` (gitignored; copy from `terraform.tfvars.example`):

- `region`
- `eks_public_access_cidrs`
- `deploy_role_arn` (once the GitHub OIDC role exists; enables the CD access entry)

`audit_object_lock_retention_days` no longer needs to be set: it defaults to **2190 (6 years)**, ADR-900 #81.
Only override it to lengthen the retention — COMPLIANCE retention cannot be shortened once objects are written.

Placeholders with defaults, to review before applying: `vpc_cidr`, instance types and sizes, node counts,
`rds_instance_class`, `redis_node_type`, `eks_cluster_version`, `kubernetes_namespace`, `helm_release_name`.

## 3. First-time bootstrap (in this order)

1. **Terraform**
   ```bash
   cd infra/terraform/environments/staging
   # uncomment backend.tf, fill in the placeholders
   terraform init
   terraform plan -out=staging.tfplan   # review: Object Lock must show COMPLIANCE with your retention
   terraform apply staging.tfplan
   terraform output                      # cluster_name, bucket names, irsa_role_arns, secret_names
   ```
2. **Secret values** (Terraform only creates the empty secrets). Write one JSON object per secret in AWS Secrets Manager,
   named as `secret_names`. Values never go to Git, Helm values or CI logs. The database uses **two** secrets so the
   schema owner never reaches a runtime pod (issue #221):

   | Secret                                            | Keys                                              | Content                                                                                                                                                                                                      |
   | ------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
   | `apex/staging/db-migrate`                         | `migrateDatabaseUrl`                              | Owner DSN, `postgresql://apex_owner:<master password>@<postgres_endpoint>/apex`. Build it from `terraform output postgres_endpoint` and the RDS-managed master secret (`postgres_master_user_secret_arn`).   |
   | `apex/staging/db-app`                             | `appDatabaseUrl`, `appPassword`                   | App DSN used by the orchestrator, `postgresql+asyncpg://apex_app_login:<app password>@<postgres_endpoint>/apex`, plus the same password. Generate it once; `bootstrap-app-role.sh` converges the role to it. |
   | `apex/staging/orchestrator`                       | `REDIS_URL`, `LLM_GATEWAY_API_KEY`, ...           | Runtime settings. `DATABASE_URL` comes from `db-app` (see the Helm chart's `database.app`), not from here.                                                                                                   |
   | `apex/staging/web`                                | `DATABASE_URL`, `REDIS_URL`, OIDC client settings | Today the **owner** DSN: the Prisma tenant extension that sets `app.tenant_id` is a DEV-2/6 follow-up.                                                                                                       |
   | `apex/staging/browser-worker`, `apex/staging/llm` | component settings                                | Vault/Redis/model settings.                                                                                                                                                                                  |

   The External Secrets Operator materialises `apex-db-app` and `apex-db-migrate` as Kubernetes Secrets. The migration
   Job reads both; the Deployments only read `apex-db-app`. The orchestrator and web IRSA roles are allowed to read
   `db-app` but **not** `db-migrate` (infra/terraform `workload_iam`): a runtime pod with the owner DSN could bypass
   row-level security.

3. **Cluster add-ons:** External Secrets Operator (with its own IRSA role allowed to read every `apex/staging/*`
   secret), the `aws-secrets-manager` ClusterSecretStore, and an ingress controller if you need one. ESO must work
   **before** the first Helm install, because the migration Job waits for the two database Secrets.

4. **Database bootstrap and the application role** happen during the Helm upgrade, in this order (pre-install /
   pre-upgrade hook Jobs, `infra/helm/apex/templates/migrations.yaml`):

   1. `<release>-migrate` (weight -5), as the schema owner: `prisma migrate deploy`, then the optional demo seed
      (`migrations.seed`), then `infra/postgres/bootstrap-app-role.sh`, which creates/updates
      `apex_app_login` (LOGIN, member of `apex_app`, `NOBYPASSRLS`) with `appPassword`.
   2. `<release>-load-defaults` (weight 0): `python -m apex.tenant_config.load_defaults` for
      `migrations.loadDefaults.tenantIds`.

   Helm waits for both Jobs before it creates or updates the Deployments, so the app pods never roll against a
   schema-less database or a missing login role. The first install therefore needs the secrets from step 2 and ESO
   working. `migrations.seed: false` in a tenant environment with real data.

5. **Repository variables** (Settings → Secrets and variables → Actions → Variables, **repository level**, because
   the `prepare` job reads them without an environment):

   | Variable                                                                       | Source                            |
   | ------------------------------------------------------------------------------ | --------------------------------- |
   | `AWS_DEPLOY_ROLE_ARN`                                                          | Deploy role ARN (human-created)   |
   | `AWS_REGION`                                                                   | `region`                          |
   | `EKS_CLUSTER_NAME`                                                             | `terraform output cluster_name`   |
   | `AWS_ORCHESTRATOR_ROLE_ARN`, `AWS_WEB_ROLE_ARN`, `AWS_BROWSER_WORKER_ROLE_ARN` | `terraform output irsa_role_arns` |
   | `S3_BUCKET_ATTACHMENTS`, `S3_BUCKET_CSV`, `S3_BUCKET_AUDIT`                    | `terraform output *_bucket`       |

   Once all nine are set, the next run of CD deploys. Until then, CD still publishes the images and the deploy job
   prints a notice that says what is missing.

6. **Helm** runs from CD. For a manual first install (same values as CD):
   ```bash
   helm upgrade --install apex infra/helm/apex -n apex-staging --create-namespace \
     -f infra/helm/apex/values-staging.yaml \
     --set-string orchestrator.image.tag=sha-<short> --set-string web.image.tag=sha-<short> \
     --set-string browserWorker.image.tag=sha-<short> --set-string migrations.image.tag=sha-<short> \
     --atomic --timeout 10m
   ```
   Also set the IRSA annotations and `config.*` values (see `.github/workflows/cd.yml`, which generates them).
   `migrations.image` is the `migrator` target of `apps/web/Dockerfile`, published by CD as
   `ghcr.io/guluc3m/apex-efn/web-migrations`; build it locally with
   `docker build -f apps/web/Dockerfile --target migrator -t apex/web-migrations:dev .`.

## 4. How CD works (`.github/workflows/cd.yml`)

- Trigger: push to `main`, or manual `workflow_dispatch`.
- `images`: builds `orchestrator`, `web`, `web-migrations` and `browser-worker`, all with **context = repo root**
  (so the orchestrator sees `apps/llm-stub` as the `[tool.uv.sources]` path source and `config/defaults`, and the
  pnpm images see the whole workspace), and pushes them to `ghcr.io/guluc3m/apex-efn/<app>` with tags
  `sha-<7 chars>` and `main`, plus provenance and SBOM. `web-migrations` is the `migrator` target of
  `apps/web/Dockerfile` (Prisma CLI + seed + psql) used only by the pre-upgrade Job.
- `prepare`: checks the nine repository variables. If any is missing, the next job is skipped and a notice says which.
- `deploy-staging`: OIDC to AWS (no stored keys), `aws eks update-kubeconfig`, then
  `helm upgrade --install --atomic --timeout 10m`. `--atomic` rolls back automatically if the rollout fails.
- Concurrency group `cd-staging` with `cancel-in-progress: false`: deploys queue, they never overlap.

## 5. Rollback

- Automatic: `--atomic` already rolls back a failed upgrade.
- Manual, to a previous release:
  ```bash
  helm history apex -n apex-staging
  helm rollback apex <REVISION> -n apex-staging --wait --timeout 10m
  ```
- Helm rolls back **only Kubernetes objects**. It does not roll back database migrations, Object Lock
  objects, or Secrets Manager values. Check the migration state before rolling back an image that depends on a
  newer schema.
- The pre-upgrade migration hooks do **not** run on `helm rollback`. Rolling back to an image that expects an
  older schema still leaves the database migrated forward (Prisma migrations are forward-only). Treat a
  migration that drops or renames columns as a two-release change (expand, then contract).

## 6. Checks run on this change

- Images built and run locally: `apex/orchestrator:dev` (boots, `GET /health` → 200, prompts present,
  `config/defaults` present at `apex.tenant_config.defaults.DEFAULT_PATH`), `apex/web:dev` (serves the
  public landing from the standalone output, `GET /` → 200), `apex/browser-worker:dev` (starts and stays
  up against Redis/Vault).
- `helm lint`, `helm template` (defaults, staging, GPU workload enabled, ingress + HPA), kubeconform `-strict`
  against Kubernetes 1.31 schemas.
- Issue #221 adds the two migration hook Jobs (`migrate`, `load-defaults`) and the two database Secrets to the
  chart. `helm template` (defaults and staging) and kubeconform were re-run on them; the RLS transcript in
  `docs/runbooks/local-dev.md` was produced against the local compose stack with the real bootstrap script.
- `terraform fmt -check`, `terraform init -backend=false` + `validate` in `environments/staging`, `tflint` (AWS
  ruleset). `terraform plan` still refuses to run until the required variables (`region`, `eks_public_access_cidrs`)
  are set.
- `actionlint` on `.github/workflows/*.yml`.

Nothing was pushed, applied or deployed: there is no AWS account, GHCR package set or EKS cluster yet.

## 7. Not done yet (follow-ups)

- **`next.config.ts` needs a DEV-6 review.** `output: 'standalone'` is a one-line DEV-6-owned change made in
  D1-09 so the web image could serve; DEV-6 owns `apps/web/next.config.ts` and should confirm it (it only
  affects the production image, not `next dev`).
- **Chromium sandbox.** The browser worker runs as non-root in a read-only root filesystem. Chromium's own sandbox
  needs user namespaces, which may not be available in this pod. The app (D5-02) must choose between `--no-sandbox` with
  documented risk, or a sandbox-capable setup. This is not decided.
- **`/dev/shm`.** Chromium crashes with the 64Mi default. The chart mounts a memory emptyDir (`browserWorker.shmSize`).
- **Browser worker health.** No HTTP endpoint yet, so no probes. Add probes when the internal API lands (D5-01).
- **LLM workload.** Disabled by default. The image, resources and read-only root filesystem (with `HOME`, `XDG_CACHE_HOME`,
  `HF_HOME` in `/tmp`) are untested on a GPU node. Validate before enabling. Model choice is a TL/ADR decision.
- **`llm-stub` and `mock-marketplace` images.** Dev-only services, not part of the staging chart. Their Dockerfiles
  land in D4-02 and D5-04; add Helm Deployments/values later if they are ever run in staging.
- **Environment protection.** The deploy job uses `environment: staging`. Add required reviewers in GitHub once wanted.
- **Production environment, backups and restore drills, DR region, cost alarms.** Not in scope. The RDS migrations
  Job now exists (pre-upgrade hook, issue #221), but it has never run against a real RDS instance.
- **Pod `automountServiceAccountToken`** is not disabled on the app pods. Low risk, but worth tightening. The two
  migration Jobs already set it to `false`.
- **`web-migrations` image size.** It is built from the full workspace (`builder` stage) so it carries
  `node_modules`; acceptable for a per-release Job on staging, revisit before production.
- **Web database role.** The web Deployment keeps the owner DSN until the Prisma tenant extension sets
  `app.tenant_id` (DEV-2/6). `database.webUrlKey` in the chart is the switch, empty on purpose today.
