-- Una base de datos por servicio. La de la app ("apex") la crea POSTGRES_DB.
-- Solo se ejecuta con el volumen vacío: tras cambiarlo, `docker compose down -v`.
CREATE DATABASE keycloak;
CREATE DATABASE langfuse;
CREATE DATABASE unleash;

-- pgvector para embeddings (productos, histórico de negociaciones). Lo usa DEV-2 (D2-03).
\connect trato
CREATE EXTENSION IF NOT EXISTS vector;
