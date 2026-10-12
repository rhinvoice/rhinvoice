# syntax=docker/dockerfile:1.7

# --- Frontend build -----------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

# --- Python dependencies --------------------------------------------------------
FROM python:3.13-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build/backend
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

# --- Runtime --------------------------------------------------------------------
FROM python:3.13-slim AS runtime
LABEL org.opencontainers.image.title="Rhinvoice" \
      org.opencontainers.image.description="Self-hosted invoicing for CH, LI, DE and AT" \
      org.opencontainers.image.source="https://github.com/rhinvoice/rhinvoice"
RUN groupadd --system --gid 10001 rhinvoice \
    && useradd --system --uid 10001 --gid rhinvoice --home-dir /app --shell /usr/sbin/nologin rhinvoice
COPY --from=backend /opt/venv /opt/venv
COPY --from=frontend /build/frontend/dist /app/static
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RHINVOICE_STATIC_DIR=/app/static
WORKDIR /app
USER rhinvoice:rhinvoice
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]
CMD ["rhinvoice", "serve"]
