# syntax=docker/dockerfile:1.10
# Build context: repository root (pnpm workspace). Ignore rules are in /.dockerignore.
#   docker build -f apps/web/Dockerfile -t trato-web .
#
# next.config.ts has no `output: 'standalone'`, so the runtime keeps the pruned
# production node_modules from `pnpm deploy` and runs `next start`.

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
RUN --mount=type=cache,id=trato-pnpm-store,target=/pnpm/store \
    pnpm fetch

FROM fetch AS builder
COPY . .
# The root postinstall builds the workspace packages (turbo) and apps/web's postinstall
# runs `prisma generate`, so the sources and prisma/schema.prisma must be present here.
RUN --mount=type=cache,id=trato-pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --offline
RUN pnpm --filter @trato/web build
# Pruned runtime: production dependencies only, plus the Next.js build output.
RUN pnpm deploy --filter @trato/web --prod /out \
 && mkdir -p /out/.next && cp -r apps/web/.next/. /out/.next/

FROM node:22.20.0-bookworm-slim AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN groupadd --system --gid 10001 trato \
 && useradd --system --uid 10001 --gid trato --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin trato
WORKDIR /app
COPY --from=builder /out ./
USER 10001:10001
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then((r) => process.exit(r.status < 500 ? 0 : 1)).catch(() => process.exit(1))"]

CMD ["./node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
