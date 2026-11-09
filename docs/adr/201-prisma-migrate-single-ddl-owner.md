# ADR-201: Prisma Migrate is the single owner of DDL

## Status

Accepted. ADR-900 Q9 approved the decision ("Prisma Migrate is the only owner of DDL, SQLAlchemy maps tables and
never migrates"). This ADR writes down the rules that follow from it. The TL reviews the details in the D2-02 PR.

## Context

Spec §5.5 puts Prisma (from `apps/web`) and SQLAlchemy 2 + Alembic (from `apps/orchestrator`) on **the same
schema**, with **one** package owning migrations to avoid drift. Both tools can emit DDL. If both did, each
would see the other's changes as drift. Prisma Migrate in particular detects objects it did not create and
offers to reset the database. AGENTS.md also says that only DEV-2 writes migrations, so migration
timestamps never collide.

Some objects the spec needs cannot be expressed in `schema.prisma`: row-level security policies (D2-04),
append-only triggers (D2-03), the `pgvector` extension and vector indexes, database roles and grants. They
still need one owner and one ordered history.

Third-party components also create tables: the LangGraph Postgres checkpointer (ADR-403 item 7) has a
`setup()` that creates its own tables, and Keycloak and Langfuse run their own migrations.

## Decision

1. **One history.** `apps/web/prisma/migrations/` is the only DDL history for the application database. It covers
   the `public` schema and every other schema the application creates. Migrations are applied with
   `prisma migrate deploy`, and with `prisma migrate dev` locally.
2. **Raw SQL goes in Prisma migrations.** RLS policies, triggers, functions, extensions (`vector`), roles, grants
   and indexes that Prisma cannot model are written with `prisma migrate dev --create-only` and edited by hand
   before they are applied. One concern per migration, with a comment that names the task (`-- D2-04: RLS`).
3. **SQLAlchemy only maps.** `apex.db` (D2-05) declares models that match the migrated tables. It never calls
   `metadata.create_all()`, never emits `ALTER`, and Alembic is not used for DDL. `alembic` stays out of runtime
   code. DEV-2 asks DEV-4 (owner of `pyproject.toml`) to drop the dependency once D2-05 lands.
4. **Naming.** Prisma models are PascalCase and map to snake_case plural tables (`@@map("audit_events")`) and
   snake_case columns (`@map`). SQLAlchemy, raw SQL and tests use the snake_case names.
5. **Drift is checked in CI from both sides.**
   - `migration-drift` (D1-04) runs `prisma migrate diff --from-migrations --to-schema-datamodel` and fails if
     `schema.prisma` and the migrations disagree.
   - D2-05 adds a test that migrates an empty database with Prisma, reflects it, and compares the result with the
     SQLAlchemy metadata.
   - Objects that `migrate diff` cannot see (policies, triggers) are covered by behaviour tests: the
     append-only triggers in D2-03 and the tenant isolation test in D2-04 (criterion 30).
6. **Roles.** Migrations run as a migrator role that owns the tables. The application connects as a separate role
   that is neither superuser, table owner nor `BYPASSRLS` (D2-04). Roles and grants are created by migrations,
   and passwords come from the environment or Vault, never from migration files.
7. **Third-party tables live outside Prisma's view.**
   - Keycloak and Langfuse use their own databases (`keycloak`, `langfuse`, D1-03).
   - The LangGraph checkpointer uses its own schema, `langgraph`. A Prisma migration creates the schema and
     grants the application role usage on it. The library's `setup()` creates the tables inside it. `setup()`
     runs as a deploy step under the migrator role, not on application start. The orchestrator connects with
     `search_path=langgraph` for the checkpointer DSN. The Prisma datasource manages `public` only, so these
     tables never show up as drift. They are not under RLS (ADR-403 item 7) and hold no secrets.
8. **Change process.** Other lanes request schema changes through a `schema-change` issue with the exact Prisma
   snippet. DEV-2 ships it as `D2-SC-<issue#>` (AGENTS.md 3.5). Destructive changes follow expand and contract:
   add, backfill, switch readers, then drop in a later migration, so the orchestrator and the web app can run
   against schema N and N+1 during a rollout.
9. **Migrations are append-only.** A merged migration is never edited. Mistakes are fixed with a new migration.

## Consequences

- One ordered history explains every object in the database, including security objects. That is what auditors
  and the WORM audit chain need.
- Developers of other lanes cannot add a column themselves. Schema changes take an issue and a DEV-2 PR.
- Hand-written SQL in migrations has no type checking. That is why the triggers and RLS policies are covered by
  behaviour tests, not by diffs.
- The LangGraph checkpointer's table layout is owned by the library version. Upgrading
  `langgraph-checkpoint-postgres` needs a deploy step that runs `setup()` again. DEV-4 records that in the
  upgrade PR.
- The spec mention of Alembic is resolved: SQLAlchemy is kept, and Alembic is not used.

## Related

- AGENTS.md section 2 (ownership of `apps/web/prisma/**` and `apex/db/**`), 3.5 (schema changes), 5 (D2-02 to D2-05)
- PROMPT-IMPLEMENTACION.md §5.5
- ADR-900 Q9, ADR-403 item 7 (checkpointer tables)
- ADR-202 (where business endpoints live)
