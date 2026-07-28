"""Measure how the voice profile affects generated copy, and whether it leaks.

Runs the full path the API uses: distil the sample with extract_style, then
generate from the descriptors alone. Both stages are checked for leaks.

Two questions, one pass:
  1. Does the sample change the writing? (average sentence length per run)
  2. Do the sample's FACTS leak into the listing copy? The built-in sample
     advertises a different property, so any of its facts appearing is a
     false claim about the listing being marketed.

By default this captions the photos once and reuses that caption, so repeated
runs measure the assembly step's sampling alone. That default hides leaks: the
API re-captions on every generation, and the leak only appears when the caption
varies (0/60 fixed against 2/36 fresh). Pass --fresh-captions to measure a real
leak rate; leave it off only to isolate the assembly step.

Run: uv run python probe_voice.py --runs 12 --tone "" --fresh-captions
"""

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.generation import (  # noqa: E402
    assemble_package,
    describe_photo,
    extract_style,
    generate_package,
)

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

# The voice check in scripts/verify-phase4.ps1 leaks where this probe does not.
# These three flags each reproduce one way its inputs differ, so the difference
# can be bisected. All three together are the smoke test's exact shape.
SMOKE_PHOTO = (Path(r"C:\Windows\Web\Wallpaper\ThemeA\img20.jpg"), "image/jpeg")

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


def probe_style(sample: str, runs: int, workers: int) -> None:
    """Extract style repeatedly and report descriptors carrying the sample's facts.

    Extraction is the only place the samples are read, so a clean result here
    means no foreign fact can reach generation at all.
    """
    print(f"extract_style only -> {runs} extractions\n")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        styles = list(pool.map(lambda _: extract_style(sample), range(runs)))

    leaked = 0
    for index, style in enumerate(styles, start=1):
        hits = [f for f in FOREIGN_FACTS if re.search(f, style.lower())]
        if hits:
            leaked += 1
            print(f"  run {index}: LEAK {', '.join(hits)}")
            for line in style.splitlines():
                if any(re.search(f, line.lower()) for f in hits):
                    print(f"          {line.strip()[:110]}")
        else:
            print(f"  run {index}: clean")
    print(f"\nstyle descriptors carrying facts: {leaked}/{runs}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=12)
    parser.add_argument("--photos", type=int, default=2, choices=[1, 2])
    parser.add_argument("--sample", default="terse", choices=sorted(SAMPLES))
    parser.add_argument("--tone", default="", help="tone_notes, empty by default")
    parser.add_argument("--workers", type=int, default=3, help="lower this on rate limits")
    parser.add_argument("--smoke-photo", action="store_true",
                        help="caption the photo the smoke test uses, not this probe's")
    parser.add_argument("--thin-listing", action="store_true",
                        help="drop interior_sqft, as the smoke test's listing does")
    parser.add_argument("--bom", action="store_true",
                        help="prefix a UTF-8 BOM and use CRLF, as the smoke test's upload does")
    parser.add_argument("--fresh-captions", action="store_true",
                        help="re-caption the photo every run, as the API does, instead"
                             " of captioning once and holding it fixed")
    parser.add_argument("--style-only", action="store_true",
                        help="only run extract_style, repeatedly, and check the"
                             " descriptors for the sample's facts")
    args = parser.parse_args()

    listing = dict(LISTING)
    if args.thin_listing:
        del listing["interior_sqft"]
    sample = SAMPLES[args.sample]
    if args.bom and sample:
        sample = "﻿" + sample.replace("\n", "\r\n")
    photos = [SMOKE_PHOTO] if args.smoke_photo else PHOTOS[: args.photos]

    if args.style_only:
        probe_style(sample, args.runs, args.workers)
        return

    # What the API stores at upload time and passes to every later generation.
    style_notes = extract_style(sample)
    if style_notes:
        print(f"extracted style:\n{style_notes}\n")
        leaked_style = [f for f in FOREIGN_FACTS if re.search(f, style_notes.lower())]
        if leaked_style:
            print(f"  STYLE CARRIES FACTS: {', '.join(leaked_style)}\n")

    print(
        f"sample={args.sample} photos={len(photos)} tone={args.tone!r}"
        f" smoke_photo={args.smoke_photo} thin_listing={args.thin_listing}"
        f" bom={args.bom} fresh_captions={args.fresh_captions}"
        f" -> {args.runs} generations\n"
    )

    if args.fresh_captions:
        def one_run(_):
            return generate_package(listing, photos, style_notes, args.tone)
    else:
        descriptions = [describe_photo(*photo) for photo in photos]

        def one_run(_):
            return assemble_package(listing, descriptions, style_notes, args.tone)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        drafts = list(pool.map(one_run, range(args.runs)))

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
