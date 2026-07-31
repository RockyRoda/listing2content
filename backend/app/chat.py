"""Conversational data entry and package editing, scoped to one listing.

One structured-output call per turn (generation.chat_turn) returns the reply
plus whatever it wants changed; this module writes it. The two jobs from
docs/PLAN.md Phase 6 are the two things it can write: listing fields, and the
copy in an already-generated package.

Package edits go through content_packages.apply_edits, so chat inherits the
Phase 5 rules rather than restating them - a row id from another package is
rejected, and any edit returns an approved package to draft.

Like generation, the prompt sees the agent's distilled style_notes and never
their raw writing samples (docs/VOICE-CONTAMINATION.md): chat rewrites listing
copy, so the same leak applies to it.
"""

import logging
from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db, generation
from .auth import get_current_user_id
from .content_packages import (
    CaptionEdit,
    PackageEdit,
    SlideEdit,
    apply_edits,
    load_package,
    require_package_id,
)
from .listings import owned_listing

router = APIRouter(prefix="/listings", tags=["chat"])

log = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ChatRequest(BaseModel):
    message: str


class ChatReply(BaseModel):
    """The transcript after the turn, and what the turn changed.

    The flags tell the page which of its own data to reload: the listing form
    on one page, the package editor on the other.
    """

    messages: list[ChatMessage]
    listing_changed: bool
    package_changed: bool


def _messages(conn, listing_id: int) -> list[ChatMessage]:
    """The listing's transcript, oldest first."""
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM chat_messages"
        " WHERE listing_id = ? ORDER BY id",
        (listing_id,),
    ).fetchall()
    return [ChatMessage(**dict(r)) for r in rows]


def _record(conn, listing_id: int, role: str, content: str) -> None:
    conn.execute(
        "INSERT INTO chat_messages (listing_id, role, content) VALUES (?, ?, ?)",
        (listing_id, role, content),
    )


def _apply_listing_updates(
    conn, listing_id: int, updates: generation.ListingPatch
) -> bool:
    """Write the fields the turn filled in. Returns whether anything changed."""
    changes = updates.model_dump(exclude_none=True)
    if not changes:
        return False
    assignments = ", ".join(f"{c} = ?" for c in changes)
    conn.execute(
        f"UPDATE listings SET {assignments}, updated_at = datetime('now')"
        " WHERE id = ?",
        (*changes.values(), listing_id),
    )
    return True


def _apply_package_edits(
    conn, listing_id: int, turn: generation.ChatTurn, current: dict
) -> bool:
    """Write the turn's copy rewrites. Returns whether anything changed.

    Skipped entirely when the turn rewrote nothing, so a chat about listing
    fields never knocks an approved package back to draft.
    """
    if not (turn.slide_edits or turn.caption_edits or turn.reel_script is not None):
        return False
    apply_edits(
        conn,
        require_package_id(conn, listing_id),
        PackageEdit(
            reel_script=(
                turn.reel_script
                if turn.reel_script is not None
                else current["reel_script"]
            ),
            slides=[SlideEdit(id=s.slide_id, caption=s.caption) for s in turn.slide_edits],
            captions=[CaptionEdit(id=c.caption_id, text=c.text) for c in turn.caption_edits],
        ),
    )
    return True


@router.get("/{listing_id}/chat", response_model=list[ChatMessage])
def get_chat(
    listing_id: int, user_id: int = Depends(get_current_user_id)
) -> list[ChatMessage]:
    """Return the listing's conversation so far."""
    with closing(db.connect()) as conn:
        owned_listing(conn, listing_id, user_id)
        return _messages(conn, listing_id)


@router.post("/{listing_id}/chat", response_model=ChatReply)
def post_chat(
    listing_id: int,
    body: ChatRequest,
    user_id: int = Depends(get_current_user_id),
) -> ChatReply:
    """Answer the agent's message and apply whatever it asked for."""
    with closing(db.connect()) as conn:
        listing = owned_listing(conn, listing_id, user_id)
        package = load_package(conn, listing_id)
        voice = conn.execute(
            "SELECT style_notes, tone_notes FROM voice_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        history = [
            {"role": m.role, "content": m.content} for m in _messages(conn, listing_id)
        ]

    current = package.model_dump() if package else None
    try:
        turn = generation.chat_turn(
            dict(listing),
            current,
            history,
            body.message,
            voice["style_notes"] if voice else "",
            voice["tone_notes"] if voice else "",
        )
    except Exception:
        log.exception("Chat turn failed for listing %s", listing_id)
        raise HTTPException(status_code=502, detail="The assistant did not respond")

    with closing(db.connect()) as conn:
        listing_changed = _apply_listing_updates(conn, listing_id, turn.listing_updates)
        package_changed = (
            _apply_package_edits(conn, listing_id, turn, current)
            if current is not None
            else False
        )
        _record(conn, listing_id, "user", body.message)
        _record(conn, listing_id, "assistant", turn.reply)
        conn.commit()
        return ChatReply(
            messages=_messages(conn, listing_id),
            listing_changed=listing_changed,
            package_changed=package_changed,
        )
