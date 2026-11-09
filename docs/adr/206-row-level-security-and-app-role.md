# ADR-206: Row-level security, the application role and tenant context

## Status

Accepted on 2026-11-09 by the repository owner, who waived the Tech Lead gate for the DEV-2 tasks. The TL has
not reviewed it and may amend or reverse it with a 900-range ADR.

## Context

Criterion 30 requires that tenant A can never read or write tenant B's data. ADR-201 item 6 says the application
connects as a role that is neither superuser, table owner nor `BYPASSRLS`, and that roles and grants are created
by migrations without passwords. ADR-205 put a `tenant_id` column on every tenant-scoped table and listed the
global tables. D2-04 turns that into policies.

## Decision

### Roles

- Migration `row_level_security` creates the role **`apex_app`** (`NOLOGIN`, no superuser, no `CREATEDB`,
  no `CREATEROLE`, no `BYPASSRLS`) if it does not exist. It gets `SELECT, INSERT, UPDATE, DELETE` on every table
  in `public` and default privileges for future tables. It gets nothing on `_prisma_migrations`.
- The application logs in as a role that is a member of `apex_app`, or the deployment turns `apex_app` itself
  into a login role (`ALTER ROLE apex_app LOGIN PASSWORD …`). The password comes from the environment or Vault,
  never from a migration. Wiring that in compose, Helm and `DATABASE_URL` is a DEV-1 platform request.
- Migrations, `prisma db seed`, `load_defaults` and the LangGraph `setup()` run as the **migrator**, which owns
  the tables. Seeding and default loading are cross-tenant administrative jobs.
- `apex_app` has `USAGE` on the `langgraph` schema and default DML privileges for the tables `setup()` creates.

### Tenant context

- The tenant is the transaction-local setting `app.tenant_id`, set with
  `SELECT set_config('app.tenant_id', $1, true)`. Being transaction-local, it cannot leak to the next user of a
  pooled connection.
- `apex_current_tenant()` returns `nullif(current_setting('app.tenant_id', true), '')`. When the setting is
  missing or empty, every policy compares against `NULL`, so tenant rows are invisible and cannot be written
  (fail closed).
- Python: `apex.db.session.tenant_session(tenant_id)` is an async context manager over SQLAlchemy. An
  `after_begin` session event sets the tenant on **every** transaction, so committing halfway keeps the tenant.
  It commits on exit and rolls back on error. `system_session()` sets no tenant and is for global tables only.
- TypeScript: `forTenant(prisma, tenantId)` in `apps/web/prisma/tenant-extension.ts` is a Prisma client
  extension that wraps each query in a batch transaction `[set_config, query]`. Per ADR-202, business data is
  read through the orchestrator, so this is for the few direct reads and for scripts.

### Policies

- **Tables with a `NOT NULL tenant_id`**: `apex_enable_tenant_rls(table)` enables and forces RLS and creates the
  policy `tenant_isolation` with `USING` and `WITH CHECK` `tenant_id = apex_current_tenant()`. The migration
  applies it to every such table it finds in the catalog. New tenant tables must call it in their migration.
- **`signing_keys` and `llm_events`** (nullable `tenant_id`): the tenant's own rows are readable and writable.
  Global rows (`tenant_id IS NULL`: service keys, LLM calls outside a tenant) are readable from any context
  through a separate `FOR SELECT` policy, but they can only be inserted, updated or deleted when no tenant is
  set. A tenant can never create, revoke, rotate or delete a service key.
- **`tenants`**: a tenant sees and writes only its own row (`id = apex_current_tenant()`).
- **`users`** (global, ADR-205): a tenant reads, updates and deletes only users that have a membership in it.
  Inserting a user needs a tenant context. The membership goes in the same transaction.
- **Global reference tables without RLS**: `sellers`, `seller_platform_ids`, `seller_signal_snapshots` and
  `fx_rates`. They hold public platform facts and market rates, never tenant data. Per-tenant seller
  **confidence** stays under RLS.
- `FORCE ROW LEVEL SECURITY` is set everywhere, so the policies apply even to the table owner. Superusers still
  bypass RLS, which is why the application must never use one.

### Out of scope for RLS

- The LangGraph checkpointer tables in `langgraph` are created by the library and carry no `tenant_id` column.
  Isolation there relies on thread IDs that the orchestrator derives from tenant-scoped mission IDs. Adding RLS
  to them would need a library change. This is a known gap, recorded here.
- Foreign key checks bypass RLS by design in Postgres. A tenant cannot learn anything from them beyond "this ID
  exists", and IDs are unguessable ULIDs.

### Test (criterion 30)

`apps/orchestrator/tests/db/test_tenant_isolation.py` reads the catalog, so it covers tables added later
without changes. It builds a valid row for tenant A in **every** table, writing through an `apex_app` login role
and following foreign keys. Then it asserts:

- every table either has a `tenant_id` with forced RLS and a policy, or is on the global list;
- tenant B reads, updates and deletes nothing of A, and an insert with `tenant_id = A` fails with `42501`;
- without a tenant nothing is visible;
- `apex_app` is not privileged, owns nothing, and cannot disable RLS or drop a policy.

`tests/db/test_session.py` and `apps/web/prisma/tenant-extension.test.ts` cover the two helpers.

## Consequences

- Every query from the application must go through `tenant_session` / `forTenant` or `system_session`.
  A forgotten tenant context returns empty results instead of leaking data.
- A table added without RLS fails the isolation test until it calls `apex_enable_tenant_rls` or is added to the
  global list here and in the test.
- Background jobs that work across tenants (FX ingestion, audit re-verification, gate SLA reminders) either loop
  over tenants with `tenant_session`, or use `system_session` for global data.
- DEV-1 must give the application its own login role in `apex_app` and its own `DATABASE_URL`. Until then the
  dev stack connects as the superuser `apex`, which bypasses RLS.

## Related

- ADR-201 (items 6 and 7), ADR-202, ADR-205
- AGENTS.md D2-04, D2-05; PROMPT-IMPLEMENTACION.md §5.10, criterion 30
