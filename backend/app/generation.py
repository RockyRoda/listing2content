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
    "\n- carousel_slides: exactly one slide per photo, in the same order as the"
    " PHOTOS list, each a caption of at most two sentences grounded in what"
    " that photo actually shows."
    "\n- captions: three to five post captions, each with a short label"
    " describing its angle (for example 'Lifestyle hook', 'Just listed',"
    " 'Investment angle') and the caption text."
    "\n- reel_script: a 30-45 second Reel script with spoken lines and brief"
    " shot directions. Write each shot direction as what the viewer sees, for"
    " an editor who cannot see the photo list."
)

# Kept next to the photo list in the user message rather than in the system
# prompt: an earlier experiment established that placement beats wording for
# this model, and this reminder is about the list it sits beside.
#
# The photos used to be numbered so slides could name a photo_number. Writing
# shot directions over a numbered manifest pulled the model into pointing back
# at it ("the sculpture from photo 2") in 22% of runs, so the numbers are gone
# and slides map to photos by position. Ordinals ("the first photo") survived
# the numbers, hence the second sentence.
SOURCE_REMINDER = (
    "This list is your source material, not something to mention. Never refer"
    " to these photos as photos, and never by their position: no 'photo 2',"
    " no 'the first photo', no 'the next image'. In captions and shot"
    " directions, name what the viewer sees instead, as in 'the undulating"
    " blue sculpture'."
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


CHAT_PROMPT = (
    "You are the assistant inside a content tool for luxury and resort-market"
    " real estate agents. The agent is working on one listing, and you do two"
    " things for them: record listing details they mention, and rewrite copy in"
    " their generated content package when they ask for a change."
    "\n\nlisting_updates: set only the fields the agent actually gave you a"
    " value for in this message, and leave every other field null. Never infer,"
    " round, or invent a value, and never repeat a value that is already"
    " recorded. If they were vague ('it's a big lot'), leave the field null and"
    " ask them for the value in your reply."
    "\n\nslide_edits and caption_edits: address rows by the slide_id and"
    " caption_id given below, and include only the rows you are changing. Send"
    " the complete new text for a row, not a fragment or a description of the"
    " change. reel_script is the whole replacement script, or null to leave it"
    " alone. Rewritten copy keeps the agent's voice and stays accurate to the"
    " listing data -- change what they asked you to change and nothing else."
    "\n\nreply: one or two sentences, to the agent, saying what you recorded or"
    " rewrote, or asking for what you need. Never claim a change you did not put"
    " in the fields above."
)

# Sits next to the package copy rather than in CHAT_PROMPT, on the same lesson
# as SOURCE_REMINDER: a constraint about a block of material works where it sits
# beside it. Without this, a turn whose predecessor rewrote a caption re-sent
# that rewrite alongside whatever it had actually been asked - 4 of 5 measured
# runs - which returned an approved package to draft for no reason.
EDIT_REMINDER = (
    "That is the copy as it stands right now, and it already includes every"
    " edit you have made in this conversation. Those are saved. Do not send"
    " them again: leave slide_edits and caption_edits empty and reel_script"
    " null unless the agent's latest message asks for a further change to the"
    " copy itself."
)

# Enough turns for the agent to say "make that shorter" and be understood,
# without growing the prompt without limit over a long session.
MAX_CHAT_HISTORY = 20


class StyleProfile(BaseModel):
    """An agent's writing style, described without any of its subject matter."""

    sentence_rhythm: str
    vocabulary: str
    punctuation: str


class SlideDraft(BaseModel):
    """One carousel slide. Tied to a photo by its position in the list."""

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


class ListingPatch(BaseModel):
    """Listing fields the agent named in chat; null means "leave this alone".

    Mirrors listings.ListingUpdate. Kept here rather than imported so this
    module stays free of the HTTP layer - it is the one part of the app that
    needs no router, database, or request to test.
    """

    title: str | None
    location: str | None
    price: int | None
    beds: int | None
    baths: float | None
    interior_sqft: int | None
    lot_size: str | None
    property_type: str | None
    mls_number: str | None
    features: str | None
    description: str | None


class SlideEditDraft(BaseModel):
    """A rewrite of one carousel slide, addressed by its row id."""

    slide_id: int
    caption: str


class CaptionEditDraft(BaseModel):
    """A rewrite of one post caption, addressed by its row id."""

    caption_id: int
    text: str


class ChatTurn(BaseModel):
    """One assistant turn: what to say, and what to change while saying it."""

    reply: str
    listing_updates: ListingPatch
    slide_edits: list[SlideEditDraft]
    caption_edits: list[CaptionEditDraft]
    reel_script: str | None


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
    photos = "\n".join(f"- {text}" for text in photo_descriptions)
    user_content = (
        f"LISTING\n{_listing_brief(listing)}"
        f"\n\nPHOTOS, in order\n"
        f"{photos or 'No photos were provided for this listing.'}"
        f"\n\n{SOURCE_REMINDER}"
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

    Photos are captioned in parallel but returned in input order, so the nth
    draft slide belongs to the nth photo. An empty list skips captioning
    entirely and leaves assemble_package to note that no photos were given -
    a pool sized on an empty list would raise instead.
    """
    capped = photos[:MAX_CAPTIONED_PHOTOS]
    descriptions: list[str] = []
    if capped:
        with ThreadPoolExecutor(max_workers=len(capped)) as pool:
            descriptions = list(pool.map(lambda photo: describe_photo(*photo), capped))
    return assemble_package(listing, descriptions, style_notes, tone_notes)


def _listing_state(listing: dict) -> str:
    """Render every listing field, naming the unset ones.

    Unlike _listing_brief, which drops empty fields so the writer never sees a
    blank, chat needs to know what is missing so it can ask for it.
    """
    return "\n".join(
        f"{label}: {listing[field] if listing.get(field) not in (None, '') else '(not set)'}"
        for field, label in BRIEF_FIELDS.items()
    )


def _package_state(package: dict | None) -> str:
    """Render the package's copy with the row ids chat must address it by."""
    if package is None:
        return (
            "No content package has been generated for this listing yet. There"
            " is no copy to edit and no way to save any: slide_edits,"
            " caption_edits, and reel_script cannot be used until one exists."
            " If the agent asks for a copy change, do not draft, quote, or"
            " describe one, and do not report it as done -- say the package has"
            " to be generated first."
        )
    lines = ["Reel script:", package["reel_script"], "", "Carousel slides:"]
    lines += [f"- slide_id {s['id']}: {s['caption']}" for s in package["slides"]]
    lines += ["", "Post captions:"]
    lines += [f"- caption_id {c['id']} ({c['label']}): {c['text']}" for c in package["captions"]]
    return "\n".join(lines)


def chat_turn(
    listing: dict,
    package: dict | None,
    history: list[dict],
    message: str,
    style_notes: str,
    tone_notes: str,
) -> ChatTurn:
    """Answer the agent's message, and say what to record or rewrite with it.

    History carries only what was said. The listing and package state goes in
    the current message instead, so the model reads today's rows rather than
    the copy of them that some earlier turn quoted.
    """
    context = (
        f"CURRENT LISTING\n{_listing_state(listing)}"
        f"\n\nCURRENT CONTENT PACKAGE\n{_package_state(package)}"
        f"\n\n{EDIT_REMINDER}"
        f"\n\nAGENT VOICE\n{_voice_brief(style_notes, tone_notes)}"
        f"\n\nTHE AGENT SAYS\n{message}"
    )
    response = completion(
        model=ASSEMBLY_MODEL,
        messages=[
            {"role": "system", "content": CHAT_PROMPT},
            *history[-MAX_CHAT_HISTORY:],
            {"role": "user", "content": context},
        ],
        response_format=ChatTurn,
        reasoning_effort="low",
        extra_body=CEREBRAS_BODY,
    )
    return ChatTurn.model_validate_json(response.choices[0].message.content)
