"""Listing CRUD and photo upload/serving.

All routes are owner-scoped: a listing (and its photos) is only visible to the
user who created it. Photos are validated (type/size/count) and served back
through an owner-checked endpoint rather than a public URL.
"""

from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import db, storage
from .auth import get_current_user_id

router = APIRouter(prefix="/listings", tags=["listings"])

# Columns a client may set on create/update, in one place so both share it.
EDITABLE_FIELDS = [
    "title",
    "location",
    "price",
    "beds",
    "baths",
    "interior_sqft",
    "lot_size",
    "property_type",
    "mls_number",
    "features",
    "description",
]


class ListingCreate(BaseModel):
    title: str
    location: str | None = None
    price: int | None = None
    beds: int | None = None
    baths: float | None = None
    interior_sqft: int | None = None
    lot_size: str | None = None
    property_type: str | None = None
    mls_number: str | None = None
    features: str | None = None
    description: str | None = None


class ListingUpdate(BaseModel):
    title: str | None = None
    location: str | None = None
    price: int | None = None
    beds: int | None = None
    baths: float | None = None
    interior_sqft: int | None = None
    lot_size: str | None = None
    property_type: str | None = None
    mls_number: str | None = None
    features: str | None = None
    description: str | None = None


class Photo(BaseModel):
    id: int
    original_name: str | None
    content_type: str
    url: str


class Listing(ListingCreate):
    id: int
    created_at: str
    updated_at: str
    photos: list[Photo]


class ListingSummary(BaseModel):
    id: int
    title: str
    location: str | None
    price: int | None
    photo_count: int
    created_at: str


def photo_url(listing_id: int, photo_id: int) -> str:
    return f"/listings/{listing_id}/photos/{photo_id}"


def owned_listing(conn, listing_id: int, user_id: int):
    """Return the listing row or 404 if it is missing or not owned by user."""
    row = conn.execute(
        "SELECT * FROM listings WHERE id = ? AND user_id = ?", (listing_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return row


def _load_listing(conn, row) -> Listing:
    """Build a Listing (with its photos) from a listings row."""
    photos = conn.execute(
        "SELECT id, original_name, content_type FROM listing_photos"
        " WHERE listing_id = ? ORDER BY id",
        (row["id"],),
    ).fetchall()
    return Listing(
        **{f: row[f] for f in EDITABLE_FIELDS},
        id=row["id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        photos=[
            Photo(
                id=p["id"],
                original_name=p["original_name"],
                content_type=p["content_type"],
                url=photo_url(row["id"], p["id"]),
            )
            for p in photos
        ],
    )


@router.post("", response_model=Listing)
def create_listing(
    body: ListingCreate, user_id: int = Depends(get_current_user_id)
) -> Listing:
    """Create a listing owned by the current user."""
    fields = body.model_dump()
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    with closing(db.connect()) as conn:
        cur = conn.execute(
            f"INSERT INTO listings (user_id, {columns}) VALUES (?, {placeholders})",
            (user_id, *fields.values()),
        )
        conn.commit()
        row = owned_listing(conn, cur.lastrowid, user_id)
        return _load_listing(conn, row)


@router.get("", response_model=list[ListingSummary])
def list_listings(user_id: int = Depends(get_current_user_id)) -> list[ListingSummary]:
    """List the current user's listings, newest first."""
    with closing(db.connect()) as conn:
        rows = conn.execute(
            "SELECT l.id, l.title, l.location, l.price, l.created_at,"
            " (SELECT COUNT(*) FROM listing_photos p WHERE p.listing_id = l.id)"
            " AS photo_count"
            " FROM listings l WHERE l.user_id = ? ORDER BY l.id DESC",
            (user_id,),
        ).fetchall()
    return [ListingSummary(**dict(r)) for r in rows]


@router.get("/{listing_id}", response_model=Listing)
def get_listing(
    listing_id: int, user_id: int = Depends(get_current_user_id)
) -> Listing:
    """Fetch one listing with its photos."""
    with closing(db.connect()) as conn:
        row = owned_listing(conn, listing_id, user_id)
        return _load_listing(conn, row)


@router.put("/{listing_id}", response_model=Listing)
def update_listing(
    listing_id: int,
    body: ListingUpdate,
    user_id: int = Depends(get_current_user_id),
) -> Listing:
    """Update the provided fields on a listing (owner only)."""
    changes = body.model_dump(exclude_unset=True)
    with closing(db.connect()) as conn:
        owned_listing(conn, listing_id, user_id)
        if changes:
            assignments = ", ".join(f"{c} = ?" for c in changes)
            conn.execute(
                f"UPDATE listings SET {assignments}, updated_at = datetime('now')"
                " WHERE id = ?",
                (*changes.values(), listing_id),
            )
            conn.commit()
        row = owned_listing(conn, listing_id, user_id)
        return _load_listing(conn, row)


@router.post("/{listing_id}/photos", response_model=Listing)
async def upload_photos(
    listing_id: int,
    files: list[UploadFile],
    user_id: int = Depends(get_current_user_id),
) -> Listing:
    """Upload one or more photos to a listing after validating type/size/count."""
    with closing(db.connect()) as conn:
        owned_listing(conn, listing_id, user_id)
        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM listing_photos WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()["n"]

    if existing + len(files) > storage.MAX_PHOTOS_PER_LISTING:
        raise HTTPException(
            status_code=400,
            detail=f"A listing can hold at most {storage.MAX_PHOTOS_PER_LISTING} photos",
        )

    # Validate the whole batch before saving anything.
    validated: list[tuple[bytes, str, str | None]] = []
    for file in files:
        if file.content_type not in storage.ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=415, detail="Photos must be JPEG, PNG, or WebP"
            )
        data = await file.read()
        if len(data) > storage.MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="Each photo must be 5 MB or less")
        validated.append((data, file.content_type, file.filename))

    with closing(db.connect()) as conn:
        for data, content_type, original_name in validated:
            filename = storage.save_photo(data, content_type)
            conn.execute(
                "INSERT INTO listing_photos"
                " (listing_id, filename, original_name, content_type)"
                " VALUES (?, ?, ?, ?)",
                (listing_id, filename, original_name, content_type),
            )
        conn.commit()
        row = owned_listing(conn, listing_id, user_id)
        return _load_listing(conn, row)


@router.get("/{listing_id}/photos/{photo_id}")
def get_photo(
    listing_id: int,
    photo_id: int,
    user_id: int = Depends(get_current_user_id),
) -> FileResponse:
    """Stream a photo's bytes to its owner."""
    with closing(db.connect()) as conn:
        owned_listing(conn, listing_id, user_id)
        row = conn.execute(
            "SELECT filename, content_type FROM listing_photos"
            " WHERE id = ? AND listing_id = ?",
            (photo_id, listing_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(storage.photo_path(row["filename"]), media_type=row["content_type"])


@router.delete("/{listing_id}/photos/{photo_id}", response_model=Listing)
def delete_photo(
    listing_id: int,
    photo_id: int,
    user_id: int = Depends(get_current_user_id),
) -> Listing:
    """Remove a photo from a listing (owner only)."""
    with closing(db.connect()) as conn:
        owned_listing(conn, listing_id, user_id)
        row = conn.execute(
            "SELECT filename FROM listing_photos WHERE id = ? AND listing_id = ?",
            (photo_id, listing_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        conn.execute("DELETE FROM listing_photos WHERE id = ?", (photo_id,))
        conn.commit()
        storage.delete_photo(row["filename"])
        listing = owned_listing(conn, listing_id, user_id)
        return _load_listing(conn, listing)
