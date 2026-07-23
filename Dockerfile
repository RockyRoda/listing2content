# Single-container build: FastAPI backend (serves the built frontend in later
# phases). OPENROUTER_API_KEY is provided at run time via --env-file, never
# baked into the image.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app/backend

# Install dependencies in a cached layer keyed on the lockfile.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# Application code.
COPY backend/app ./app

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
