"""Manual live check of the Phase 4 generation pipeline.

Runs the real two-step path - vision captioning per photo over OpenRouter,
then structured package assembly on Cerebras - against a sample listing and
the photos given on the command line. The unit tests monkeypatch both calls,
so this script is what proves the live path still works.

Run: uv run python spike_generation.py path/to/photo.jpg [more.jpg ...]
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.generation import PackageDraft, generate_package  # noqa: E402

LISTING = {
    "title": "Oceanfront Villa Kai",
    "location": "Wailea, Maui",
    "price": 8950000,
    "beds": 4,
    "baths": 4.5,
    "interior_sqft": 5200,
    "features": "Infinity pool, outdoor kitchen, private beach path",
}
TONE_NOTES = "Warm, unhurried, a little wry."
CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def run(paths: list[Path]) -> PackageDraft:
    photos = [(path, CONTENT_TYPES[path.suffix.lower()]) for path in paths]
    return generate_package(LISTING, photos, "", TONE_NOTES)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: uv run python spike_generation.py photo.jpg [more.jpg ...]")

    draft = run([Path(arg) for arg in sys.argv[1:]])
    for index, slide in enumerate(draft.carousel_slides, start=1):
        print(f"Slide {index} (photo {slide.photo_number}): {slide.caption}")
    for caption in draft.captions:
        print(f"\n[{caption.label}] {caption.text}")
    print(f"\nReel script:\n{draft.reel_script}")
