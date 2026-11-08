-- Una base de datos por servicio. La de la app ("apex") la crea POSTGRES_DB.
-- Solo se ejecuta con el volumen vacío: tras cambiarlo, `docker compose down -v`.
CREATE DATABASE keycloak;
CREATE DATABASE langfuse;
