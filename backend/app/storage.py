"""Listing photo storage on the container filesystem.

Photos are ephemeral (lost on rebuild/restart, same lifecycle as the DB) and
stored with random UUID filenames. Override the directory with L2C_MEDIA_DIR.
"""

import os
import uuid
from pathlib import Path

DEFAULT_MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"

# content-type -> file extension allowlist for uploaded photos.
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTOS_PER_LISTING = 20


def media_dir() -> Path:
    """Resolve the media directory, honoring the L2C_MEDIA_DIR override."""
    return Path(os.environ.get("L2C_MEDIA_DIR", str(DEFAULT_MEDIA_DIR)))


def init_storage() -> None:
    """Ensure the media directory exists."""
    media_dir().mkdir(parents=True, exist_ok=True)


def save_photo(data: bytes, content_type: str) -> str:
    """Write photo bytes under a new UUID filename and return that filename."""
    filename = f"{uuid.uuid4().hex}{ALLOWED_IMAGE_TYPES[content_type]}"
    (media_dir() / filename).write_bytes(data)
    return filename


def photo_path(filename: str) -> Path:
    """Absolute path to a stored photo."""
    return media_dir() / filename


def delete_photo(filename: str) -> None:
    """Remove a stored photo if it still exists."""
    photo_path(filename).unlink(missing_ok=True)
