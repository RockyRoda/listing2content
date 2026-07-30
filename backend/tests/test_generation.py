"""Unit tests for the two LLM steps in app.generation.

These are the only tests that exercise generation itself: everywhere else the
module is monkeypatched away. The seam here is one level lower - litellm's
`completion` - so the real prompt building and the real structured-output
parsing both run, offline and with no API key.
"""

import base64
import json

import pytest

from app import generation

PACKAGE_JSON = json.dumps(
    {
        "carousel_slides": [{"caption": "Light pours across the lanai."}],
        "captions": [{"label": "Lifestyle hook", "text": "Mornings here are slow."}],
        "reel_script": "Open wide on the water. Push in on the pool.",
    }
)

STYLE_JSON = json.dumps(
    {
        "sentence_rhythm": "Short declaratives, often in threes.",
        "vocabulary": "Plain, concrete, no ornament.",
        "punctuation": "Full stops over commas; no exclamation marks.",
    }
)

LISTING = {
    "title": "Oceanfront Villa Kai",
    "location": "Wailea, Maui",
    "price": 8950000,
    "beds": 4,
    "baths": 4.5,
    "interior_sqft": None,
    "lot_size": "",
    "property_type": None,
    "mls_number": None,
    "features": "Infinity pool, private beach path",
    "description": None,
}


def _response(content):
    """Minimal stand-in for a litellm ModelResponse."""

    class Message:
        def __init__(self, text):
            self.content = text

    class Choice:
        def __init__(self, text):
            self.message = Message(text)

    class Response:
        def __init__(self, text):
            self.choices = [Choice(text)]

    return Response(content)


def _describe_from_bytes(kwargs):
    """Derive a photo description from the photo's own bytes.

    Captioning runs in a thread pool, so a double that handed out queued
    replies could attribute one to the wrong photo - masking an ordering bug or
    inventing one. Keying each reply to its request makes order assertions mean
    something.
    """
    url = kwargs["messages"][0]["content"][1]["image_url"]["url"]
    return "Description of " + base64.b64decode(url.split(",", 1)[1]).decode()


class FakeCompletion:
    """Stands in for litellm.completion, dispatching on the kind of call.

    The two steps are told apart by `response_format`, so a test never has to
    predict how many calls happen or in what order.
    """

    def __init__(self, package, style, vision):
        self.package = package
        self.style = style
        self.vision = vision or _describe_from_bytes
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        fmt = kwargs.get("response_format")
        if fmt is generation.PackageDraft:
            return _response(self.package)
        if fmt is generation.StyleProfile:
            return _response(self.style)
        return _response(self.vision(kwargs))

    @property
    def last(self):
        return self.calls[-1]

    @property
    def vision_calls(self):
        return [c for c in self.calls if "response_format" not in c]

    def structured_call(self):
        """The one call that asked for a schema."""
        return next(c for c in self.calls if "response_format" in c)

    def user_content(self):
        return self.structured_call()["messages"][-1]["content"]

    def system_content(self):
        return self.structured_call()["messages"][0]["content"]


@pytest.fixture
def fake_completion(monkeypatch):
    """Replace litellm.completion inside app.generation."""

    def install(package=PACKAGE_JSON, style=STYLE_JSON, vision=None):
        fake = FakeCompletion(package, style, vision)
        monkeypatch.setattr(generation, "completion", fake)
        return fake

    return install


# --- Structured output parsing (the Phase 8 requirement) ---


def test_assemble_package_parses_the_structured_output(fake_completion):
    fake = fake_completion()
    draft = generation.assemble_package(LISTING, ["A wide lanai."], "", "")

    assert isinstance(draft, generation.PackageDraft)
    assert [s.caption for s in draft.carousel_slides] == ["Light pours across the lanai."]
    assert draft.captions[0].label == "Lifestyle hook"
    assert draft.reel_script.startswith("Open wide")
    assert fake.last["response_format"] is generation.PackageDraft


def test_assemble_package_rejects_a_payload_missing_a_field(fake_completion):
    """A reply that is not the agreed shape must fail loudly, not half-parse."""
    fake_completion(package=json.dumps({"carousel_slides": [{"caption": "x"}]}))
    with pytest.raises(Exception):
        generation.assemble_package(LISTING, ["A wide lanai."], "", "")


def test_assemble_package_rejects_non_json(fake_completion):
    fake_completion(package="Sorry, I cannot help with that.")
    with pytest.raises(Exception):
        generation.assemble_package(LISTING, ["A wide lanai."], "", "")


def test_extract_style_parses_and_formats_the_profile(fake_completion):
    fake_completion()
    notes = generation.extract_style("Three beds. Priced to move.")

    assert "Sentence rhythm: Short declaratives, often in threes." in notes
    assert "Vocabulary: Plain, concrete, no ornament." in notes
    assert "Punctuation: Full stops over commas; no exclamation marks." in notes


def test_extract_style_skips_the_call_for_blank_samples(fake_completion):
    fake = fake_completion()
    assert generation.extract_style("   \n  ") == ""
    assert fake.calls == []


def test_extract_style_truncates_long_samples(fake_completion):
    """Only the leading characters shape the voice, and the agent is waiting."""
    fake = fake_completion()
    generation.extract_style("x" * (generation.MAX_STYLE_SAMPLE_CHARS + 500))
    assert fake.user_content().count("x") == generation.MAX_STYLE_SAMPLE_CHARS


# --- Prompt construction ---


def test_listing_brief_labels_fields_and_drops_empty_ones(fake_completion):
    fake = fake_completion()
    generation.assemble_package(LISTING, ["A wide lanai."], "", "")
    sent = fake.user_content()

    assert "Title: Oceanfront Villa Kai" in sent
    assert "Price (USD): 8950000" in sent
    assert "Bathrooms: 4.5" in sent
    # None and "" fields are omitted rather than sent as blanks.
    assert "Interior sqft" not in sent
    assert "Lot size" not in sent
    assert "MLS number" not in sent


def test_photo_descriptions_are_listed_unnumbered(fake_completion):
    """Numbering the photos made the model point back at the list."""
    fake = fake_completion()
    generation.assemble_package(LISTING, ["A wide lanai.", "A blue sculpture."], "", "")
    sent = fake.user_content()

    assert "- A wide lanai." in sent
    assert "- A blue sculpture." in sent
    assert generation.SOURCE_REMINDER in sent


def test_no_photos_is_stated_rather_than_left_blank(fake_completion):
    fake = fake_completion()
    generation.assemble_package(LISTING, [], "", "")
    assert "No photos were provided for this listing." in fake.user_content()


def test_voice_brief_carries_both_tone_and_style(fake_completion):
    fake = fake_completion()
    generation.assemble_package(LISTING, ["A lanai."], "Rhythm: clipped.", "Wry, warm.")
    sent = fake.user_content()
    assert "Wry, warm." in sent
    assert "Rhythm: clipped." in sent


def test_voice_brief_falls_back_when_no_profile_is_set(fake_completion):
    fake = fake_completion()
    generation.assemble_package(LISTING, ["A lanai."], "", "")
    assert "has not provided writing samples" in fake.user_content()


def test_voice_material_in_the_prompt_is_only_what_was_passed(fake_completion):
    """assemble_package can only relay the voice arguments it is given.

    The contamination guard from docs/VOICE-CONTAMINATION.md cannot be tested
    here: this function never receives the agent's raw samples, so asserting
    their facts are absent would pass no matter what the code did. The real
    invariant - that the endpoint passes style_notes and not sample_text - is
    enforced by test_voice_profiles.test_generation_never_sees_the_raw_samples
    and, over the whole flow with real prompt building, by
    test_integration_flow.test_agent_walks_the_whole_product.
    """
    fake = fake_completion()
    generation.assemble_package(LISTING, ["A lanai."], "Rhythm: clipped.", "Warm.")
    voice_section = fake.user_content().split("AGENT VOICE", 1)[1]

    assert "Rhythm: clipped." in voice_section
    assert "Warm." in voice_section
    # Nothing else from the call leaks into the voice section.
    assert "Wailea" not in voice_section
    assert "A lanai." not in voice_section


# --- Model and provider routing (per docs/PLAN.md) ---


def test_assembly_routes_through_cerebras(fake_completion):
    fake = fake_completion()
    generation.assemble_package(LISTING, ["A lanai."], "", "")
    assert fake.last["model"] == generation.ASSEMBLY_MODEL
    assert fake.last["extra_body"] == {"provider": {"order": ["cerebras"]}}


def test_vision_does_not_route_through_cerebras(fake_completion, tmp_path):
    """Cerebras does not serve vision for gpt-oss-120b, so step 1 must not use it."""
    photo = tmp_path / "shot.png"
    photo.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    fake = fake_completion(vision=lambda kwargs: "A sunlit lanai.")
    generation.describe_photo(photo, "image/png")

    assert fake.last["model"] == generation.VISION_MODEL
    assert "extra_body" not in fake.last


def test_describe_photo_sends_a_base64_data_url(fake_completion, tmp_path):
    photo = tmp_path / "shot.webp"
    photo.write_bytes(b"webp-bytes")
    fake = fake_completion(vision=lambda kwargs: "  A sunlit lanai.  ")
    caption = generation.describe_photo(photo, "image/webp")

    assert caption == "A sunlit lanai."
    parts = fake.last["messages"][0]["content"]
    encoded = base64.b64encode(b"webp-bytes").decode()
    assert parts[1]["image_url"]["url"] == f"data:image/webp;base64,{encoded}"
    assert parts[0]["text"] == generation.PHOTO_PROMPT


def test_describe_photo_tolerates_an_empty_reply(fake_completion, tmp_path):
    photo = tmp_path / "shot.png"
    photo.write_bytes(b"bytes")
    fake_completion(vision=lambda kwargs: None)
    assert generation.describe_photo(photo, "image/png") == ""


# --- generate_package: capping, ordering, and the empty case ---


def _photos(tmp_path, count):
    """Photos whose bytes identify them, so descriptions are attributable."""
    photos = []
    for i in range(count):
        path = tmp_path / f"{i}.png"
        path.write_bytes(f"photo-{i}".encode())
        photos.append((path, "image/png"))
    return photos


def test_generate_package_caps_the_photos_it_captions(fake_completion, tmp_path):
    fake = fake_completion()
    generation.generate_package({"title": "Villa"}, _photos(tmp_path, 12), "", "")
    assert len(fake.vision_calls) == generation.MAX_CAPTIONED_PHOTOS


def test_generate_package_keeps_photo_order_despite_concurrency(
    fake_completion, tmp_path
):
    """Captioning runs in a pool; the nth description must still be the nth photo."""
    fake = fake_completion()
    generation.generate_package({"title": "Villa"}, _photos(tmp_path, 6), "", "")

    sent = fake.user_content()
    positions = [sent.index(f"Description of photo-{i}") for i in range(6)]
    assert positions == sorted(positions)


def test_generate_package_with_no_photos_skips_captioning(fake_completion):
    """A pool sized on an empty list used to raise before assembly was reached."""
    fake = fake_completion()
    draft = generation.generate_package({"title": "Villa"}, [], "", "")

    assert fake.vision_calls == []
    assert "No photos were provided for this listing." in fake.user_content()
    assert isinstance(draft, generation.PackageDraft)
