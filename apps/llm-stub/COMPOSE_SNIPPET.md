# Proposed compose wiring for llm-stub (platform-request for DEV-1)

DEV-4 does **not** edit `infra/docker-compose.yml` or write `apps/*/Dockerfile` (both are DEV-1).
This document is the proposal. Open a `platform-request` issue with this content.

## Dockerfile (`apps/llm-stub/Dockerfile`, DEV-1 to own)

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.5.11

FROM base AS deps
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM base AS runtime
RUN useradd --create-home --uid 10001 stub
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY src ./src
COPY scenarios ./scenarios
ENV PATH="/app/.venv/bin:$PATH" \
    LLM_STUB_SCENARIOS_DIR=/app/scenarios \
    LLM_STUB_HOST=0.0.0.0 \
    LLM_STUB_PORT=8001
USER stub
EXPOSE 8001
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health').status==200 else 1)"
CMD ["python", "-m", "llm_stub"]
```

Note: `uv sync --no-dev` needs the project itself installed (hatchling). If DEV-1 prefers, run
`uv sync --frozen --no-dev` after copying `src` (drop `--no-install-project` in the deps stage).

## Compose service (`infra/docker-compose.yml`, DEV-1 to own)

```yaml
services:
  llm-stub:
    build:
      context: ../apps/llm-stub
      dockerfile: Dockerfile
    image: apex/llm-stub:dev
    ports:
      - "8001:8001"
    environment:
      LLM_STUB_SCENARIOS_DIR: /app/scenarios
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health').status==200 else 1)"]
      interval: 5s
      timeout: 3s
      retries: 20
    restart: unless-stopped
```

Orchestrator / gateway config for local dev should point at
`LLM_BASE_URL=http://llm-stub:8001/v1` inside the compose network, or
`http://localhost:8001/v1` from the host. Scenario selection from the orchestrator is done with the
`X-Stub-Scenario` header.

If the compose file mounts scenarios from the host instead of baking them into the image, add:

```yaml
    volumes:
      - ../apps/llm-stub/scenarios:/app/scenarios:ro
```
