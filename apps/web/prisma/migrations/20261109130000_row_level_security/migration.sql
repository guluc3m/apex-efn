-- D2-04: application role, grants and row-level security (ADR-201 item 6, ADR-206).
--
-- The application connects as a member of `apex_app`. That role is not a superuser, does not own any table and
-- does not have BYPASSRLS. Migrations run as the migrator, which owns the tables. Passwords never appear here:
-- the deployment gives `apex_app` (or a login role that is a member of it) its password from the environment.
--
-- The tenant comes from the transaction-local setting `app.tenant_id`. When it is unset or empty, tenant rows
-- are invisible and cannot be written (fail closed).

-- =============================================================================
-- Application role
-- =============================================================================

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apex_app') THEN
    CREATE ROLE apex_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END;
$$;

GRANT USAGE ON SCHEMA public TO apex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO apex_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO apex_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO apex_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO apex_app;

-- Prisma's bookkeeping table is for the migrator only.
DO $$
BEGIN
  IF to_regclass('public._prisma_migrations') IS NOT NULL THEN
    REVOKE ALL ON TABLE public._prisma_migrations FROM apex_app;
  END IF;
END;
$$;

-- LangGraph checkpointer (ADR-201 item 7): setup() creates the tables later, as the migrator.
GRANT USAGE ON SCHEMA langgraph TO apex_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO apex_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph GRANT USAGE, SELECT ON SEQUENCES TO apex_app;

-- =============================================================================
-- Tenant context
-- =============================================================================

CREATE FUNCTION apex_current_tenant() RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT nullif(current_setting('app.tenant_id', true), '')
$$;

-- Enables and forces RLS on a tenant-scoped table with the standard policy. New tenant tables must call it in
-- their migration; the isolation test fails for any table with a tenant_id column and no policy.
CREATE FUNCTION apex_enable_tenant_rls(tbl regclass) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', tbl);
  EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', tbl);
  EXECUTE format(
    'CREATE POLICY tenant_isolation ON %s USING (tenant_id = apex_current_tenant()) '
    'WITH CHECK (tenant_id = apex_current_tenant())', tbl);
END;
$$;

DO $$
DECLARE
  t text;
BEGIN
  FOR t IN
    SELECT c.table_name
    FROM information_schema.columns c
    JOIN information_schema.tables tb
      ON tb.table_schema = c.table_schema AND tb.table_name = c.table_name AND tb.table_type = 'BASE TABLE'
    WHERE c.table_schema = 'public' AND c.column_name = 'tenant_id' AND c.is_nullable = 'NO'
    ORDER BY c.table_name
  LOOP
    PERFORM apex_enable_tenant_rls(format('public.%I', t)::regclass);
  END LOOP;
END;
$$;

-- Tables whose tenant_id may be null: service signing keys and LLM calls made outside a tenant. Global rows are
-- readable from any context, but they can only be inserted, updated or deleted when no tenant is set, so a tenant
-- can never create, revoke, rotate or delete a service key. Permissive policies are OR-ed per command, so SELECT
-- gets both and every write gets only the strict one.
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['signing_keys', 'llm_events'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I '
      'USING (tenant_id = apex_current_tenant() OR (tenant_id IS NULL AND apex_current_tenant() IS NULL)) '
      'WITH CHECK (tenant_id = apex_current_tenant() OR (tenant_id IS NULL AND apex_current_tenant() IS NULL))',
      t);
    EXECUTE format(
      'CREATE POLICY global_read ON %I FOR SELECT USING (tenant_id IS NULL)', t);
  END LOOP;
END;
$$;

-- A tenant sees only its own row.
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenants
  USING (id = apex_current_tenant())
  WITH CHECK (id = apex_current_tenant());

-- Users are global, but a tenant sees only its members. Inserting a user needs a tenant context; insert the
-- membership in the same transaction, and do not read the user back before the membership exists.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
CREATE POLICY members_read ON users FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM memberships m WHERE m.user_id = users.id AND m.tenant_id = apex_current_tenant()
  ));
CREATE POLICY members_update ON users FOR UPDATE
  USING (EXISTS (
    SELECT 1 FROM memberships m WHERE m.user_id = users.id AND m.tenant_id = apex_current_tenant()
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM memberships m WHERE m.user_id = users.id AND m.tenant_id = apex_current_tenant()
  ));
CREATE POLICY members_delete ON users FOR DELETE
  USING (EXISTS (
    SELECT 1 FROM memberships m WHERE m.user_id = users.id AND m.tenant_id = apex_current_tenant()
  ));
CREATE POLICY provision ON users FOR INSERT
  WITH CHECK (apex_current_tenant() IS NOT NULL);

-- Global reference data stays outside RLS: sellers, seller_platform_ids, seller_signal_snapshots and fx_rates
-- hold public platform facts and market rates, never tenant data (ADR-205).
