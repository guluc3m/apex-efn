# ADR-001: Monorepo Structure

## Status

Accepted

## Context

APEX-EFN is a hybrid application with:
- TypeScript frontend (Next.js) and browser automation (Puppeteer)
- Python backend (FastAPI, LangGraph) for agent orchestration
- Shared business logic (money, scoring) needed in both languages

We need a structure that:
1. Allows shared types between services
2. Supports independent deployment of services
3. Enables efficient CI/CD with caching
4. Keeps development environment simple

## Decision

Use a **pnpm workspaces + Turborepo** monorepo with the following structure:

```
/apps
  /web            Next.js (frontend + BFF)
  /orchestrator   FastAPI + LangGraph (Python)
  /browser-worker Node/TS + Puppeteer
/packages
  /shared-types   Zod schemas + Python pydantic (generated from OpenAPI)
  /money          Monetary arithmetic (TS, with test vectors for Python)
  /scoring        Seller confidence, MCDA (TS, with test vectors for Python)
  /crypto-client  Ed25519 signing (browser WebCrypto)
  /ui             Design system (shadcn/ui)
  /eslint-config, /tsconfig
/infra            Docker Compose, Helm, Terraform
/docs             ADRs, runbooks, compliance
```

- OpenAPI 3.1 is the **source of truth** for contracts between services
- Types are generated from OpenAPI, not duplicated
- Python packages use `pyproject.toml` and are not managed by pnpm
- Test vectors for money/scoring are shared via JSON fixtures

## Consequences

### Easier
- Single repo for all code, easy to navigate
- Shared types reduce drift between services
- Turborepo caching speeds up CI
- Easy to run everything locally with `docker compose up`

### Harder
- Developers need both Node.js and Python toolchains
- CI needs to handle both ecosystems
- OpenAPI schema must be kept in sync manually (or via generation)

## Related

- [Section 5.1 of PROMPT-IMPLEMENTACION.md](../../PROMPT-IMPLEMENTACION.md)
