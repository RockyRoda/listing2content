"""Generation and retrieval of a listing's content package.

A listing holds at most one package: generating again replaces the previous
draft and its slides/captions. The listing is only touched after both LLM
steps succeed, so a failed generation leaves the existing package intact.
"""

import logging
from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db, generation, storage
from .auth import get_current_user_id
from .listings import EDITABLE_FIELDS, owned_listing, photo_url

router = APIRouter(prefix="/listings", tags=["content-packages"])

log = logging.getLogger(__name__)


class Slide(BaseModel):
    id: int
    listing_photo_id: int | None
    order_index: int
    caption: str
    photo_url: str | None


class Caption(BaseModel):
    id: int
    label: str
    text: str


class Package(BaseModel):
    id: int
    listing_id: int
    status: str
    generated_at: str
    reel_script: str
    slides: list[Slide]
    captions: list[Caption]


def _load_package(conn, listing_id: int) -> Package | None:
    """Build a listing's package with its slides and captions, or None."""
    row = conn.execute(
        "SELECT * FROM content_packages WHERE listing_id = ?", (listing_id,)
    ).fetchone()
    if row is None:
        return None
    slides = conn.execute(
        "SELECT id, listing_photo_id, order_index, caption FROM carousel_slides"
        " WHERE content_package_id = ? ORDER BY order_index",
        (row["id"],),
    ).fetchall()
    captions = conn.execute(
        "SELECT id, label, text FROM captions WHERE content_package_id = ? ORDER BY id",
        (row["id"],),
    ).fetchall()
    return Package(
        id=row["id"],
        listing_id=listing_id,
        status=row["status"],
        generated_at=row["generated_at"],
        reel_script=row["reel_script"],
        slides=[
            Slide(
                **dict(s),
                photo_url=(
                    photo_url(listing_id, s["listing_photo_id"])
                    if s["listing_photo_id"]
                    else None
                ),
            )
            for s in slides
        ],
        captions=[Caption(**dict(c)) for c in captions],
    )


def _slide_photo_id(photo_number: int, photo_ids: list[int]) -> int | None:
    """Resolve a draft slide's 1-based photo_number to a listing_photos id."""
    if 1 <= photo_number <= len(photo_ids):
        return photo_ids[photo_number - 1]
    return None


def _replace_package(
    conn, listing_id: int, draft: generation.PackageDraft, photo_ids: list[int]
) -> None:
    """Drop the listing's previous package and write the new draft in its place."""
    old = conn.execute(
        "SELECT id FROM content_packages WHERE listing_id = ?", (listing_id,)
    ).fetchone()
    if old:
        conn.execute("DELETE FROM captions WHERE content_package_id = ?", (old["id"],))
        conn.execute(
            "DELETE FROM carousel_slides WHERE content_package_id = ?", (old["id"],)
        )
        conn.execute("DELETE FROM content_packages WHERE id = ?", (old["id"],))

    cur = conn.execute(
        "INSERT INTO content_packages (listing_id, reel_script) VALUES (?, ?)",
        (listing_id, draft.reel_script),
    )
    package_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO carousel_slides"
        " (content_package_id, listing_photo_id, order_index, caption)"
        " VALUES (?, ?, ?, ?)",
        [
            (package_id, _slide_photo_id(s.photo_number, photo_ids), i, s.caption)
            for i, s in enumerate(draft.carousel_slides)
        ],
    )
    conn.executemany(
        "INSERT INTO captions (content_package_id, label, text) VALUES (?, ?, ?)",
        [(package_id, c.label, c.text) for c in draft.captions],
    )


@router.post("/{listing_id}/package", response_model=Package)
def create_package(
    listing_id: int, user_id: int = Depends(get_current_user_id)
) -> Package:
    """Caption the listing's photos, assemble a draft package, and store it."""
    with closing(db.connect()) as conn:
        listing = owned_listing(conn, listing_id, user_id)
        photos = conn.execute(
            "SELECT id, filename, content_type FROM listing_photos"
            " WHERE listing_id = ? ORDER BY id LIMIT ?",
            (listing_id, generation.MAX_CAPTIONED_PHOTOS),
        ).fetchall()
        voice = conn.execute(
            "SELECT style_notes, tone_notes FROM voice_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not photos:
        raise HTTPException(
            status_code=400,
            detail="Add at least one photo before generating a content package",
        )

    try:
        draft = generation.generate_package(
            {field: listing[field] for field in EDITABLE_FIELDS},
            [(storage.photo_path(p["filename"]), p["content_type"]) for p in photos],
            voice["style_notes"] if voice else "",
            voice["tone_notes"] if voice else "",
        )
    except Exception:
        log.exception("Content generation failed for listing %s", listing_id)
        raise HTTPException(status_code=502, detail="Content generation failed")

    with closing(db.connect()) as conn:
        _replace_package(conn, listing_id, draft, [p["id"] for p in photos])
        conn.commit()
        return _load_package(conn, listing_id)


@router.get("/{listing_id}/package", response_model=Package)
def get_package(
    listing_id: int, user_id: int = Depends(get_current_user_id)
) -> Package:
    """Return the listing's current package, or 404 if none has been generated."""
    with closing(db.connect()) as conn:
        owned_listing(conn, listing_id, user_id)
        package = _load_package(conn, listing_id)
    if package is None:
        raise HTTPException(status_code=404, detail="No content package yet")
    return package
