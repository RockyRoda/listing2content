"""End-to-end flow: signup -> voice profile -> listing -> generate -> edit -> approve.

One test walks the whole product the way an agent does, over HTTP, on a fresh
database. The other tests cover each endpoint in isolation; this one is here to
catch the seams between them - a token that works for auth but not for
listings, a package that generates but cannot be edited, an approval that does
not survive a reload.

Only the two LLM calls are stubbed, at litellm's `completion`, so the real
prompt building and structured-output parsing run as they do in production.
"""

import base64
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
        "captions": [
            {"label": "Lifestyle hook", "text": "Mornings here are unhurried."},
            {"label": "Just listed", "text": "Newly available in Wailea."},
            {"label": "Investment angle", "text": "Rental demand runs year round."},
        ],
        "reel_script": (
            "Open wide on the water. Push in on the pool as the light drops."
            " Hold on the lanai. End on the front door, open."
        ),
    }
)

STYLE_JSON = json.dumps(
    {
        "sentence_rhythm": "Short declaratives.",
        "vocabulary": "Concrete and plain.",
        "punctuation": "Full stops, no exclamation marks.",
    }
)


@pytest.fixture
def stub_llm(monkeypatch):
    """Stub litellm.completion for both steps, recording the prompts sent."""
    sent = []

    def completion(**kwargs):
        sent.append(kwargs)
        fmt = kwargs.get("response_format")
        body = PACKAGE_JSON if fmt is generation.PackageDraft else STYLE_JSON
        if fmt is None:
            url = kwargs["messages"][0]["content"][1]["image_url"]["url"]
            decoded = base64.b64decode(url.split(",", 1)[1])
            body = f"A room, photographed ({len(decoded)} bytes)."

        class Response:
            choices = [type("C", (), {"message": type("M", (), {"content": body})()})()]

        return Response()

    monkeypatch.setattr(generation, "completion", completion)
    return sent


def test_health_answers_for_the_scripts_and_the_container(client):
    """The start scripts poll this, and the Dockerfile's HEALTHCHECK hits it."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_agent_walks_the_whole_product(client, stub_llm):
    """Signup, set a voice, build a listing, generate, edit, approve, reload."""

    # --- 1. A new agent signs up and gets a usable token ---
    signup = client.post(
        "/api/auth/signup", json={"email": "agent@studio.com", "password": "secret123"}
    )
    assert signup.status_code == 200
    token = signup.json()["token"]
    H = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=H).json()["email"] == "agent@studio.com"

    # --- 2. They upload writing samples; only descriptors are kept for later ---
    voice = client.put(
        "/api/voice-profile",
        files=[("files", ("samples.txt", b"Three beds. Priced to move.", "text/plain"))],
        data={"tone_notes": "Warm, unhurried."},
        headers=H,
    )
    assert voice.status_code == 200
    assert voice.json()["sample_text"] == "Three beds. Priced to move."
    assert "Short declaratives." in voice.json()["style_notes"]

    # --- 3. A listing, then photos on it ---
    listing_id = client.post(
        "/api/listings",
        json={"title": "Oceanfront Villa Kai", "location": "Wailea, Maui", "price": 8950000},
        headers=H,
    ).json()["id"]

    with_photos = client.post(
        f"/api/listings/{listing_id}/photos",
        files=[("files", (f"{i}.png", PNG, "image/png")) for i in range(2)],
        headers=H,
    )
    assert with_photos.status_code == 200
    photo_ids = [p["id"] for p in with_photos.json()["photos"]]
    assert len(photo_ids) == 2

    # --- 4. Generate. Both LLM steps run for real against the stub ---
    package = client.post(f"/api/listings/{listing_id}/package", headers=H)
    assert package.status_code == 200
    pkg = package.json()
    assert pkg["status"] == "draft"
    assert [s["listing_photo_id"] for s in pkg["slides"]] == photo_ids
    assert len(pkg["captions"]) == 3

    # The agent's raw sample must not have reached the assembly prompt.
    assembly = next(c for c in stub_llm if c.get("response_format") is generation.PackageDraft)
    assembly_text = "".join(m["content"] for m in assembly["messages"])
    assert "Priced to move" not in assembly_text
    assert "Warm, unhurried." in assembly_text

    # --- 5. Edit every piece of copy and save ---
    edit = client.put(
        f"/api/listings/{listing_id}/package",
        json={
            "reel_script": "A tighter script.",
            "slides": [{"id": s["id"], "caption": f"My words {i}"} for i, s in enumerate(pkg["slides"])],
            "captions": [{"id": c["id"], "text": "My caption"} for c in pkg["captions"]],
        },
        headers=H,
    )
    assert edit.status_code == 200
    assert edit.json()["reel_script"] == "A tighter script."

    # --- 6. Approve, and confirm both survive a reload ---
    assert client.post(
        f"/api/listings/{listing_id}/package/approve", headers=H
    ).json()["status"] == "approved"

    reloaded = client.get(f"/api/listings/{listing_id}/package", headers=H).json()
    assert reloaded["status"] == "approved"
    assert reloaded["reel_script"] == "A tighter script."
    assert [s["caption"] for s in reloaded["slides"]] == ["My words 0", "My words 1"]
    # Editing text left the photo bindings and ordering alone.
    assert [s["listing_photo_id"] for s in reloaded["slides"]] == photo_ids
    assert [s["order_index"] for s in reloaded["slides"]] == [0, 1]

    # --- 7. The listing still lists, and its photo still serves ---
    summaries = client.get("/api/listings", headers=H).json()
    assert [s["id"] for s in summaries] == [listing_id]
    assert summaries[0]["photo_count"] == 2
    assert client.get(
        f"/api/listings/{listing_id}/photos/{photo_ids[0]}", headers=H
    ).status_code == 200


def test_a_second_agent_shares_nothing_with_the_first(client, stub_llm):
    """The whole flow again for another agent, checking isolation at each step."""
    first = client.post(
        "/api/auth/signup", json={"email": "one@studio.com", "password": "pw"}
    ).json()
    second = client.post(
        "/api/auth/signup", json={"email": "two@studio.com", "password": "pw"}
    ).json()
    H1 = {"Authorization": f"Bearer {first['token']}"}
    H2 = {"Authorization": f"Bearer {second['token']}"}

    listing_id = client.post(
        "/api/listings", json={"title": "Agent one's villa"}, headers=H1
    ).json()["id"]
    client.post(
        f"/api/listings/{listing_id}/photos",
        files=[("files", ("a.png", PNG, "image/png"))],
        headers=H1,
    )
    client.post(f"/api/listings/{listing_id}/package", headers=H1)

    # Agent two sees none of it, and cannot touch any of it.
    assert client.get("/api/listings", headers=H2).json() == []
    assert client.get(f"/api/listings/{listing_id}", headers=H2).status_code == 404
    assert client.get(f"/api/listings/{listing_id}/package", headers=H2).status_code == 404
    assert client.post(f"/api/listings/{listing_id}/package/approve", headers=H2).status_code == 404
    assert client.put(
        f"/api/listings/{listing_id}/package",
        json={"reel_script": "mine now", "slides": [], "captions": []},
        headers=H2,
    ).status_code == 404

    # Agent two's own voice profile is independent of agent one's.
    assert client.get("/api/voice-profile", headers=H2).json()["sample_text"] == ""
