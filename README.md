# APEX-EFN (Apex Platform Enterprise Xchange - Element Fintech Network)

<img width="1321" height="529" alt="image" src="https://github.com/user-attachments/assets/2315fc91-7a9d-4c05-a66a-d791e64b827b" />

> Plataforma B2B de sourcing inteligente y negociación automatizada de compras por volumen

## Descripción

APEX-EFN es un **agente de compras** que:

1. **Perfila a la empresa** (quién compra, para qué, con qué dinero, con qué restricciones)
2. **Busca** productos en múltiples plataformas y proveedores
3. **Puntúa la confianza de cada vendedor** a partir de su antigüedad, ventas, catálogo y reseñas
4. **Descarta precios anómalos** comparando cada oferta contra el mercado
5. **Regatea** con los vendedores en sus propios canales de chat
6. **Evalúa financieramente** cada resultado contra la capacidad real de pago
7. **Presenta los tratos finales en un dashboard** donde un responsable humano decide
8. **Firma criptográficamente toda decisión** dejando un rastro verificable

## Estructura del Proyecto

```
/apps
  /web              Next.js 15 (frontend + BFF, dashboard y firma)
  /orchestrator     FastAPI + LangGraph (agentes, trust, sanity, scoring)
  /browser-worker   Node/TS + Puppeteer (scraping y negociación)

/packages
  /shared-types     Esquemas Zod + tipos generados desde OpenAPI
  /money            Aritmética monetaria y FX (EUR/USD/CNY)
  /scoring          Confianza de vendedor y MCDA
  /crypto-client    Firma Ed25519 en navegador (WebCrypto)
  /ui               Design system (shadcn/ui + Tailwind)
  /eslint-config    Configuración ESLint compartida
  /tsconfig         Configuración TypeScript compartida

/infra              Docker Compose / Helm / Terraform
/docs               ADRs, runbooks, compliance por plataforma
```

## Requisitos

- **Node.js** >= 22.0.0
- **pnpm** >= 9.0.0
- **Python** >= 3.12
- **Docker** y **Docker Compose**

## Desarrollo Local

```bash
# Instalar dependencias
pnpm install

# Levantar servicios (Postgres, Redis, RustFS, Keycloak, Langfuse, LLM stub)
cd infra && docker compose up -d

# Ejecutar migraciones
pnpm db:migrate

# Desarrollo
pnpm dev
```

## Despliegue

La referencia de staging/producción es AWS + EKS + Helm: [runbook de despliegue](docs/runbooks/deploy.md) y
[ADR-100](docs/adr/100-aws-deployment-target.md). El chart `infra/helm/apex` ya separa la web de la API; Keycloak
es un servicio externo o se publica con su propia Ingress. La topología pública recomendada es:

| Host público       | Upstream            | Qué sirve                                                 |
| ------------------ | ------------------- | --------------------------------------------------------- |
| `app.example.com`  | `web:3000`          | UI Next.js, BFF `/api/auth/*` y proxy `/api/v1/*`         |
| `api.example.com`  | `orchestrator:8000` | API pública `/v1/*`, `/health` y webhooks de plataformas  |
| `auth.example.com` | `keycloak:8080`     | OIDC del realm `apex` (`/realms/apex/*` y `/resources/*`) |

Solo se publican **80/tcp** (redirección a HTTPS y ACME) y **443/tcp**. El resto de puertos son internos del
cluster o de los servicios gestionados (RDS, ElastiCache, S3) y no deben abrirse a Internet.

### Puertos

| Puerto               | Servicio                            | Expuesto | Notas                                                                     |
| -------------------- | ----------------------------------- | -------- | ------------------------------------------------------------------------- |
| `80/tcp`             | reverse proxy                       | sí       | `301` a `https://` y `/.well-known/acme-challenge/`                       |
| `443/tcp`            | reverse proxy                       | sí       | TLS, HTTP/2; único puerto de aplicación publicado                         |
| `3000/tcp`           | `web` (Next.js + BFF)               | ingress  | upstream de `app.example.com`                                             |
| `8000/tcp`           | `orchestrator` (FastAPI)            | ingress  | upstream de `api.example.com`; también lo llama la web por la red interna |
| `8080/tcp`           | Keycloak                            | ingress  | upstream de `auth.example.com`; TLS termina en el proxy                   |
| `4010/tcp`           | `browser-worker` (API interna)      | no       | solo lo llama el orquestador; el chart aún no crea un Service (D5-01)     |
| `5432/tcp`           | PostgreSQL / RDS                    | no       | solo desde los pods/servicios autorizados                                 |
| `6379/tcp`           | Redis / ElastiCache                 | no       | solo desde los pods autorizados                                           |
| `9000/tcp`           | RustFS local / endpoint S3          | no       | S3 es interno; en producción se usa el endpoint de AWS S3 por `443`       |
| `8200/tcp`           | Vault                               | no       | solo orquestador y browser-worker                                         |
| `4317`, `4318/tcp`   | OpenTelemetry collector             | no       | OTLP desde los pods; nunca público                                        |
| `4242/tcp`           | Unleash                             | no       | solo clientes de feature flags                                            |
| `3001/tcp`           | Langfuse                            | no       | operación; VPN o allowlist, nunca Internet abierta                        |
| `3002/tcp`           | Grafana                             | no       | operación; VPN o allowlist                                                |
| `9090/tcp`           | Prometheus                          | no       | operación; VPN o allowlist                                                |
| `3100/tcp`           | Loki                                | no       | operación; interno                                                        |
| `3200/tcp`           | Tempo                               | no       | operación; interno                                                        |
| `8123/tcp`           | ClickHouse                          | no       | analítica interna                                                         |
| `8001/tcp`           | LLM gateway / stub                  | no       | solo orquestador; en producción puede ser un endpoint externo por `443`   |
| `9001/tcp`           | consola de RustFS                   | no       | solo desarrollo; no existe en producción                                  |
| `13000`, `13001/tcp` | Camoufox / CRW (stack de navegador) | no       | solo desarrollo; no forma parte del despliegue de staging                 |

### Endpoints públicos

La web expone la aplicación y el BFF; el navegador **no necesita** llamar al orquestador directamente.

**`app.example.com`**

- `/`, `/login` y `/{es,en,zh}/...`: landing, acceso y aplicación (las rutas de `(app)` exigen sesión).
- `/_next/static/*`, `/_next/image*`, `/brand/*`, `/favicon.ico`: assets de Next.js.
- `/api/auth/*`: Auth.js. Incluye `signin`, `callback/keycloak`, `signout`, `session`, `csrf`, `providers` y `error`.
- `/api/v1/{path}`: proxy BFF hacia `orchestrator:8000/v1/{path}`. Añade el bearer del servidor, el
  `Idempotency-Key` en escrituras y pasa el stream SSE sin bufferizar.
- `GET /api/v1/missions/{id}/events`: SSE de progreso y transcripción en vivo.

**`api.example.com`**

Todas las rutas llevan el prefijo `/v1` y autenticación `Authorization: Bearer <access token>`, salvo
`/health` y el webhook (HMAC). El contrato completo y los esquemas están en
[`contracts/openapi.yaml`](contracts/openapi.yaml).

| Área                | Rutas                                                                                                                                                                                                                                                                                                                                             |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Categorías/perfiles | `GET /categories` · `GET /profiles`                                                                                                                                                                                                                                                                                                               |
| Onboarding          | `GET,POST /onboarding/sessions` · `GET,PATCH /onboarding/sessions/{id}` · `GET,POST /onboarding/sessions/{id}/messages` · `POST /onboarding/{id}/financial-csv` · `POST /onboarding/{id}/financial-csv/mapping` · `GET /onboarding/{id}/financial-csv/{import_id}` · `POST /onboarding/{id}/financial-csv/activate`                               |
| Sourcing            | `POST /sourcing-requests`                                                                                                                                                                                                                                                                                                                         |
| Misiones            | `GET,POST /missions` · `GET /missions/{id}` · `POST /missions/{id}/pause` · `POST /missions/{id}/resume` · `POST /missions/{id}/cancel` · `GET /missions/{id}/events` · `GET /missions/{id}/offers` · `GET /missions/{id}/recommendation` · `GET /missions/{id}/recommendation/export`                                                            |
| Vendedores          | `GET /sellers/{id}/confidence` · `POST /sellers/{id}/confidence/recompute`                                                                                                                                                                                                                                                                        |
| Dashboard           | `GET /dashboard/deals` · `GET /dashboard/deals/{id}` · `GET /dashboard/summary` · `POST /dashboard/deals/{id}/actions`                                                                                                                                                                                                                            |
| Gate                | `GET /gate/queue` · `POST /gate/queue/{id}/actions`                                                                                                                                                                                                                                                                                               |
| Aprobaciones        | `GET /approvals` · `GET /approvals/{id}` · `GET /approvals/{id}/documents/{kind}` · `POST /approvals/{id}/notify-finance`                                                                                                                                                                                                                         |
| Cuentas             | `GET,POST /connected-accounts` · `DELETE /connected-accounts/{id}`                                                                                                                                                                                                                                                                                |
| Configuración       | `GET /config/effective` · `GET /config/versions` · `POST /config/proposals`                                                                                                                                                                                                                                                                       |
| Negociación         | `POST /negotiations/{id}/takeover` · `POST /negotiations/{id}/resume` · `POST /negotiations/{id}/abort` · `POST /negotiations/{id}/reopen` · `GET /negotiations/{id}` · `GET,POST /negotiations/{id}/messages` · `POST /negotiations/{id}/messages/{message_id}/translate` · `POST /negotiations/{id}/approve` · `POST /negotiations/{id}/reject` |
| Firma               | `POST,DELETE /signing-sessions` · `GET,DELETE /signing-sessions/{id}` · `POST /decisions` · `GET /decisions/{id}` · `POST /decisions/{id}/sign` · `POST /decisions/{id}/verify` · `GET,POST /keys/me` · `POST /keys/{id}/revoke`                                                                                                                  |
| Auditoría           | `GET /audit` · `GET /audit/verify`                                                                                                                                                                                                                                                                                                                |
| Webhooks            | `POST /webhooks/platforms/{platform}`                                                                                                                                                                                                                                                                                                             |

- `GET /v1/missions/{id}/events` es `text/event-stream`: el proxy debe desactivar buffering y permitir una
  conexión larga (ver nginx). Se reanuda con `Last-Event-ID`.
- `POST /v1/webhooks/platforms/{platform}` se autentica con `X-Platform-Signature` (HMAC-SHA256), no con cookie.
  Debe ser alcanzable desde las plataformas. La ruta aún comparte la dependencia OIDC global; hasta que D5-11 la
  exima, no la publiques o recibirá `401` antes de validar la firma.
- El CSV financiero tiene un límite de **5 MiB**; el proxy debe aceptar al menos ese cuerpo.
- `GET /health` es liveness del orquestador. Los probes de Kubernetes no necesitan la Ingress; si el balanceador
  lo usa, restringe el acceso a la red interna.
- Algunas rutas del contrato todavía responden `501` porque su motor no está mergeado; la superficie y el proxy no
  cambian por ello.

**`auth.example.com`**

- `/realms/apex/.well-known/openid-configuration`
- `/realms/apex/protocol/openid-connect/auth`, `/token`, `/certs`, `/logout`, `/userinfo`
- `/realms/apex/login-actions/*` (login, OTP y step-up con ACR)
- `/resources/*` (temas y assets del login)
- **No publicar** `/admin/*` ni `/realms/master/*`. La consola de administración debe quedar en VPN/allowlist.

### Variables de entorno del borde

| Variable               | Valor recomendado                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| `AUTH_URL`             | `https://app.example.com`                                                                              |
| `AUTH_KEYCLOAK_ISSUER` | `https://auth.example.com/realms/apex`                                                                 |
| `AUTH_KEYCLOAK_ID`     | `apex-web` (cliente confidencial del realm)                                                            |
| `APEX_AUTH_ISSUER`     | `https://auth.example.com/realms/apex` (mismo `iss` que valida el orquestador)                         |
| `APEX_AUTH_JWKS_URL`   | `http://keycloak:8080/realms/apex/protocol/openid-connect/certs` (interno)                             |
| `ORCHESTRATOR_URL`     | `http://orchestrator:8000` (solo lo usa la web en la red interna)                                      |
| `S3_ENDPOINT`          | endpoint interno de S3; el navegador nunca lo necesita                                                 |
| `CORS_ORIGINS`         | `["https://app.example.com"]` solo si el navegador llama a `api.example.com`; con el BFF no hace falta |

En Keycloak, el cliente `apex-web` necesita `Valid redirect URIs` con
`https://app.example.com/api/auth/callback/keycloak`, `Web origins` con `https://app.example.com` y el
`post.logout.redirect.uris` correspondiente. El issuer y la URL pública deben coincidir exactamente: si Keycloak
emite `iss=https://auth.example.com/realms/apex`, el orquestador y Auth.js deben validar ese valor.

### Requisitos del reverse proxy

- Termina TLS y envía `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto` y
  `X-Forwarded-Port` a los upstreams.
- No cachees `/api/*` ni `/v1/*`: hay datos autenticados y respuestas `no-store`.
- SSE (`/api/v1/missions/{id}/events` y `/v1/missions/{id}/events`): `proxy_buffering off`, `proxy_cache off`,
  `Connection ""` y timeout de una hora. Respeta `Last-Event-ID` y `X-Accel-Buffering: no`.
- Subidas: `client_max_body_size 8m` cubre el CSV de 5 MiB con margen.
- Webhooks: preserva el cuerpo **crudo** (no reescribas JSON ni añadas auth de usuario); la firma HMAC cubre los
  bytes exactos. Si el proxy añade cabeceras, no cambia el cuerpo.
- Keycloak: `KC_HOSTNAME=https://auth.example.com`, `KC_PROXY_HEADERS=xforwarded` y `KC_HTTP_ENABLED=true` detrás
  del TLS del proxy. No expongas la consola de administración.
- Operación: Grafana, Langfuse, Prometheus, Loki, Tempo, Unleash, Vault, RustFS y las bases de datos van por VPN,
  allowlist o red interna; nunca por la Ingress pública.

### Ejemplo de nginx

Sustituye los hosts, certificados y nombres de servicio por los de tu entorno (`web`, `orchestrator` y `keycloak`
son los nombres del compose; en Kubernetes usa el DNS del `Service`).

```nginx
upstream apex_web {
    server web:3000;
    keepalive 32;
}

upstream apex_api {
    server orchestrator:8000;
    keepalive 32;
}

upstream apex_keycloak {
    server keycloak:8080;
    keepalive 16;
}

# 80: ACME + redirección a HTTPS.
server {
    listen 80;
    server_name app.example.com api.example.com auth.example.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# Web + BFF. Todo el tráfico del navegador entra por aquí.
server {
    listen 443 ssl;
    http2 on;
    server_name app.example.com;

    ssl_certificate     /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    client_max_body_size 8m;
    server_tokens off;

    # SSE del BFF: sin buffer y con conexión larga.
    location ~ ^/api/v1/missions/[^/]+/events$ {
        proxy_pass http://apex_web;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1h;
        proxy_send_timeout 1h;
    }

    location / {
        proxy_pass http://apex_web;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
    }
}

# API pública y webhooks. La web no necesita este host: usa el BFF.
server {
    listen 443 ssl;
    http2 on;
    server_name api.example.com;

    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    client_max_body_size 8m;
    server_tokens off;

    # SSE de misiones.
    location ~ ^/v1/missions/[^/]+/events$ {
        proxy_pass http://apex_api;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1h;
        proxy_send_timeout 1h;
    }

    # Webhooks de plataformas: cuerpo crudo, solo POST y sin auth de usuario.
    location ^~ /v1/webhooks/platforms/ {
        limit_except POST { deny all; }
        proxy_pass http://apex_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_request_buffering off;
        proxy_buffering off;
    }

    location /v1/ {
        proxy_pass http://apex_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
    }

    # Health: solo el balanceador/monitorización, no Internet.
    location = /health {
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        deny all;
        proxy_pass http://apex_api;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Keycloak: solo el realm apex y sus assets. Nunca /admin ni /realms/master.
server {
    listen 443 ssl;
    http2 on;
    server_name auth.example.com;

    ssl_certificate     /etc/letsencrypt/live/auth.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/auth.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    server_tokens off;

    location /realms/apex/ {
        proxy_pass http://apex_keycloak;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
    }

    location /resources/ {
        proxy_pass http://apex_keycloak;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /admin/ {
        return 404;
    }

    location /realms/master/ {
        return 404;
    }
}
```

El chart ya tiene `ingress.enabled`, `ingress.web.host`, `ingress.api.host` y `ingress.tls` para los hosts de web y
API; Keycloak y los servicios de operación necesitan su propia Ingress o un servicio gestionado. Si añades una ruta
al contrato, actualiza esta sección: la fuente de verdad es `contracts/openapi.yaml`.

## Stack

| Componente     | Tecnología                                         |
| -------------- | -------------------------------------------------- |
| Frontend       | Next.js 15, React 19, TanStack Query, Tailwind CSS |
| BFF            | Next.js API Routes                                 |
| Orquestador    | FastAPI, LangGraph, Celery                         |
| Scraping       | Puppeteer, Playwright, BullMQ                      |
| Base de datos  | PostgreSQL 16, Prisma + SQLAlchemy                 |
| Caché/Colas    | Redis                                              |
| Almacenamiento | S3-compatible (RustFS/R2)                          |
| Auth           | Keycloak (OIDC)                                    |
| LLM            | Compatible OpenAI (`/v1/chat/completions`)         |
| Observabilidad | OpenTelemetry, Langfuse, Grafana                   |

## Documentación

- [PROMPT-IMPLEMENTACION.md](./PROMPT-IMPLEMENTACION.md) — Especificación completa del producto
- [NOTAS-TECH-LEAD.md](./NOTAS-TECH-LEAD.md) — Decisiones y supuestos
- [docs/adr/](./docs/adr/) — Architecture Decision Records

## Principios de Diseño

1. **Aritmética de dinero**: enteros en unidades menores (céntimos/fen), nunca floats
2. **Confianza del vendedor**: cálculo determinista y versionado, no juicio del LLM
3. **LLM Gateway**: solo endpoints compatibles con OpenAI, sin SDK propietarios
4. **Firmas Ed25519**: toda decisión firmada, verificable, encadenada
5. **Gate humano**: el sistema recomienda, el humano decide

## Licencia

Privado — Todos los derechos reservados
