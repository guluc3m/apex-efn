#!/bin/sh
# Create or update the application database login role (D1-03, D2-04, ADR-206).
#
# The row-level-security migration (apps/web/prisma/migrations/20261109130000_row_level_security)
# creates the `apex_app` group role: NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS,
# plus its grants. A group role cannot log in and a password must never live in a migration, so the
# deployment creates the login role here, as the schema owner (the migrator):
#
#   apex_app_login  LOGIN, member of apex_app, NOBYPASSRLS  -> row-level security applies to it.
#
# This script is idempotent: it creates the login role when it is missing and then converges the
# attributes, membership, CONNECT grant and role setting on every run. Run it *after* the Prisma
# migrations (they create apex_app). Never connect as the app role to run it.
#
# Usage:
#   APEX_APP_DB_PASSWORD=... MIGRATE_DATABASE_URL=postgresql://apex:apex@localhost:5432/apex \
#     infra/postgres/bootstrap-app-role.sh
#   pnpm db:bootstrap                      # same thing with the dev defaults below
#
# Environment:
#   APEX_APP_DB_PASSWORD  Password for the login role. DEV DEFAULT "apex_app_dev" (see .env.example);
#                         production injects it from the Secret, never from a committed file.
#   MIGRATE_DATABASE_URL  Owner/migrator connection URI. Falls back to DATABASE_URL, then to libpq's
#                         PG* variables (host, port, user, database, password). The URL scheme must be
#                         postgresql:// or postgres://; a "?schema=public" query string is stripped
#                         because psql rejects URI parameters it does not know.
#   APEX_APP_DB_ROLE      Login role name. Default: apex_app_login.
#   APEX_APP_DB_NAME      Database the role may connect to. Default: apex.
#
# Requires psql >= 15 (this script uses \getenv, so the password never appears in psql's argv or in
# the shell history). PostgreSQL 16 is pinned everywhere in this repo.
set -eu

APEX_APP_DB_PASSWORD="${APEX_APP_DB_PASSWORD:-apex_app_dev}"
APEX_APP_DB_ROLE="${APEX_APP_DB_ROLE:-apex_app_login}"
APEX_APP_DB_NAME="${APEX_APP_DB_NAME:-apex}"
# \getenv reads these from the environment of the psql process, so they must be exported.
export APEX_APP_DB_PASSWORD APEX_APP_DB_ROLE APEX_APP_DB_NAME

log() {
  printf '[bootstrap-app-role] %s\n' "$*" >&2
}

if ! command -v psql >/dev/null 2>&1; then
  log "ERROR: psql not found on PATH. Run this inside the postgres container (see docs/runbooks/local-dev.md)."
  exit 127
fi

# Prefer the migrator DSN. Strip any Prisma-style query string: psql only accepts libpq URI parameters.
connection_url="${MIGRATE_DATABASE_URL:-${DATABASE_URL:-}}"
connection_url="${connection_url%%\?*}"

if [ "$APEX_APP_DB_PASSWORD" = "apex_app_dev" ]; then
  log "using the DEV-ONLY default password for $APEX_APP_DB_ROLE (set APEX_APP_DB_PASSWORD elsewhere)"
fi
log "bootstrapping login role $APEX_APP_DB_ROLE (member of apex_app, database $APEX_APP_DB_NAME)"

# psql reads the SQL from stdin, so the same block works from the host and inside the container.
# The password reaches format() as a psql variable and is quoted with %L, so quotes and backslashes
# are escaped by PostgreSQL itself. The generated statements run through \gexec and are never echoed.
run_psql() {
  psql "$@" --no-psqlrc --quiet --set=ON_ERROR_STOP=1 -f - <<'SQL'
-- The group role comes from the RLS migration. Without it there is nothing to join: fail loudly
-- instead of creating a login role that owns no grants.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apex_app') THEN
    RAISE EXCEPTION
      'role apex_app does not exist: apply the Prisma migrations first (D2-04, row-level security)';
  END IF;
END;
$$;

\getenv app_password APEX_APP_DB_PASSWORD
\getenv app_role APEX_APP_DB_ROLE
\getenv app_db APEX_APP_DB_NAME

-- Create only when missing. CREATE ROLE cannot run inside a transaction block, so a DO block is not
-- an option here; \gexec runs the generated statement in its own transaction.
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L IN ROLE apex_app',
  :'app_role', :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec

-- Converge on every run: login enabled, no elevated attributes, password current.
SELECT format(
  'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L',
  :'app_role', :'app_password'
)
\gexec

-- Membership is GRANT, not ALTER ROLE (ALTER ROLE has no IN ROLE option). Idempotent: re-granting an
-- existing membership is a NOTICE, not an error.
SELECT format('GRANT apex_app TO %I', :'app_role')
\gexec

-- The app connects over TCP. CONNECT is granted to PUBLIC by default; make it explicit so a
-- hardened cluster that revoked it still works.
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'app_db', :'app_role')
\gexec

-- A read-only default would make every write fail with "cannot execute ... in a read-only transaction".
SELECT format('ALTER ROLE %I SET default_transaction_read_only = off', :'app_role')
\gexec

SELECT format(
  'application login role %I is ready: member of apex_app, row-level security applies',
  :'app_role'
) AS bootstrap_result;
SQL
}

if [ -n "$connection_url" ]; then
  run_psql "$connection_url"
else
  # No DSN: use libpq's PG* variables, which is what `docker compose exec postgres sh -s` provides.
  run_psql
fi

log "done"
