-- D2-13: read-only view of Postgres for the dbt marts. Dev credentials only (same as the dev compose stack).
CREATE DATABASE IF NOT EXISTS apex_pg
ENGINE = PostgreSQL('postgres:5432', 'apex', 'analytics_reader', 'analytics_reader', 'public');
CREATE DATABASE IF NOT EXISTS analytics;
