# syntax=docker/dockerfile:1
# OpenAI-compatible LLM stub (D4-02) built for compose/local dev (D1-03).
# Owner: DEV-1 (Dockerfiles). The Python project and scenarios belong to DEV-4.
#
# Two stages: a builder that resolves the locked environment with the pinned uv image, and a slim
# runtime that only carries the virtualenv plus src/ and scenarios/. No compiler, no build cache.

# uv is pinned on purpose (same version as UV_VERSION in .github/workflows/ci.yml). Copied from the
# official image instead of `pip install uv`, so the build has no dependency on PyPI being reachable.
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# Dependencies first (cached independently of the sources), then the project itself.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY scenarios ./scenarios
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    LLM_STUB_SCENARIOS_DIR=/app/scenarios \
    LLM_STUB_HOST=0.0.0.0 \
    LLM_STUB_PORT=8001

# Non-root, fixed UID/GID so a bind-mounted volume or a k8s runAsUser stays stable.
RUN groupadd --gid 10001 stub \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin stub

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/scenarios /app/scenarios

USER 10001:10001

EXPOSE 8001

# Python is the venv interpreter (PATH above), so no extra tooling is needed in the image.
# start-period covers the first import of FastAPI/pydantic on a cold CPU.
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=20 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2).status == 200 else 1)"]

CMD ["python", "-m", "llm_stub"]
