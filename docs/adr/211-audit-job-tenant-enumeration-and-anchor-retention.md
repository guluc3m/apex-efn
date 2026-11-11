# ADR-211: Audit job tenant enumeration and WORM anchor retention

Status: **Accepted** (TL decision, 2026-11-11). Lane DEV-2, follow-up of D2-10 / D2-10b (#350).

## Context
`AuditChainService` (D2-10b) verifies and anchors every tenant, with the tenant list and the retention injected.
Two things were left open: how the job lists tenants when `tenants` is under FORCE RLS, and the Object Lock retention.

## Decisions
1. **Tenant enumeration:** the SQL function `apex_list_tenant_ids()` (SECURITY DEFINER, owned by the dedicated
   no-login role `apex_tenant_lister`, which can read only `tenants.id`). `apex_app` gets EXECUTE on it and still
   cannot read other tenants' rows. No second DSN, no BYPASSRLS role in the app. Deployments where the migrator
   is not allowed to `GRANT apex_tenant_lister TO` itself must pre-create the role with that grant.
2. **Retention:** `audit_anchor_retention_days`, default **2192 days (6 years)**, the commercial-records period
   (Código de Comercio art. 30). It is an operator setting (env `AUDIT_ANCHOR_RETENTION_DAYS`) and COMPLIANCE
   retention cannot be shortened later, so raise it only deliberately. An anchor holds a hash, never personal data,
   so it does not conflict with ADR-210 erasure.
3. `apex.audit.service.build_audit_chain_service(settings, clock)` builds the service (boto3 client from the S3
   settings, `Boto3AnchorStore`, the function above). The worker lane plugs it into `WorkerPorts.audit`.
