"""FastAPI application entry point for Listing2Content."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .auth import router as auth_router

# The built frontend (Next.js static export). Override with L2C_FRONTEND_DIR;
# defaults to <repo>/frontend/out for local runs and /app/frontend/out in Docker.
FRONTEND_DIR = Path(
    os.environ.get(
        "L2C_FRONTEND_DIR",
        Path(__file__).resolve().parent.parent.parent / "frontend" / "out",
    )
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Recreate the database schema on startup."""
    db.init_db()
    yield


app = FastAPI(title="Listing2Content", lifespan=lifespan)
app.include_router(auth_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by scripts and the container healthcheck."""
    return {"status": "ok"}


# Serve the built frontend at the root when it is present. Mounted last so the
# API routes above take precedence; html=True serves each route's index.html.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
