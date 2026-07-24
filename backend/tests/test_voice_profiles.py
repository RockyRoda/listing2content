"""Voice profile upload, tone notes, and retrieval tests."""


def test_get_empty_default(client, auth_headers):
    resp = client.get("/api/voice-profile", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"sample_text": "", "tone_notes": "", "updated_at": None}


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


def test_tone_notes_only_keeps_sample_text(client, auth_headers):
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
