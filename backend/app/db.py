"""SQLite access and schema.

The database is recreated from scratch on every startup, matching the
container's ephemeral filesystem (per docs/PLAN.md). Set L2C_DB_PATH to point
at a different file (used by tests).
"""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "listing2content.db"

SCHEMA = """
DROP TABLE IF EXISTS listing_photos;
DROP TABLE IF EXISTS listings;
DROP TABLE IF EXISTS voice_profiles;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    location TEXT,
    price INTEGER,
    beds INTEGER,
    baths REAL,
    interior_sqft INTEGER,
    lot_size TEXT,
    property_type TEXT,
    mls_number TEXT,
    features TEXT,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE listing_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    filename TEXT NOT NULL,
    original_name TEXT,
    content_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE voice_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    sample_text TEXT NOT NULL DEFAULT '',
    tone_notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def db_path() -> str:
    """Resolve the DB file path, honoring the L2C_DB_PATH override."""
    return os.environ.get("L2C_DB_PATH", str(DEFAULT_DB_PATH))


def connect() -> sqlite3.Connection:
    """Open a connection with row access by name and foreign keys enforced."""
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create a fresh schema, dropping any existing tables."""
    from contextlib import closing

    with closing(connect()) as conn:
        conn.executescript(SCHEMA)
