"""Signup, signin, and bearer-token authentication.

Tokens are opaque (secrets.token_urlsafe) and stored in the sessions table.
There is no expiry or logout for v1 - tokens die when the DB is recreated on
the next startup.
"""

import secrets
import sqlite3
from contextlib import closing

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr

from . import db

router = APIRouter(prefix="/auth", tags=["auth"])
ph = PasswordHasher()


class Credentials(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    id: int
    email: str


class AuthResponse(BaseModel):
    user: User
    token: str


def _issue_token(user_id: int) -> str:
    """Create and persist a new opaque session token for a user."""
    token = secrets.token_urlsafe(32)
    with closing(db.connect()) as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id)
        )
        conn.commit()
    return token


@router.post("/signup", response_model=AuthResponse)
def signup(creds: Credentials) -> AuthResponse:
    """Register a new user and return the user with a fresh session token."""
    hashed = ph.hash(creds.password)
    with closing(db.connect()) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
                (creds.email, hashed),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Email already registered")
        user_id = cur.lastrowid
    token = _issue_token(user_id)
    return AuthResponse(user=User(id=user_id, email=creds.email), token=token)


@router.post("/signin", response_model=AuthResponse)
def signin(creds: Credentials) -> AuthResponse:
    """Verify credentials and return the user with a fresh session token."""
    with closing(db.connect()) as conn:
        row = conn.execute(
            "SELECT id, hashed_password FROM users WHERE email = ?", (creds.email,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    try:
        ph.verify(row["hashed_password"], creds.password)
    except VerifyMismatchError:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = _issue_token(row["id"])
    return AuthResponse(user=User(id=row["id"], email=creds.email), token=token)


def get_current_user_id(authorization: str = Header(default="")) -> int:
    """Resolve the user id from an Authorization: Bearer <token> header."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    with closing(db.connect()) as conn:
        row = conn.execute(
            "SELECT user_id FROM sessions WHERE token = ?", (token,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return row["user_id"]


@router.get("/me", response_model=User)
def me(user_id: int = Depends(get_current_user_id)) -> User:
    """Return the currently authenticated user (a protected endpoint)."""
    with closing(db.connect()) as conn:
        row = conn.execute(
            "SELECT id, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return User(id=row["id"], email=row["email"])
