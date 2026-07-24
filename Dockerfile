# Single-container build: FastAPI backend serves the built frontend.
# OPENROUTER_API_KEY is provided at run time via --env-file, never baked in.

# Stage 1: build the Next.js static export (frontend/out).
FROM node:lts-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: backend runtime, serving the static export from stage 1.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app/backend

# Install dependencies in a cached layer keyed on the lockfile.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# Application code.
COPY backend/app ./app

# Built frontend, served by FastAPI at the root (see app/main.py FRONTEND_DIR).
COPY --from=frontend /app/frontend/out /app/frontend/out

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
