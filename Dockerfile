# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — build the React/Vite SPA into static assets.
# ---------------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend

# Install deps against the lockfile first for better layer caching.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build   # → /app/frontend/dist

# ---------------------------------------------------------------------------
# Stage 2 — Python backend (FastAPI + uv) that also serves the built SPA.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# ffmpeg is required for clip concat + master-audio muxing (Task 12).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv for dependency management (never bare pip — see CODE_STANDARDS.md).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app/backend

# Resolve dependencies from the lockfile first (cached until the lock changes).
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# App source, then install the project itself.
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Drop the built SPA where FastAPI mounts it (see main.py::_STATIC_DIR).
COPY --from=frontend /app/frontend/dist ./src/omnichain/static

EXPOSE 8080
# `sh -c` so Cloud Run's injected $PORT is expanded (JSON form for clean signals).
CMD ["sh", "-c", "uv run uvicorn omnichain.main:app --host 0.0.0.0 --port ${PORT}"]
