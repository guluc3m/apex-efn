-- D2-10c (ADR-211): the scheduled audit job must visit every tenant, but `tenants` is under FORCE row-level
-- security and `apex_app` sees only its own row. A narrow SECURITY DEFINER function returns tenant ids and
-- nothing else. Its owner is a dedicated role that can read only `tenants.id`, not a superuser.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apex_tenant_lister') THEN
    CREATE ROLE apex_tenant_lister NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END;
$$;

-- The migrator must be a member to hand the function over (PG16: the creator holds ADMIN OPTION).
GRANT apex_tenant_lister TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO apex_tenant_lister;
GRANT SELECT (id) ON tenants TO apex_tenant_lister;
CREATE POLICY tenant_ids_for_lister ON tenants FOR SELECT TO apex_tenant_lister USING (true);

CREATE FUNCTION apex_list_tenant_ids() RETURNS SETOF text
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
  AS $$ SELECT id FROM tenants ORDER BY id $$;
ALTER FUNCTION apex_list_tenant_ids() OWNER TO apex_tenant_lister;
REVOKE ALL ON FUNCTION apex_list_tenant_ids() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION apex_list_tenant_ids() TO apex_app;
