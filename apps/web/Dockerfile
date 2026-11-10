# syntax=docker/dockerfile:1.10
# Build context: repository root (pnpm workspace). Ignore rules are in /.dockerignore.
#   docker build -f apps/web/Dockerfile -t apex/web:dev .
#
# Standalone output (output: 'standalone' in apps/web/next.config.ts): the runtime runs
# `node apps/web/server.js` from `.next/standalone`, which carries the traced production
# node_modules. `next start` is never used, so the image does not need pnpm, TypeScript
# (a devDependency) or the full workspace at runtime, and next.config.ts is not re-loaded.

FROM node:22.20.0-bookworm-slim AS base
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    HUSKY=0 \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate \
 && pnpm config set store-dir /pnpm/store
WORKDIR /app

# Lockfile-only layer: downloads the locked packages into the BuildKit store cache.
FROM base AS fetch
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
RUN --mount=type=cache,id=apex-pnpm-store,target=/pnpm/store \
    pnpm fetch

FROM fetch AS builder
COPY . .
# The root postinstall builds the workspace packages (turbo) and apps/web's postinstall
# runs `prisma generate`, so the sources and prisma/schema.prisma must be present here.
RUN --mount=type=cache,id=apex-pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --offline
RUN pnpm --filter @apex/web build

# ---------------------------------------------------------------------------
# Migration image (D1-03, issue #221): Prisma CLI, the migrations, the seed and the psql client
# on top of the full workspace. Used only by the Helm pre-upgrade Job (templates/migrations.yaml),
# never by the app runtime.
#   docker build -f apps/web/Dockerfile --target migrator -t apex/web-migrations:dev .
# The Job runs `prisma migrate deploy`, then the optional seed, then
# infra/postgres/bootstrap-app-role.sh, all as the schema owner (migrateDatabaseUrl).
# ---------------------------------------------------------------------------
FROM builder AS migrator
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client \
 && rm -rf /var/lib/apt/lists/*
COPY infra/postgres/bootstrap-app-role.sh /usr/local/bin/bootstrap-app-role.sh
RUN chmod 0755 /usr/local/bin/bootstrap-app-role.sh
# The pod runs with a read-only root filesystem and an emptyDir at /tmp, so HOME must live there.
ENV HOME=/tmp
WORKDIR /app/apps/web
USER 10001:10001
CMD ["sh", "-c", "pnpm exec prisma migrate deploy"]

# ---------------------------------------------------------------------------
# Application runtime (standalone Next.js server).
# ---------------------------------------------------------------------------
FROM node:22.20.0-bookworm-slim AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN groupadd --system --gid 10001 apex \
 && useradd --system --uid 10001 --gid apex --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin apex
WORKDIR /app

# Next.js 15 places the standalone server entry at .next/standalone/apps/web/server.js in a
# monorepo; the standalone directory already contains the traced node_modules. The static
# assets and public files are never copied into standalone, so copy them to the paths
# server.js resolves (apps/web/.next/static and apps/web/public).
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/public ./apps/web/public

USER 10001:10001
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/es/acceso').then((r) => process.exit(r.status < 500 ? 0 : 1)).catch(() => process.exit(1))"]

CMD ["node", "apps/web/server.js"]
