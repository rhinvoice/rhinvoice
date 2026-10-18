# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

# --- Frontend build -----------------------------------------------------------
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS frontend
WORKDIR /build/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

# --- Python dependencies --------------------------------------------------------
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS backend
COPY --from=ghcr.io/astral-sh/uv:0.10@sha256:72ab0aeb448090480ccabb99fb5f52b0dc3c71923bffb5e2e26517a1c27b7fec /uv /usr/local/bin/uv
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
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS runtime
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
