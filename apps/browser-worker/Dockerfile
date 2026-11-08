# syntax=docker/dockerfile:1.10
# Build context: repository root (pnpm workspace). Ignore rules are in /.dockerignore.
#   docker build -f apps/browser-worker/Dockerfile -t trato-browser-worker .
#
# Chromium comes from Debian (not from the Puppeteer download), so the image
# does not depend on a Chrome build fetched at install time. PUPPETEER_EXECUTABLE_PATH
# points at it. Playwright is installed as a package but no browsers are shipped.

FROM node:22.20.0-bookworm-slim AS base
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    HUSKY=0 \
    PUPPETEER_SKIP_DOWNLOAD=true \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate \
 && pnpm config set store-dir /pnpm/store
WORKDIR /app

FROM base AS fetch
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
RUN --mount=type=cache,id=trato-pnpm-store,target=/pnpm/store \
    pnpm fetch

FROM fetch AS builder
COPY . .
RUN --mount=type=cache,id=trato-pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --offline
RUN pnpm --filter @trato/browser-worker build
RUN pnpm deploy --filter @trato/browser-worker --prod /out \
 && mkdir -p /out/dist && cp -r apps/browser-worker/dist/. /out/dist/

FROM node:22.20.0-bookworm-slim AS runtime
# tini reaps Chromium child processes (PID 1 would otherwise inherit zombies).
# Debian packages are not version-pinned: bookworm security updates must reach the
# browser. The image is rebuilt on every merge to main.
# hadolint ignore=DL3008
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      chromium \
      fonts-liberation \
      ca-certificates \
      tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 trato \
 && useradd --system --uid 10001 --gid trato --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin trato

ENV NODE_ENV=production \
    PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    HOME=/tmp
WORKDIR /app
COPY --from=builder /out ./
USER 10001:10001

# No HEALTHCHECK yet: the worker exposes no HTTP endpoint until the internal API
# lands (D5-01). Liveness is handled by the orchestrator's queue monitoring.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "dist/index.js"]
