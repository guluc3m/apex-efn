# APEX-EFN (Apex Platform Enterprise Xchange - Element Fintech Network)
<img width="635" height="234" alt="image" src="https://github.com/user-attachments/assets/bd27c208-3a83-4609-abc6-8b46dd22e1b8" />

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

# Levantar servicios (Postgres, Redis, MinIO, Keycloak, Langfuse, LLM stub)
cd infra && docker compose up -d

# Ejecutar migraciones
pnpm db:migrate

# Desarrollo
pnpm dev
```

## Stack

| Componente | Tecnología |
|------------|------------|
| Frontend | Next.js 15, React 19, TanStack Query, Tailwind CSS |
| BFF | Next.js API Routes |
| Orquestador | FastAPI, LangGraph, Celery |
| Scraping | Puppeteer, Playwright, BullMQ |
| Base de datos | PostgreSQL 16, Prisma + SQLAlchemy |
| Caché/Colas | Redis |
| Almacenamiento | S3-compatible (MinIO/R2) |
| Auth | Keycloak (OIDC) |
| LLM | Compatible OpenAI (`/v1/chat/completions`) |
| Observabilidad | OpenTelemetry, Langfuse, Grafana |

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
