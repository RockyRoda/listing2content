"""Voice profile upload, tone notes, and retrieval tests.

The style-extraction LLM call is monkeypatched throughout, so the suite runs
offline; it echoes the samples it was given so tests can assert it ran.
"""

import pytest

from app import generation, voice_profiles


@pytest.fixture(autouse=True)
def fake_extract_style(monkeypatch):
    """Stand in for the extraction call, recording what it was asked to distil."""
    seen = []

    def extract(sample_text):
        seen.append(sample_text)
        return f"Sentence rhythm: distilled from {sample_text!r}"

    monkeypatch.setattr(voice_profiles.generation, "extract_style", extract)
    return seen


def test_get_empty_default(client, auth_headers):
    resp = client.get("/api/voice-profile", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "sample_text": "",
        "style_notes": "",
        "tone_notes": "",
        "updated_at": None,
    }


def test_put_files_sets_sample_text(client, auth_headers):
    resp = client.put(
        "/api/voice-profile",
        files=[
            ("files", ("a.txt", b"Bright and airy.", "text/plain")),
            ("files", ("b.txt", b"Timeless elegance.", "text/plain")),
        ],
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["sample_text"] == "Bright and airy.\n\nTimeless elegance."

    persisted = client.get("/api/voice-profile", headers=auth_headers).json()
    assert persisted["sample_text"] == "Bright and airy.\n\nTimeless elegance."
    assert persisted["updated_at"] is not None


def test_upload_distils_the_samples_into_style_notes(
    client, auth_headers, fake_extract_style
):
    resp = client.put(
        "/api/voice-profile",
        files=[("files", ("a.txt", b"Three beds. Priced to move.", "text/plain"))],
        headers=auth_headers,
    )
    assert fake_extract_style == ["Three beds. Priced to move."]
    assert resp.json()["style_notes"].startswith("Sentence rhythm:")


def test_generation_never_sees_the_raw_samples(client, auth_headers, monkeypatch):
    """The samples advertise other properties - only the distillation may pass."""
    monkeypatch.setattr(
        voice_profiles.generation,
        "extract_style",
        lambda _: "Sentence rhythm: short and declarative.",
    )
    client.put(
        "/api/voice-profile",
        files=[("files", ("a.txt", b"Roof is new. Open Saturday.", "text/plain"))],
        headers=auth_headers,
    )
    listing = client.post(
        "/api/listings", json={"title": "Villa"}, headers=auth_headers
    ).json()
    client.post(
        f"/api/listings/{listing['id']}/photos",
        files=[("files", ("p.jpg", b"\xff\xd8\xff", "image/jpeg"))],
        headers=auth_headers,
    )

    passed = {}

    def fake_generate(listing, photos, style_notes, tone_notes):
        passed["style_notes"] = style_notes
        return generation.PackageDraft(
            carousel_slides=[], captions=[], reel_script="Script."
        )

    monkeypatch.setattr(generation, "generate_package", fake_generate)
    client.post(f"/api/listings/{listing['id']}/package", headers=auth_headers)

    assert passed["style_notes"] == "Sentence rhythm: short and declarative."
    assert "Open Saturday" not in passed["style_notes"]


def test_tone_notes_only_keeps_sample_text(client, auth_headers, fake_extract_style):
    client.put(
        "/api/voice-profile",
        files=[("files", ("a.txt", b"Sample copy.", "text/plain"))],
        headers=auth_headers,
    )
    resp = client.put(
        "/api/voice-profile", data={"tone_notes": "Warm, confident."}, headers=auth_headers
    )
    body = resp.json()
    assert body["tone_notes"] == "Warm, confident."
    assert body["sample_text"] == "Sample copy."
    # No new samples, so the distillation is kept rather than paid for again.
    assert body["style_notes"].startswith("Sentence rhythm:")
    assert fake_extract_style == ["Sample copy."]


def test_uploading_files_replaces_sample_text(client, auth_headers):
    client.put(
        "/api/voice-profile",
        files=[("files", ("a.txt", b"First.", "text/plain"))],
        headers=auth_headers,
    )
    resp = client.put(
        "/api/voice-profile",
        files=[("files", ("b.txt", b"Second.", "text/plain"))],
        headers=auth_headers,
    )
    assert resp.json()["sample_text"] == "Second."


def test_put_rejects_non_txt(client, auth_headers):
    resp = client.put(
        "/api/voice-profile",
        files=[("files", ("photo.png", b"\x89PNG", "image/png"))],
        headers=auth_headers,
    )
    assert resp.status_code == 415


def test_voice_profile_requires_auth(client):
    assert client.get("/api/voice-profile").status_code == 401
