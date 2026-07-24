"""Shared test fixtures: a TestClient on a fresh temp DB + media dir."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient backed by a fresh temp DB and media dir (built on startup)."""
    monkeypatch.setenv("L2C_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("L2C_MEDIA_DIR", str(tmp_path / "media"))
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """Sign up a user and return an Authorization header for them."""
    token = client.post(
        "/api/auth/signup", json={"email": "agent@b.com", "password": "pw"}
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}
