"""FastAPI application entry point for Listing2Content."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db
from .auth import router as auth_router


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
