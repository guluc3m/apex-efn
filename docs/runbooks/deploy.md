# Deploy runbook (staging on AWS)

Decision and rationale: [ADR-100](../adr/100-aws-deployment-target.md). Status of the target: **nothing is
applied yet**. This runbook is for the first bootstrap and for day-to-day operation after it.

## 1. Prerequisites

| Item                                                                                                                              | Who                         | Notes                                                                                                                                                                                                                                                                     |
| --------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AWS account for staging                                                                                                           | Human (TL)                  | Separate from production.                                                                                                                                                                                                                                                 |
| Region (EU, GDPR)                                                                                                                 | TL decision                 | Variable `region`. No default.                                                                                                                                                                                                                                            |
| **Audit Object Lock retention, in days**                                                                                          | **TL decision (issue #81)** | Variable `audit_object_lock_retention_days`. No default. COMPLIANCE mode: cannot be shortened after the first write.                                                                                                                                                      |
| Public API CIDRs for EKS                                                                                                          | Human                       | Variable `eks_public_access_cidrs`. Must not include `0.0.0.0/0`.                                                                                                                                                                                                         |
| Terraform remote state (S3 bucket + lock table)                                                                                   | Human                       | Created outside this repo. Then uncomment `backend.tf`.                                                                                                                                                                                                                   |
| GitHub OIDC identity provider + deploy role                                                                                       | Human                       | Trust only `repo:guluc3m/apex-efn:ref:refs/heads/main` (and the `staging` environment). Permissions: ECR not needed; GHCR is used. Needs `eks:DescribeCluster` for `update-kubeconfig`. Its ARN goes in `deploy_role_arn` and in the repo variable `AWS_DEPLOY_ROLE_ARN`. |
| GHCR packages                                                                                                                     | Human                       | Packages are private by default. Either make them public, or create a `kubernetes.io/dockerconfigjson` Secret (read:packages token) and set `imagePullSecrets` in the Helm values.                                                                                        |
| EKS add-ons: External Secrets Operator (>= 0.16, API `external-secrets.io/v1`), an ingress controller (only if `ingress.enabled`) | Human                       | Installed in the cluster after Terraform.                                                                                                                                                                                                                                 |
| ClusterSecretStore `aws-secrets-manager`                                                                                          | Human                       | Backed by AWS Secrets Manager with IRSA for ESO. The name must match `externalSecrets.storeName`.                                                                                                                                                                         |

## 2. Terraform variables that must be set

`infra/terraform/environments/staging/terraform.tfvars` (gitignored; copy from `terraform.tfvars.example`):

- `region`
- `audit_object_lock_retention_days` (TL decision)
- `eks_public_access_cidrs`
- `deploy_role_arn` (once the GitHub OIDC role exists; enables the CD access entry)

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
   named as `secret_names` (for example `apex/staging/orchestrator`). The keys of the JSON are the environment
   variables the app reads (`DATABASE_URL`, `REDIS_URL`, `LLM_GATEWAY_API_KEY`, ...). Values never go to Git,
   Helm values or CI logs.
3. **Cluster add-ons:** External Secrets Operator, the `aws-secrets-manager` ClusterSecretStore, and an ingress
   controller if you need one.
4. **Repository variables** (Settings → Secrets and variables → Actions → Variables, **repository level**, because
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

5. **Helm** runs from CD. For a manual first install (same values as CD):
   ```bash
   helm upgrade --install apex infra/helm/apex -n apex-staging --create-namespace \
     -f infra/helm/apex/values-staging.yaml \
     --set-string orchestrator.image.tag=sha-<short> --set-string web.image.tag=sha-<short> \
     --set-string browserWorker.image.tag=sha-<short> --atomic --timeout 10m
   ```
   Also set the IRSA annotations and `config.*` values (see `.github/workflows/cd.yml`, which generates them).

## 4. How CD works (`.github/workflows/cd.yml`)

- Trigger: push to `main`, or manual `workflow_dispatch`.
- `images`: builds `orchestrator` (context `apps/orchestrator`), `web` and `browser-worker` (context = repo root)
  and pushes them to `ghcr.io/guluc3m/apex-efn/<app>` with tags `sha-<7 chars>` and `main`, plus provenance and SBOM.
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

## 6. Checks run on this change (no cluster, no AWS account)

- `helm lint`, `helm template` (defaults, staging, GPU workload enabled), kubeconform `-strict` against Kubernetes schemas.
- `terraform fmt -check`, `terraform validate`, tflint with the AWS ruleset. `terraform plan` refuses to run until
  the required variables are set.
- actionlint with shellcheck on the workflows; hadolint on the three Dockerfiles.

Nothing was built, pushed, applied or deployed by the author of this change.

## 7. Not done yet (follow-ups)

- **Next.js standalone output.** `apps/web/next.config.ts` has no `output: 'standalone'`. The image keeps the
  pruned `pnpm deploy` node_modules and runs `next start`. Adding `output: 'standalone'` (DEV-6) would make the image
  smaller. That is a recommendation for the web owner, not a change made here.
- **Chromium sandbox.** The browser worker runs as non-root in a read-only root filesystem. Chromium's own sandbox
  needs user namespaces, which may not be available in this pod. The app (D5-02) must choose between `--no-sandbox` with
  documented risk, or a sandbox-capable setup. This is not decided.
- **`/dev/shm`.** Chromium crashes with the 64Mi default. The chart mounts a memory emptyDir (`browserWorker.shmSize`).
- **Browser worker health.** No HTTP endpoint yet, so no probes. Add probes when the internal API lands (D5-01).
- **LLM workload.** Disabled by default. The image, resources and read-only root filesystem (with `HOME`, `XDG_CACHE_HOME`,
  `HF_HOME` in `/tmp`) are untested on a GPU node. Validate before enabling. Model choice is a TL/ADR decision.
- **Orchestrator prompts.** `apps/orchestrator/prompts/` is not in the wheel (hatch packages only `src/apex`). If the
  agents load prompts from disk, the image must copy them (DEV-4).
- **Environment protection.** The deploy job uses `environment: staging`. Add required reviewers in GitHub once wanted.
- **Production environment, RDS migrations job, backups and restore drills, DR region, cost alarms.** Not in scope.
- **Pod `automountServiceAccountToken`** is not disabled on the app pods. Low risk, but worth tightening.
