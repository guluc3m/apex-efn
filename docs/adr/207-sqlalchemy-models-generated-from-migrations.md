# ADR-207: SQLAlchemy models generated from the migrated database

## Status

Accepted on 2026-11-09 by the repository owner, who waived the Tech Lead gate for the DEV-2 tasks. The TL has
not reviewed it and may amend or reverse it with a 900-range ADR.

## Context

ADR-201 makes Prisma Migrate the only owner of DDL. The orchestrator still needs typed SQLAlchemy 2 models for the
same 44 tables, and D2-05 requires a CI check that fails when they drift from the migrations. Writing the models
by hand means keeping 44 classes, 37 enums, composite foreign keys and a partial unique index in sync with
`schema.prisma`, with nothing but review to catch a mistake.

## Decision

### Generated, not hand-written

- `python -m apex.db.codegen --database-url <migrated db>` reads the Postgres catalog of a database migrated with
  `apps/web/prisma/migrations` and writes `apps/orchestrator/src/apex/db/models/generated.py`. The output is
  formatted with `ruff format`, so it is byte-stable. **Never edit it by hand.**
- `--check` exits 1 when the committed file differs. The workflow for a schema change is: edit
  `schema.prisma`, add the migration (DEV-2 only), apply it locally, regenerate, commit both.
- `apex.db.models` re-exports everything in `generated.py`. Consumers import from `apex.db.models`.

### Mapping rules

- Class names are the Prisma model names, matched to tables through `@@map`. Tables are the `@@map` names.
- Postgres enums become `StrEnum` classes with the same name as the Postgres type. Columns use
  `postgresql.ENUM(Cls, name=..., create_type=False, values_callable=enum_values)`, so the database stores the
  labels and SQLAlchemy never emits `CREATE TYPE`. Enum arrays are `ARRAY(ENUM(...))`.
- Money and counters are `BigInteger` (int64). FX rates and ratios are `Numeric(p, s)` and load as `Decimal`.
  Timestamps are `TIMESTAMP(timezone=True, precision=6)` and load timezone-aware. JSON is `JSONB`.
- pgvector columns use `apex.db.types.Vector`, which sends and reads the text format `[1,2,3]`. It works with
  asyncpg and psycopg without registering a codec, and avoids a dependency on the `pgvector` package.
- Nullability, primary keys, foreign keys (with their names and `ON DELETE` / `ON UPDATE` actions) and indexes
  (including `postgresql_where` for the partial unique index) are mapped. Single-column foreign keys are inline,
  composite ones are `ForeignKeyConstraint`.
- **No relationships.** Async sessions cannot lazy-load, and implicit loading hides queries. Callers join or use
  `select(...)` explicitly. Relationships may be added later in hand-written mixins if a real need appears.
- CHECK constraints, triggers (append-only guards, ADR-205) and RLS policies (ADR-206) are not mapped. Postgres
  enforces them, and SQLAlchemy never creates tables (`Base.metadata.create_all()` must not be called).
- The generator stops with an error on anything it cannot map faithfully (unique constraints that are not
  indexes, expression indexes, unknown column types). None exist today; extending the generator is part of the
  migration that introduces them.

### Drift checks (CI)

`apps/orchestrator/tests/db/test_models.py`, in the integration job, against a database migrated from scratch:

1. the generator output equals the committed `generated.py`;
2. an independent SQLAlchemy reflection of the catalog matches `Base.metadata`: tables, column types,
   nullability, primary keys, foreign keys and indexes. This catches a bug in the generator itself;
3. an ORM round trip through `tenant_session` as an `apex_app` login role: bigint above 2^31, `Decimal` FX rate
   with 12 decimals, enums and an enum array, a vector and timezone-aware timestamps, plus a check that another
   tenant sees none of it.

A non-integration test checks that every Prisma model is mapped under its own name.

## Consequences

- A migration without regenerated models fails CI with a message that says how to fix it.
- The models describe the database as migrated, not `schema.prisma` directly. The `migration-drift` job already
  guarantees that the two agree.
- Generating needs a running Postgres with pgvector. Developers have one in the compose stack; CI uses
  Testcontainers.
- `ruff` is needed to generate (it is a dev dependency), not to import the models.

## Related

- ADR-201 (Prisma owns DDL), ADR-205 (schema conventions), ADR-206 (RLS and `tenant_session`)
- AGENTS.md D2-05; PROMPT-IMPLEMENTACION.md §5.5
