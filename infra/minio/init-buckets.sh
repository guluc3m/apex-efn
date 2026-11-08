#!/bin/sh
# Crea los buckets de desarrollo. Idempotente: se puede ejecutar de nuevo sin efectos.
# Ejecutado por el servicio `minio-init` de infra/docker-compose.yml.
set -eu

: "${MINIO_ENDPOINT:?MINIO_ENDPOINT no definido}"
: "${MINIO_ROOT_USER:?MINIO_ROOT_USER no definido}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD no definido}"
# SOLO DESARROLLO. La retención de producción (modo COMPLIANCE) es una decisión del TL.
: "${MINIO_AUDIT_RETENTION:=1d}"

mc alias set local "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

# Object Lock exige versionado; `--with-lock` lo activa al crear el bucket.
mc mb --ignore-existing --with-lock local/apex-attachments
mc mb --ignore-existing --with-lock local/apex-csv
mc mb --ignore-existing --with-lock local/apex-audit

# Retención por defecto en COMPLIANCE: ni el propio root puede borrar versiones antes de caducar.
mc retention set --default COMPLIANCE "$MINIO_AUDIT_RETENTION" local/apex-audit

echo "apex buckets listos (audit retention=$MINIO_AUDIT_RETENTION, dev only)"
