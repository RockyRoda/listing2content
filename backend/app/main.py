"""FastAPI application entry point for Listing2Content."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db, storage
from .auth import router as auth_router
from .chat import router as chat_router
from .content_packages import router as packages_router
from .listings import router as listings_router
from .voice_profiles import router as voice_router

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Pick up OPENROUTER_API_KEY for local runs. In Docker the repo .env is never
# copied in, so this is a no-op and the key arrives via docker run --env-file.
load_dotenv(REPO_ROOT / ".env")

# The built frontend (Next.js static export). Override with L2C_FRONTEND_DIR;
# defaults to <repo>/frontend/out for local runs and /app/frontend/out in Docker.
FRONTEND_DIR = Path(
    os.environ.get("L2C_FRONTEND_DIR", REPO_ROOT / "frontend" / "out")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Recreate the database schema and media directory on startup."""
    db.init_db()
    storage.init_storage()
    yield


# API routes live under /api so they never collide with the frontend's own
# routes (the SPA owns paths like /listings and /settings at the root).
app = FastAPI(title="Listing2Content", lifespan=lifespan)
app.include_router(auth_router, prefix="/api")
app.include_router(listings_router, prefix="/api")
app.include_router(packages_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(voice_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by scripts and the container healthcheck."""
    return {"status": "ok"}


# Serve the built frontend at the root when it is present. Mounted last so the
# API routes above take precedence; html=True serves each route's index.html.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
