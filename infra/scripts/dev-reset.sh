#!/usr/bin/env bash
# Reinicio completo del entorno local: borra volúmenes (datos de Postgres, S3, Keycloak...),
# levanta PostgreSQL, aplica migraciones y seed como el propietario del esquema, crea el rol de login
# de la aplicación (RLS) y solo entonces levanta el resto de servicios.
# Uso: pnpm dev:reset   (desde la raíz del repositorio)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Valor de desarrollo por defecto. Solo se usa si no hay MIGRATE_DATABASE_URL en el entorno.
# Las migraciones, el seed y load_defaults NUNCA usan el rol de la aplicación: ese rol está sujeto a
# row-level security y no es dueño de las tablas (ver docs/runbooks/local-dev.md, "Database roles").
export MIGRATE_DATABASE_URL="${MIGRATE_DATABASE_URL:-postgresql://apex:apex@localhost:5432/apex}"
# Contraseña del rol de login de la aplicación. Solo desarrollo; en staging/producción viene del Secret.
export APEX_APP_DB_PASSWORD="${APEX_APP_DB_PASSWORD:-apex_app_dev}"

# Prisma lee DATABASE_URL. Debe ser el propietario del esquema, nunca apex_app_login.
prisma_url="$MIGRATE_DATABASE_URL"
case "$prisma_url" in
  *\?*) ;;
  *) prisma_url="$prisma_url?schema=public" ;;
esac
export DATABASE_URL="$prisma_url"

log() {
  printf '[dev-reset] %s\n' "$*"
}

# Ejecuta infra/postgres/bootstrap-app-role.sh con el psql del host si existe; si no, dentro del
# contenedor de PostgreSQL (no hace falta instalar clientes en la máquina).
bootstrap_app_role() {
  if command -v psql >/dev/null 2>&1; then
    log "psql disponible en el host: creando el rol con MIGRATE_DATABASE_URL."
    MIGRATE_DATABASE_URL="$MIGRATE_DATABASE_URL" APEX_APP_DB_PASSWORD="$APEX_APP_DB_PASSWORD" \
      sh infra/postgres/bootstrap-app-role.sh
    return 0
  fi
  log "psql no está en el host: creando el rol dentro del contenedor postgres."
  if ! docker compose exec -T \
    -e PGUSER=apex -e PGDATABASE=apex \
    -e APEX_APP_DB_PASSWORD="$APEX_APP_DB_PASSWORD" \
    postgres sh -s <infra/postgres/bootstrap-app-role.sh; then
    log "ERROR: no se pudo crear/actualizar el rol de login de la aplicación."
    return 1
  fi
}

log "Borrando contenedores y volúmenes (datos locales)."
log "Nota: S3 con Object Lock en COMPLIANCE no permite borrar objetos antes de caducar; aquí se borra el volumen entero."
docker compose down -v --remove-orphans

log "Levantando PostgreSQL (las migraciones necesitan la base de datos)."
docker compose up -d --wait postgres

if [ -d apps/web/prisma/migrations ]; then
  log "Aplicando migraciones Prisma como el propietario del esquema (MIGRATE_DATABASE_URL)."
  pnpm --filter @apex/web exec prisma migrate deploy
else
  log "Omitido: no hay migraciones Prisma todavía (D2-03)."
fi

if [ -f apps/web/prisma/seed.ts ]; then
  log "Sembrando datos Prisma como el propietario del esquema."
  pnpm --filter @apex/web exec prisma db seed
else
  log "Omitido: no hay seed Prisma todavía (D2-03)."
fi

if [ -f apps/orchestrator/src/apex/tenant_config/load_defaults.py ]; then
  log "Cargando configuración por defecto de los tenants."
  (cd apps/orchestrator && uv run python -m apex.tenant_config.load_defaults)
else
  log "Omitido: no existe apex.tenant_config.load_defaults todavía (D4-03)."
fi

# Después de las migraciones: la migración de RLS crea el grupo apex_app, y este paso crea el login
# apex_app_login que se une a él. Antes de levantar la aplicación, para que arranque con un DSN válido.
if [ -f infra/postgres/bootstrap-app-role.sh ]; then
  log "Creando/actualizando el rol de login de la aplicación (apex_app_login, sujeto a RLS)."
  bootstrap_app_role
else
  log "Omitido: no existe infra/postgres/bootstrap-app-role.sh."
fi

log "Levantando el resto del entorno (espera a los healthchecks)."
docker compose up -d --wait

log "Entorno listo."
