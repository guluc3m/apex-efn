# ADR-100: AWS as the deployment target (EKS, RDS, ElastiCache, S3 Object Lock, KMS)

## Status

Proposed

## Context

PROMPT-IMPLEMENTACION.md §5.8 asks for Kubernetes (EKS or GKE), a separate node pool for browser workers,
an optional GPU pool for self-hosted models, Terraform, and GitHub Actions CD. §5.5 requires the signed
audit log to be anchored in S3 Object Lock (compliance mode). §5.9 requires KMS and a secrets manager.

The spec names AWS-specific controls (S3 Object Lock in compliance mode, KMS, Secrets Manager), so AWS is
the lowest-risk target: each requirement maps to a managed service with a known control. GKE would also
satisfy §5.8, but it would need an equivalent for Object Lock compliance retention and a different
secrets/KMS story. Choosing GKE later stays possible: the containers and the Helm chart are cloud-neutral,
and only `infra/terraform/` is AWS-specific.

## Decision

1. **Kubernetes:** Amazon EKS, managed node groups:
   - `general`: web, orchestrator, add-ons.
   - `browser`: tainted `trato.io/nodepool=browser:NoSchedule`. Chromium pods only.
   - `gpu`: tainted `trato.io/nodepool=gpu:NoSchedule`, AL2023 NVIDIA AMI, desired count 0 by default.
     Used only by the optional self-hosted LLM (vLLM, OpenAI-compatible `/v1`, ADR-002).
2. **Database:** RDS for PostgreSQL 16 (pgvector is available). TLS forced by parameter group. Master
   password generated and stored by RDS in Secrets Manager (never in Terraform state).
3. **Cache and queues:** ElastiCache for Redis 7.1, TLS in transit, KMS at rest.
4. **Object storage:** S3 buckets `attachments`, `csv`, `audit`. All private, versioned, SSE-KMS, TLS only,
   BucketOwnerEnforced. The `audit` bucket is created with **Object Lock enabled** and a default
   **COMPLIANCE** retention. The retention length is a **required Terraform variable with no default**,
   because it is an open Tech Lead decision (issue #81). It cannot be shortened once objects are written.
5. **Keys and secrets:** two KMS keys with rotation (`data`, `audit`). Secrets Manager holds one secret
   per component, created as an empty placeholder by Terraform. Values are set out of band and read by
   External Secrets Operator, so the chart never contains secret values.
6. **Workload identity:** IRSA. One IAM role per ServiceAccount, trusting only that ServiceAccount.
   The audit bucket is append-only for the orchestrator (no delete permission).
7. **Packaging and delivery:** images in GHCR (`ghcr.io/guluc3m/apex-efn/<app>`), tagged `sha-<short>`
   and `main`, never `latest`. One Helm umbrella chart (`infra/helm/trato`), not a chart per app: the three
   apps are released together and share config and secret conventions, and per-component toggles keep the
   value surface in one place. CD (`.github/workflows/cd.yml`) authenticates with GitHub OIDC, with no
   stored AWS keys.
8. **Terraform:** community modules `terraform-aws-modules/vpc` 5.21.0 and `terraform-aws-modules/eks`
   20.37.2 (exact pins), because they are mature and carry many edge cases. Everything else (S3, KMS, RDS,
   ElastiCache, IAM, Secrets Manager) uses plain AWS provider resources, so the security-relevant settings
   stay visible in this repo. AWS provider `~> 5.100.0`. Remote state is a commented example (no real bucket).

## Consequences

- Staging is fully described as code, but nothing has been applied. The first apply is blocked until the
  TL decides the audit retention and the GitHub OIDC role exists.
- Object Lock COMPLIANCE is irreversible per object. A wrong retention value cannot be fixed by a later
  apply. This is why the variable has no default.
- Cross-cloud portability is limited to containers and the chart. Moving to GKE means a new Terraform
  root, IRSA-equivalent identity, and the audit anchor in a different WORM service.
- Browser workers run Chromium in a container. Sandboxing and `/dev/shm` sizing are app-level concerns (see
  docs/runbooks/deploy.md, "Not done yet").
- Cost and sizing (instance types, node counts, RDS class, NAT) are placeholders labelled as such. They
  are not business numbers.

## Open decisions (TL)

- Audit Object Lock retention in days (issue #81). Required, no default.
- AWS region and EU data residency (GDPR). Required, no default.
- Domain names for the web app and the API (Helm `ingress.*`). Required when the ingress is enabled.
- Public API endpoint CIDRs for EKS. Required, no default.

## Related

- PROMPT-IMPLEMENTACION.md §5.5, §5.8, §5.9
- ADR-002 (OpenAI-compatible LLM gateway; the self-hosted GPU workload)
- docs/runbooks/deploy.md
- Tasks D1-06 (secrets), D1-09 (this ADR's delivery work), D2-10 (audit anchoring)
