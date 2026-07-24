"""Voice profile: one reusable profile per user.

The agent uploads .txt writing samples; the server concatenates them into
sample_text (replacing what was there). An optional tone_notes field lets the
agent add short style guidance. Both feed Phase 4 content generation.
"""

from contextlib import closing

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import db
from .auth import get_current_user_id

router = APIRouter(prefix="/voice-profile", tags=["voice-profile"])

MAX_VOICE_BYTES = 1024 * 1024


class VoiceProfile(BaseModel):
    sample_text: str
    tone_notes: str
    updated_at: str | None


@router.get("", response_model=VoiceProfile)
def get_voice_profile(
    user_id: int = Depends(get_current_user_id),
) -> VoiceProfile:
    """Return the current user's voice profile, or empty defaults if unset."""
    with closing(db.connect()) as conn:
        row = conn.execute(
            "SELECT sample_text, tone_notes, updated_at FROM voice_profiles"
            " WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return VoiceProfile(sample_text="", tone_notes="", updated_at=None)
    return VoiceProfile(**dict(row))


@router.put("", response_model=VoiceProfile)
async def put_voice_profile(
    files: list[UploadFile] = File(default=[]),
    tone_notes: str | None = Form(default=None),
    user_id: int = Depends(get_current_user_id),
) -> VoiceProfile:
    """Replace sample_text from uploaded .txt files and/or set tone_notes."""
    sample_text: str | None = None
    if files:
        parts: list[str] = []
        total = 0
        for file in files:
            is_text = file.content_type == "text/plain" or (
                file.filename or ""
            ).lower().endswith(".txt")
            if not is_text:
                raise HTTPException(
                    status_code=415, detail="Voice samples must be .txt files"
                )
            data = await file.read()
            total += len(data)
            if total > MAX_VOICE_BYTES:
                raise HTTPException(
                    status_code=413, detail="Voice samples must total 1 MB or less"
                )
            parts.append(data.decode("utf-8", errors="ignore").strip())
        sample_text = "\n\n".join(p for p in parts if p)

    with closing(db.connect()) as conn:
        existing = conn.execute(
            "SELECT sample_text, tone_notes FROM voice_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        new_sample = sample_text if sample_text is not None else (
            existing["sample_text"] if existing else ""
        )
        new_notes = tone_notes if tone_notes is not None else (
            existing["tone_notes"] if existing else ""
        )
        conn.execute(
            "INSERT INTO voice_profiles (user_id, sample_text, tone_notes, updated_at)"
            " VALUES (?, ?, ?, datetime('now'))"
            " ON CONFLICT(user_id) DO UPDATE SET"
            " sample_text = excluded.sample_text,"
            " tone_notes = excluded.tone_notes,"
            " updated_at = datetime('now')",
            (user_id, new_sample, new_notes),
        )
        conn.commit()
        row = conn.execute(
            "SELECT sample_text, tone_notes, updated_at FROM voice_profiles"
            " WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return VoiceProfile(**dict(row))
