"""Auth flow tests: signup, signin, and bearer-token protection."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient backed by a fresh temp DB (schema built on startup)."""
    monkeypatch.setenv("L2C_DB_PATH", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_signup_returns_user_and_token(client):
    resp = client.post("/auth/signup", json={"email": "a@b.com", "password": "pw"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "a@b.com"
    assert body["user"]["id"] > 0
    assert body["token"]


def test_signup_duplicate_email_conflicts(client):
    client.post("/auth/signup", json={"email": "a@b.com", "password": "pw"})
    resp = client.post("/auth/signup", json={"email": "a@b.com", "password": "pw2"})
    assert resp.status_code == 409


def test_signup_rejects_invalid_email(client):
    resp = client.post("/auth/signup", json={"email": "not-an-email", "password": "pw"})
    assert resp.status_code == 422


def test_signin_success_returns_token(client):
    client.post("/auth/signup", json={"email": "a@b.com", "password": "pw"})
    resp = client.post("/auth/signin", json={"email": "a@b.com", "password": "pw"})
    assert resp.status_code == 200
    assert resp.json()["token"]


def test_signin_wrong_password_unauthorized(client):
    client.post("/auth/signup", json={"email": "a@b.com", "password": "pw"})
    resp = client.post("/auth/signin", json={"email": "a@b.com", "password": "nope"})
    assert resp.status_code == 401


def test_signin_unknown_email_unauthorized(client):
    resp = client.post("/auth/signin", json={"email": "ghost@b.com", "password": "pw"})
    assert resp.status_code == 401


def test_me_with_valid_token(client):
    token = client.post(
        "/auth/signup", json={"email": "a@b.com", "password": "pw"}
    ).json()["token"]
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "a@b.com"


def test_me_missing_token_unauthorized(client):
    assert client.get("/auth/me").status_code == 401


def test_me_bad_token_unauthorized(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401
