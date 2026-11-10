# syntax=docker/dockerfile:1.10
# Build context: apps/ (see apps/.dockerignore).
#
# The llm-stub sibling must be present in the context: pyproject.toml declares it as a
# path source in [tool.uv.sources]. It is a dev-only dependency, so uv resolves its
# metadata to validate the lockfile but does not install it (`--no-dev`).
#
# The wheel carries src/apex (hatchling packages only src/apex), so the runtime stage
# only needs the virtualenv plus the data files the code resolves relative to the
# installed package (prompts/, see the runtime stage below).

FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

FROM python:3.12.12-slim-bookworm AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build

# The project and its llm-stub sibling (path source in [tool.uv.sources]).
COPY orchestrator/pyproject.toml orchestrator/uv.lock ./orchestrator/
COPY llm-stub/pyproject.toml ./llm-stub/
COPY llm-stub/src ./llm-stub/src
RUN --mount=type=cache,target=/root/.cache/uv \
    sh -c 'cd orchestrator && uv sync --locked --no-dev --no-install-project'

COPY orchestrator/src ./orchestrator/src
RUN --mount=type=cache,target=/root/.cache/uv \
    sh -c 'cd orchestrator && uv sync --locked --no-dev --no-editable'

FROM python:3.12.12-slim-bookworm AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 apex \
 && useradd --system --uid 10001 --gid apex --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin apex
COPY --from=builder /opt/venv /opt/venv

# Prompts. apex/llm/prompts.py resolves PROMPTS_DIR = parents[3] of the installed
# apex.llm.prompts module, which is /opt/venv/lib/python3.12 in a 3.12 wheel install.
# The wheel does not carry prompts/ (hatchling packages only src/apex), so copy them
# here in the runtime stage. If the base image's Python version changes, update this path.
COPY orchestrator/prompts /opt/venv/lib/python3.12/prompts

WORKDIR /app
USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["uvicorn", "apex.main:app", "--host", "0.0.0.0", "--port", "8000"]
