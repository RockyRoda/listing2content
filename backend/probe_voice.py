"""Measure how the voice profile affects generated copy, and whether it leaks.

Two questions, one pass:
  1. Does the sample change the writing? (average sentence length per run)
  2. Do the sample's FACTS leak into the listing copy? The built-in sample
     advertises a different property, so any of its facts appearing is a
     false claim about the listing being marketed.

Holds the listing and photo captions fixed and varies only what is asked for,
so repeated runs measure the model's sampling rather than changed inputs.

Run: uv run python probe_voice.py --runs 12 --photos 1 --tone ""
"""

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.generation import assemble_package, describe_photo  # noqa: E402

LISTING = {
    "title": "Oceanfront Villa Kai",
    "location": "Wailea, Maui",
    "price": 8950000,
    "beds": 4,
    "baths": 4.5,
    "interior_sqft": 5200,
    "features": "Infinity pool, outdoor kitchen, private beach path",
}
PHOTOS = [
    (Path(r"C:\Windows\Web\Wallpaper\Spotlight\img14.jpg"), "image/jpeg"),
    (Path(r"C:\Windows\Web\Wallpaper\ThemeA\img20.jpg"), "image/jpeg"),
]

# Writing samples advertising a DIFFERENT property than the one generated for.
SAMPLES = {
    "none": "",
    "terse": (
        "Three beds. Two baths. Corner lot on Sycamore. Priced to move.\n"
        "Open Saturday, noon to three. Bring your agent. It will not last.\n"
        "Roof is new. Furnace is new. Basement is dry. Nothing left to do.\n"
        "Walk to the elementary school. Call me. I answer my phone."
    ),
    "lyrical": (
        "There is a particular quality to the light here in the late"
        " afternoon, when the water goes the colour of hammered brass and the"
        " whole day seems to slow to nothing at all.\n"
        "I have always thought a house should be measured not in square feet"
        " but in the number of mornings you would want to wake up inside it."
    ),
}

# Facts belonging to the sample's property, never to the listing above.
FOREIGN_FACTS = [
    r"corner lot", r"sycamore", r"furnace", r"basement", r"elementary",
    r"three bed", r"3 bed", r"two bath", r"2 bath", r"open saturday",
    r"roof is new", r"new roof", r"hammered brass",
]


def published_copy(draft) -> str:
    """Post captions plus slide captions - what the agent would publish."""
    return " ".join(
        [c.text for c in draft.captions] + [s.caption for s in draft.carousel_slides]
    )


def avg_sentence_words(text: str) -> float:
    parts = [p for p in re.split(r"[.!?]+", text) if p.strip()]
    return sum(len(p.split()) for p in parts) / max(len(parts), 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=12)
    parser.add_argument("--photos", type=int, default=2, choices=[1, 2])
    parser.add_argument("--sample", default="terse", choices=sorted(SAMPLES))
    parser.add_argument("--tone", default="", help="tone_notes, empty by default")
    parser.add_argument("--workers", type=int, default=3, help="lower this on rate limits")
    args = parser.parse_args()

    photos = PHOTOS[: args.photos]
    descriptions = [describe_photo(*photo) for photo in photos]
    print(
        f"sample={args.sample} photos={args.photos} tone={args.tone!r}"
        f" -> {args.runs} generations\n"
    )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        drafts = list(
            pool.map(
                lambda _: assemble_package(
                    LISTING, descriptions, SAMPLES[args.sample], args.tone
                ),
                range(args.runs),
            )
        )

    lengths, leaked_runs = [], 0
    for index, draft in enumerate(drafts, start=1):
        copy = published_copy(draft)
        lengths.append(avg_sentence_words(copy))
        whole = (copy + " " + draft.reel_script).lower()
        hits = [f for f in FOREIGN_FACTS if re.search(f, whole)]
        if hits:
            leaked_runs += 1
            print(f"  run {index}: LEAK {', '.join(hits)}")
            for line in re.split(r"(?<=[.!?])\s+", copy + " " + draft.reel_script):
                if any(re.search(f, line.lower()) for f in hits):
                    print(f"          {line.strip()[:110]}")
        else:
            print(f"  run {index}: clean  ({lengths[-1]:.1f} words/sentence)")

    print(f"\nmean sentence length: {sum(lengths) / len(lengths):.1f} words")
    print(f"foreign facts: {leaked_runs}/{args.runs} runs leaked")


if __name__ == "__main__":
    main()
