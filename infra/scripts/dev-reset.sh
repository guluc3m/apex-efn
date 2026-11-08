#!/usr/bin/env bash
# Reinicio completo del entorno local: borra volúmenes (datos de Postgres, MinIO, Keycloak...),
# levanta los servicios y ejecuta migraciones y seed solo si ya existen en el repo.
# Uso: pnpm dev:reset   (desde la raíz del repositorio)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Valor de desarrollo por defecto. Solo se usa si no hay DATABASE_URL en el entorno.
export DATABASE_URL="${DATABASE_URL:-postgresql://apex:apex@localhost:5432/apex?schema=public}"

log() {
  printf '[dev-reset] %s\n' "$*"
}

log "Borrando contenedores y volúmenes (datos locales)."
log "Nota: MinIO con Object Lock en COMPLIANCE no permite borrar objetos antes de caducar; aquí se borra el volumen entero."
docker compose down -v --remove-orphans

log "Levantando servicios (espera a los que tienen healthcheck)."
docker compose up -d --wait

if [ -d apps/web/prisma/migrations ]; then
  log "Aplicando migraciones Prisma (apps/web)."
  pnpm --filter @apex/web exec prisma migrate deploy
else
  log "Omitido: no hay migraciones Prisma todavía (D2-03)."
fi

if [ -f apps/web/prisma/seed.ts ]; then
  log "Sembrando datos Prisma (apps/web)."
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

log "Entorno listo."
