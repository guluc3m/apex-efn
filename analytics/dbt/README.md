# APEX analytics marts (D2-13)

dbt over ClickHouse. ClickHouse reads Postgres through the `apex_pg` database (read-only `analytics_reader` role,
see `infra/clickhouse/init.sql`). Marts: `price_history_daily`, `benchmarks` (12 months, feeds the sanity
reference, spec 3.3.1 item 3) and `savings`.

```bash
docker compose up -d postgres clickhouse
cd analytics/dbt && uvx --from dbt-core --with dbt-clickhouse dbt build --profiles-dir .
```

Every mart keeps `tenant_id`. The reader role bypasses RLS, so a consumer must always filter by tenant.
