"""FastAPI application entry point for Listing2Content."""

from fastapi import FastAPI

app = FastAPI(title="Listing2Content")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by scripts and the container healthcheck."""
    return {"status": "ok"}
