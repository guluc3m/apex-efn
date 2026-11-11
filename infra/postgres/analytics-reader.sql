-- D2-13: read-only role for ClickHouse. BYPASSRLS because the marts keep tenant_id as a column and are
-- never exposed across tenants: every consumer of the marts must filter by tenant_id.
CREATE ROLE analytics_reader LOGIN PASSWORD 'analytics_reader' BYPASSRLS;
