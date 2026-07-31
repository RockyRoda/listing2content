"""The Phase 6 chat: conversational data entry and package editing.

Only litellm's `completion` is stubbed, so the real prompt building in
app.generation and the real structured-output parsing both run. Each test says
what the model replies with; the assertions are about what the endpoint then
does with it.
"""

import json

import pytest

from app import generation

PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"

PACKAGE_JSON = json.dumps(
    {
        "carousel_slides": [
            {"caption": "Light spills across the lanai."},
            {"caption": "The pool holds the last of the sun."},
        ],
        "captions": [{"label": "Lifestyle hook", "text": "Mornings here are unhurried."}],
        "reel_script": "Open wide on the water.",
    }
)

STYLE_JSON = json.dumps(
    {
        "sentence_rhythm": "Short declaratives.",
        "vocabulary": "Concrete and plain.",
        "punctuation": "Full stops.",
    }
)


def turn(
    reply="Done.",
    listing_updates=None,
    slide_edits=(),
    caption_edits=(),
    reel_script=None,
):
    """The JSON one chat turn returns, with every field unset by default."""
    blank = {name: None for name in generation.ListingPatch.model_fields}
    return json.dumps(
        {
            "reply": reply,
            "listing_updates": {**blank, **(listing_updates or {})},
            "slide_edits": [{"slide_id": i, "caption": c} for i, c in slide_edits],
            "caption_edits": [{"caption_id": i, "text": t} for i, t in caption_edits],
            "reel_script": reel_script,
        }
    )


class Llm:
    """Stubs litellm.completion for all three call kinds, recording the prompts.

    Dispatch is on `response_format`, so a test never has to predict how many
    calls happen or in what order. `reply` is reassigned between turns to drive
    a conversation.
    """

    def __init__(self):
        self.reply = turn()
        self.calls = []
        self.fail = False

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("the provider dropped the connection")
        fmt = kwargs.get("response_format")
        if fmt is generation.ChatTurn:
            body = self.reply
        elif fmt is generation.PackageDraft:
            body = PACKAGE_JSON
        elif fmt is generation.StyleProfile:
            body = STYLE_JSON
        else:
            body = "A room, photographed."

        class Response:
            choices = [type("C", (), {"message": type("M", (), {"content": body})()})()]

        return Response()

    @property
    def chat_calls(self):
        return [c for c in self.calls if c.get("response_format") is generation.ChatTurn]

    def prompt(self):
        """Everything sent on the most recent chat call, as one string."""
        return "".join(m["content"] for m in self.chat_calls[-1]["messages"])


@pytest.fixture
def llm(monkeypatch):
    stub = Llm()
    monkeypatch.setattr(generation, "completion", stub)
    return stub


@pytest.fixture
def listing(client, auth_headers):
    """A listing with two photos, ready to generate a package from."""
    listing_id = client.post(
        "/api/listings",
        json={"title": "Oceanfront Villa Kai", "location": "Wailea, Maui"},
        headers=auth_headers,
    ).json()["id"]
    client.post(
        f"/api/listings/{listing_id}/photos",
        files=[("files", (f"{i}.png", PNG, "image/png")) for i in range(2)],
        headers=auth_headers,
    )
    return listing_id


def say(client, headers, listing_id, message="Tell me about it."):
    return client.post(
        f"/api/listings/{listing_id}/chat", json={"message": message}, headers=headers
    )


def generate(client, headers, listing_id):
    return client.post(f"/api/listings/{listing_id}/package", headers=headers).json()


# --- The transcript ---


def test_chat_starts_empty(client, auth_headers, listing):
    assert client.get(f"/api/listings/{listing}/chat", headers=auth_headers).json() == []


def test_a_turn_records_both_sides_in_order(client, auth_headers, listing, llm):
    llm.reply = turn(reply="Four beds it is.")
    body = say(client, auth_headers, listing, "It has four beds.").json()

    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "It has four beds."),
        ("assistant", "Four beds it is."),
    ]


def test_the_transcript_survives_a_reload(client, auth_headers, listing, llm):
    say(client, auth_headers, listing, "First message.")
    llm.reply = turn(reply="Second answer.")
    say(client, auth_headers, listing, "Second message.")

    reloaded = client.get(f"/api/listings/{listing}/chat", headers=auth_headers).json()
    assert [m["content"] for m in reloaded] == [
        "First message.",
        "Done.",
        "Second message.",
        "Second answer.",
    ]


def test_earlier_turns_are_replayed_to_the_model(client, auth_headers, listing, llm):
    """Without history, a follow-up like 'make that shorter' has no referent."""
    say(client, auth_headers, listing, "It has four beds.")
    say(client, auth_headers, listing, "And three baths.")

    history = llm.chat_calls[-1]["messages"][1:-1]
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "It has four beds."),
        ("assistant", "Done."),
    ]


def test_history_is_capped(client, auth_headers, listing, llm):
    """A long session must not grow the prompt without limit."""
    for i in range(generation.MAX_CHAT_HISTORY):
        say(client, auth_headers, listing, f"Message {i}.")

    history = llm.chat_calls[-1]["messages"][1:-1]
    assert len(history) == generation.MAX_CHAT_HISTORY


# --- Job one: conversational data entry ---


def test_chat_fills_in_listing_fields(client, auth_headers, listing, llm):
    llm.reply = turn(
        reply="Recorded: four beds, 4.5 baths.",
        listing_updates={"beds": 4, "baths": 4.5, "price": 8950000},
    )
    assert say(client, auth_headers, listing, "4 beds, 4.5 baths, $8.95M").json()[
        "listing_changed"
    ]

    saved = client.get(f"/api/listings/{listing}", headers=auth_headers).json()
    assert (saved["beds"], saved["baths"], saved["price"]) == (4, 4.5, 8950000)


def test_untouched_fields_are_left_alone(client, auth_headers, listing, llm):
    """Null means "leave this alone", not "clear this"."""
    llm.reply = turn(listing_updates={"beds": 4})
    say(client, auth_headers, listing, "Four beds.")

    saved = client.get(f"/api/listings/{listing}", headers=auth_headers).json()
    assert saved["title"] == "Oceanfront Villa Kai"
    assert saved["location"] == "Wailea, Maui"


def test_a_turn_that_changes_nothing_reports_nothing(client, auth_headers, listing, llm):
    llm.reply = turn(reply="What is the asking price?")
    body = say(client, auth_headers, listing, "Hello.").json()

    assert body["listing_changed"] is False
    assert body["package_changed"] is False


def test_the_prompt_names_the_fields_still_missing(client, auth_headers, listing, llm):
    """Chat can only ask for what it knows is absent."""
    say(client, auth_headers, listing)
    prompt = llm.prompt()

    assert "Title: Oceanfront Villa Kai" in prompt
    assert "Bedrooms: (not set)" in prompt
    assert "MLS number: (not set)" in prompt


# --- Job two: conversational package editing ---


def test_chat_edits_a_caption(client, auth_headers, listing, llm):
    pkg = generate(client, auth_headers, listing)
    caption_id = pkg["captions"][0]["id"]

    llm.reply = turn(
        reply="Tightened it.", caption_edits=[(caption_id, "Mornings are slow here.")]
    )
    assert say(client, auth_headers, listing, "Make that caption shorter.").json()[
        "package_changed"
    ]

    reloaded = client.get(f"/api/listings/{listing}/package", headers=auth_headers).json()
    assert reloaded["captions"][0]["text"] == "Mornings are slow here."


def test_chat_edits_a_slide_and_the_reel_script(client, auth_headers, listing, llm):
    pkg = generate(client, auth_headers, listing)
    slide_id = pkg["slides"][1]["id"]

    llm.reply = turn(
        slide_edits=[(slide_id, "Dusk settles on the water.")],
        reel_script="A tighter script.",
    )
    say(client, auth_headers, listing, "Redo the second slide and the script.")

    reloaded = client.get(f"/api/listings/{listing}/package", headers=auth_headers).json()
    assert reloaded["slides"][1]["caption"] == "Dusk settles on the water."
    assert reloaded["slides"][0]["caption"] == "Light spills across the lanai."
    assert reloaded["reel_script"] == "A tighter script."


def test_an_untouched_reel_script_is_kept(client, auth_headers, listing, llm):
    """A null script must not blank the column on a slide-only edit."""
    pkg = generate(client, auth_headers, listing)

    llm.reply = turn(slide_edits=[(pkg["slides"][0]["id"], "New words.")])
    say(client, auth_headers, listing, "Redo the first slide.")

    reloaded = client.get(f"/api/listings/{listing}/package", headers=auth_headers).json()
    assert reloaded["reel_script"] == pkg["reel_script"]


def test_the_prompt_carries_the_current_copy_and_its_row_ids(
    client, auth_headers, listing, llm
):
    """The model can only address a row it has been given the id of."""
    pkg = generate(client, auth_headers, listing)
    say(client, auth_headers, listing, "What have we got?")
    prompt = llm.prompt()

    assert f"slide_id {pkg['slides'][0]['id']}: Light spills across the lanai." in prompt
    assert f"caption_id {pkg['captions'][0]['id']} (Lifestyle hook)" in prompt
    assert "Open wide on the water." in prompt


def test_copy_edits_are_refused_before_a_package_exists(client, auth_headers, listing, llm):
    """There are no rows to address, so a rewrite must not 404 the whole turn."""
    llm.reply = turn(reply="Sure.", reel_script="A script from nowhere.")
    resp = say(client, auth_headers, listing, "Write me a script.")

    assert resp.status_code == 200
    assert resp.json()["package_changed"] is False
    assert client.get(f"/api/listings/{listing}/package", headers=auth_headers).status_code == 404


def test_the_prompt_says_when_there_is_nothing_to_edit(client, auth_headers, listing, llm):
    """Told only that copy is unavailable, the model still drafted some and
    reported it done in 2 of 6 runs; the text now forbids that outright."""
    say(client, auth_headers, listing)
    prompt = llm.prompt()

    assert "No content package has been generated" in prompt
    assert "do not draft, quote, or describe one" in prompt


def test_the_prompt_says_earlier_edits_are_already_saved(client, auth_headers, listing, llm):
    """Without this, a turn after a rewrite re-sent that rewrite in 4 of 5 runs,
    returning an approved package to draft for no reason. It sits beside the
    copy it governs, not in the system prompt - see EDIT_REMINDER."""
    generate(client, auth_headers, listing)
    say(client, auth_headers, listing, "Anything.")

    assert generation.EDIT_REMINDER in llm.prompt()


def test_a_copy_edit_returns_an_approved_package_to_draft(
    client, auth_headers, listing, llm
):
    """Approval covers the exact copy approved - the Phase 5 rule, inherited."""
    pkg = generate(client, auth_headers, listing)
    client.post(f"/api/listings/{listing}/package/approve", headers=auth_headers)

    llm.reply = turn(caption_edits=[(pkg["captions"][0]["id"], "Reworded.")])
    say(client, auth_headers, listing, "Reword that caption.")

    reloaded = client.get(f"/api/listings/{listing}/package", headers=auth_headers).json()
    assert reloaded["status"] == "draft"


def test_talking_about_the_listing_leaves_an_approved_package_approved(
    client, auth_headers, listing, llm
):
    """Only a copy rewrite un-approves; recording a spec must not."""
    generate(client, auth_headers, listing)
    client.post(f"/api/listings/{listing}/package/approve", headers=auth_headers)

    llm.reply = turn(listing_updates={"beds": 4})
    say(client, auth_headers, listing, "Four beds.")

    reloaded = client.get(f"/api/listings/{listing}/package", headers=auth_headers).json()
    assert reloaded["status"] == "approved"


def test_a_row_id_from_another_package_is_rejected(client, auth_headers, listing, llm):
    """apply_edits scopes every UPDATE to the package, and chat inherits that."""
    generate(client, auth_headers, listing)
    other = client.post(
        "/api/listings", json={"title": "Second villa"}, headers=auth_headers
    ).json()["id"]
    client.post(
        f"/api/listings/{other}/photos",
        files=[("files", ("a.png", PNG, "image/png"))],
        headers=auth_headers,
    )
    other_pkg = generate(client, auth_headers, other)

    llm.reply = turn(caption_edits=[(other_pkg["captions"][0]["id"], "Not yours.")])
    assert say(client, auth_headers, listing, "Change that.").status_code == 404

    untouched = client.get(f"/api/listings/{other}/package", headers=auth_headers).json()
    assert untouched["captions"][0]["text"] == "Mornings here are unhurried."


# --- The voice, and the contamination invariant ---


def test_chat_writes_with_the_style_notes_and_never_the_samples(
    client, auth_headers, listing, llm
):
    """Chat rewrites listing copy, so docs/VOICE-CONTAMINATION.md binds it too."""
    client.put(
        "/api/voice-profile",
        files=[("files", ("s.txt", b"Roof is new. Open Saturday.", "text/plain"))],
        data={"tone_notes": "Warm, unhurried."},
        headers=auth_headers,
    )
    say(client, auth_headers, listing, "How does this read?")
    prompt = llm.prompt()

    assert "Short declaratives." in prompt
    assert "Warm, unhurried." in prompt
    assert "Roof is new" not in prompt
    assert "Open Saturday" not in prompt


# --- Failure and scoping ---


def test_a_provider_failure_is_a_502_and_records_nothing(
    client, auth_headers, listing, llm
):
    llm.fail = True
    assert say(client, auth_headers, listing, "Anything.").status_code == 502
    assert client.get(f"/api/listings/{listing}/chat", headers=auth_headers).json() == []


def test_another_agent_cannot_read_or_join_the_conversation(client, auth_headers, listing, llm):
    say(client, auth_headers, listing, "My private notes.")
    other = client.post(
        "/api/auth/signup", json={"email": "two@studio.com", "password": "pw"}
    ).json()["token"]
    H = {"Authorization": f"Bearer {other}"}

    assert client.get(f"/api/listings/{listing}/chat", headers=H).status_code == 404
    assert say(client, H, listing, "Set the price to 1.").status_code == 404


def test_chat_needs_a_token(client, listing):
    assert client.get(f"/api/listings/{listing}/chat").status_code == 401
    assert client.post(f"/api/listings/{listing}/chat", json={"message": "hi"}).status_code == 401


# --- Routing (per docs/PLAN.md) ---


def test_chat_routes_through_cerebras(client, auth_headers, listing, llm):
    say(client, auth_headers, listing)
    call = llm.chat_calls[-1]
    assert call["model"] == generation.ASSEMBLY_MODEL
    assert call["extra_body"] == {"provider": {"order": ["cerebras"]}}
