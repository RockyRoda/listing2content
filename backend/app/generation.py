"""Two-step AI content generation for a listing.

Step 1 captions each photo with a vision-capable model over plain OpenRouter.
Step 2 feeds those captions, the listing specs, and the agent's voice profile
into gpt-oss-120b on Cerebras with a Pydantic response schema (see the
`cerebras` skill), producing the carousel/caption-set/Reel-script package.

The voice profile reaching step 2 is `extract_style`'s descriptors, never the
agent's raw writing samples. The samples advertise other properties, and any
prompt that showed them to the assembly step eventually carried their facts
into the copy - see docs/VOICE-CONTAMINATION.md.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from litellm import completion
from pydantic import BaseModel

VISION_MODEL = "openrouter/google/gemini-2.5-flash"
ASSEMBLY_MODEL = "openrouter/openai/gpt-oss-120b"
CEREBRAS_BODY = {"provider": {"order": ["cerebras"]}}

# Captioning is one call per photo, so only the first few photos reach the
# vision model - enough for a full carousel without a slow, costly request.
MAX_CAPTIONED_PHOTOS = 8

PHOTO_PROMPT = (
    "You are cataloguing photos of a luxury resort-market property for a real"
    " estate agent. In two or three sentences, describe what this photo shows:"
    " the room or outdoor space, materials and finishes, light, views, and any"
    " standout features. Describe only what is visible."
)

ASSEMBLY_PROMPT = (
    "You are a social content writer for luxury and resort-market real estate"
    " agents. Write in the agent's own voice, matching the vocabulary, rhythm,"
    " and punctuation of their writing samples. Frame the property as a"
    " lifestyle -- mornings, light, water, entertaining, the feel of being"
    " there -- rather than a spec sheet, but keep every concrete detail"
    " accurate to the listing data and photo descriptions given."
    "\n\nProduce:"
    "\n- carousel_slides: one slide per photo, in the order the photos are"
    " listed, each with that photo's photo_number and a caption of at most two"
    " sentences grounded in what that photo actually shows."
    "\n- captions: three to five post captions, each with a short label"
    " describing its angle (for example 'Lifestyle hook', 'Just listed',"
    " 'Investment angle') and the caption text."
    "\n- reel_script: a 30-45 second Reel script with spoken lines and brief"
    " shot directions."
)

# Kept next to the numbered photo list in the user message rather than in the
# system prompt: the model reaches for "from Photo 1" in shot directions, and
# the reminder holds better when it sits beside the numbering it is about.
NUMBERING_REMINDER = (
    "The numbering above exists only to fill in each slide's photo_number."
    " That field is the one place a photo number belongs. Never write"
    " 'Photo 1' or similar in a caption, a script line, or a shot direction --"
    " describe what the image shows instead, as in 'the undulating blue"
    " sculpture', never 'the sculpture from Photo 1'."
)

# Listing columns worth showing the model, with the labels used in the prompt.
BRIEF_FIELDS = {
    "title": "Title",
    "location": "Location",
    "price": "Price (USD)",
    "beds": "Bedrooms",
    "baths": "Bathrooms",
    "interior_sqft": "Interior sqft",
    "lot_size": "Lot size",
    "property_type": "Property type",
    "mls_number": "MLS number",
    "features": "Features",
    "description": "Agent description",
}


STYLE_PROMPT = (
    "You are analysing a real estate agent's past writing so another writer can"
    " reproduce their voice on a completely different property. Capture only HOW"
    " they write, never WHAT they wrote about."
    "\n\nDescribe the form in concrete, imitable terms -- typical sentence"
    " length, cadence, register, favourite grammatical constructions,"
    " punctuation habits."
    "\n\nQuote nothing. Do not reproduce any phrase, sentence, or word list from"
    " the samples, not even to illustrate a pattern -- describe the pattern"
    " instead ('repeats a short subject-is-adjective frame across consecutive"
    " sentences'). Never mention any property, feature, condition, price,"
    " measurement, place name, date, or event that appears in the samples. A"
    " reader of your description must not be able to tell what was being"
    " advertised."
)

# Only the first few thousand characters shape the voice; the rest is more of
# the same and this runs on upload, where the agent is waiting.
MAX_STYLE_SAMPLE_CHARS = 6000


class StyleProfile(BaseModel):
    """An agent's writing style, described without any of its subject matter."""

    sentence_rhythm: str
    vocabulary: str
    punctuation: str


class SlideDraft(BaseModel):
    """One carousel slide, tied to a photo by its 1-based prompt number."""

    photo_number: int
    caption: str


class CaptionDraft(BaseModel):
    """One post caption and the angle it takes."""

    label: str
    text: str


class PackageDraft(BaseModel):
    """The full generated content package, before it is persisted."""

    carousel_slides: list[SlideDraft]
    captions: list[CaptionDraft]
    reel_script: str


def describe_photo(path: Path, content_type: str) -> str:
    """Return a short visual description of one listing photo."""
    encoded = base64.b64encode(path.read_bytes()).decode()
    response = completion(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PHOTO_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{encoded}"},
                    },
                ],
            }
        ],
    )
    return (response.choices[0].message.content or "").strip()


def extract_style(sample_text: str) -> str:
    """Distil writing samples into style descriptors, dropping their content.

    Run once when the agent uploads samples. The descriptors are what later
    generations see, so the samples' facts never reach the assembly prompt.
    """
    if not sample_text.strip():
        return ""
    response = completion(
        model=ASSEMBLY_MODEL,
        messages=[
            {"role": "system", "content": STYLE_PROMPT},
            {
                "role": "user",
                "content": "WRITING SAMPLES\n"
                + sample_text[:MAX_STYLE_SAMPLE_CHARS],
            },
        ],
        response_format=StyleProfile,
        reasoning_effort="low",
        extra_body=CEREBRAS_BODY,
    )
    style = StyleProfile.model_validate_json(response.choices[0].message.content)
    return (
        f"Sentence rhythm: {style.sentence_rhythm}"
        f"\nVocabulary: {style.vocabulary}"
        f"\nPunctuation: {style.punctuation}"
    )


def _listing_brief(listing: dict) -> str:
    """Render the listing's populated fields as labelled lines."""
    lines = [
        f"{label}: {listing[field]}"
        for field, label in BRIEF_FIELDS.items()
        if listing.get(field) not in (None, "")
    ]
    return "\n".join(lines)


def _voice_brief(style_notes: str, tone_notes: str) -> str:
    """Render the agent's voice profile, or a fallback when none is set."""
    parts = []
    if tone_notes:
        parts.append(f"Tone notes from the agent:\n{tone_notes}")
    if style_notes:
        parts.append(
            "The agent's own writing style, described below. Match it closely:"
            " if it is clipped and declarative, write clipped and declarative;"
            " if it runs long and unhurried, do the same. Reproduce its"
            f" sentence length, punctuation, and turns of phrase.\n{style_notes}"
        )
    if not parts:
        return (
            "The agent has not provided writing samples. Use a warm, confident,"
            " understated luxury voice."
        )
    return "\n\n".join(parts)


def assemble_package(
    listing: dict,
    photo_descriptions: list[str],
    style_notes: str,
    tone_notes: str,
) -> PackageDraft:
    """Generate the content package from listing data, photos, and voice."""
    photos = "\n".join(
        f"Photo {n}: {text}" for n, text in enumerate(photo_descriptions, start=1)
    )
    user_content = (
        f"LISTING\n{_listing_brief(listing)}"
        f"\n\nPHOTOS\n{photos or 'No photos were provided for this listing.'}"
        f"\n\n{NUMBERING_REMINDER}"
        f"\n\nAGENT VOICE\n{_voice_brief(style_notes, tone_notes)}"
    )
    response = completion(
        model=ASSEMBLY_MODEL,
        messages=[
            {"role": "system", "content": ASSEMBLY_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format=PackageDraft,
        reasoning_effort="low",
        extra_body=CEREBRAS_BODY,
    )
    return PackageDraft.model_validate_json(response.choices[0].message.content)


def generate_package(
    listing: dict,
    photos: list[tuple[Path, str]],
    style_notes: str,
    tone_notes: str,
) -> PackageDraft:
    """Caption the photos concurrently, then assemble the package from them.

    Photos are captioned in parallel but returned in input order, so a draft
    slide's 1-based photo_number indexes straight back into `photos`.
    """
    capped = photos[:MAX_CAPTIONED_PHOTOS]
    with ThreadPoolExecutor(max_workers=len(capped)) as pool:
        descriptions = list(pool.map(lambda photo: describe_photo(*photo), capped))
    return assemble_package(listing, descriptions, style_notes, tone_notes)
