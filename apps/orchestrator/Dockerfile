# syntax=docker/dockerfile:1.10
# Build context: apps/orchestrator (see apps/orchestrator/.dockerignore).
# Built from the locked uv project; the wheel carries src/apex, so the runtime
# stage only needs the virtualenv.

FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

FROM python:3.12.12-slim-bookworm AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.12.12-slim-bookworm AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 apex \
 && useradd --system --uid 10001 --gid apex --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin apex
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["uvicorn", "apex.main:app", "--host", "0.0.0.0", "--port", "8000"]
