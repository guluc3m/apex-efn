#!/usr/bin/env bash
# Migration drift (D1-04, activates with D2-03): the Prisma schema must match the migrations.
# Needs a shadow database: SHADOW_DATABASE_URL (CI starts a Postgres service), or else a throwaway
# pgvector container started here. No URL and no Docker means FAIL.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [ ! -d apps/web/prisma/migrations ]; then
  skip "apps/web/prisma/migrations does not exist yet (activates with D2-03)"
fi

require_cmd pnpm "install pnpm 9 and run pnpm install --frozen-lockfile"

container=""
cleanup() {
  if [ -n "${container}" ]; then
    docker rm -f "${container}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [ -z "${SHADOW_DATABASE_URL:-}" ]; then
  require_docker "migration-drift starts a shadow Postgres container when SHADOW_DATABASE_URL is not set"
  container="apex-ci-shadow-$$"
  docker run -d --rm --name "${container}" -p 127.0.0.1::5432 \
    -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=shadow \
    pgvector/pgvector:pg16 >/dev/null
  port="$(docker port "${container}" 5432/tcp | sed -n '1s/.*://p')"
  for _ in $(seq 1 60); do
    if docker exec "${container}" pg_isready -U postgres >/dev/null 2>&1; then break; fi
    sleep 1
  done
  SHADOW_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:${port}/shadow"
  export SHADOW_DATABASE_URL
fi

pnpm --filter @apex/web exec prisma migrate diff \
  --from-migrations prisma/migrations \
  --to-schema-datamodel prisma/schema.prisma \
  --shadow-database-url "${SHADOW_DATABASE_URL}" \
  --exit-code
