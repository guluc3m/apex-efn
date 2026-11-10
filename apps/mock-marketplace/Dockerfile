# syntax=docker/dockerfile:1
# @apex/mock-marketplace (D5-04) built for compose/local dev (D1-03).
# Owner: DEV-1 (Dockerfiles). The app and its fixtures belong to DEV-5.
#
# The build context is the REPO ROOT, because the app extends the workspace
# tsconfig (@apex/tsconfig) and is built with the workspace toolchain:
#   docker build -f apps/mock-marketplace/Dockerfile -t apex/mock-marketplace:dev .
#
# Two stages: a builder that installs the locked workspace deps and compiles with
# tsc, and a slim runtime that only carries the production deployment (pnpm deploy
# output: package.json, dist/, fixtures/ and prod node_modules). No pnpm, no
# TypeScript, no sources.

FROM node:22.20.0-bookworm-slim AS builder

# pnpm comes from Corepack, pinned to the root packageManager version (9.15.0).
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

# Workspace manifests first: the dependency layer is cached independently of the
# sources. Only the projects this image needs are present in the workspace.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/tsconfig/package.json ./packages/tsconfig/package.json
COPY packages/eslint-config/package.json ./packages/eslint-config/package.json
COPY apps/mock-marketplace/package.json ./apps/mock-marketplace/package.json

# --ignore-scripts skips the root postinstall (it builds every packages/*), which
# this app does not need; the only native-free deps are fastify and zod.
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --ignore-scripts --filter @apex/mock-marketplace...

COPY packages/tsconfig ./packages/tsconfig
COPY packages/eslint-config ./packages/eslint-config
COPY apps/mock-marketplace ./apps/mock-marketplace

# tsc emits dist/. `pnpm deploy --prod` then produces a portable directory whose
# node_modules only has fastify and zod (no workspace links, no dev deps).
RUN pnpm --filter @apex/mock-marketplace build \
    && pnpm --filter @apex/mock-marketplace deploy --prod --ignore-scripts /out

FROM node:22.20.0-bookworm-slim AS runtime

ENV NODE_ENV=production \
    PORT=8002 \
    HOST=0.0.0.0 \
    MOCK_MARKETPLACE_SEED=0

# Non-root, fixed UID/GID so a bind mount or a k8s runAsUser stays stable.
RUN groupadd --gid 10001 marketplace \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin marketplace

WORKDIR /app

COPY --from=builder --chown=10001:10001 /out/package.json ./package.json
COPY --from=builder --chown=10001:10001 /out/node_modules ./node_modules
COPY --from=builder --chown=10001:10001 /out/dist ./dist
# src/fixtures/load.ts resolves ../../fixtures/ relative to dist/fixtures/, so the
# catalog must sit next to dist/ in the runtime image.
COPY --from=builder --chown=10001:10001 /out/fixtures ./fixtures

USER 10001:10001

EXPOSE 8002

# Node 22 ships fetch; no curl/wget in the slim image.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:8002/healthz').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]

CMD ["node", "dist/index.js"]
