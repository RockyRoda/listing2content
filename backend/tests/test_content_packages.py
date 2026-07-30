"""Content package generation, replacement, ownership, and failure tests.

The two LLM calls are monkeypatched throughout, so the suite runs offline and
exercises the real capping, photo mapping, and persistence logic around them.
"""

import pytest

from app import generation

PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"


def _listing_with_photos(client, headers, count=2):
    """Create a listing owned by `headers` and upload `count` photos to it."""
    lid = client.post(
        "/api/listings",
        json={"title": "Oceanfront Villa", "location": "Maui"},
        headers=headers,
    ).json()["id"]
    if count:
        client.post(
            f"/api/listings/{lid}/photos",
            files=[("files", (f"{i}.png", PNG, "image/png")) for i in range(count)],
            headers=headers,
        )
    return lid


def _draft(slide_count=2, reel="Open on the pool. Cut to the lanai."):
    """A PackageDraft with `slide_count` slides, bound to photos by position."""
    return generation.PackageDraft(
        carousel_slides=[
            generation.SlideDraft(caption=f"Slide for photo {n}")
            for n in range(1, slide_count + 1)
        ],
        captions=[generation.CaptionDraft(label="Lifestyle hook", text="Golden hour.")],
        reel_script=reel,
    )


class FakeLLM:
    """Stubs both LLM steps: counts captioned photos, returns a set draft."""

    def __init__(self):
        self.described = 0
        self.draft = _draft()

    def describe_photo(self, path, content_type):
        self.described += 1
        return f"A described photo ({content_type})"

    def assemble_package(self, *args):
        return self.draft


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(generation, "describe_photo", fake.describe_photo)
    monkeypatch.setattr(generation, "assemble_package", fake.assemble_package)
    return fake


def test_generate_returns_draft_package(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers)
    resp = client.post(f"/api/listings/{lid}/package", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "draft"
    assert body["listing_id"] == lid
    assert body["reel_script"] == "Open on the pool. Cut to the lanai."
    assert [c["label"] for c in body["captions"]] == ["Lifestyle hook"]


def test_slides_reference_the_right_photos(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers)
    photo_ids = [
        p["id"] for p in client.get(f"/api/listings/{lid}", headers=auth_headers).json()["photos"]
    ]
    slides = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()["slides"]
    assert [s["listing_photo_id"] for s in slides] == photo_ids
    assert [s["order_index"] for s in slides] == [0, 1]
    assert slides[0]["photo_url"] == f"/listings/{lid}/photos/{photo_ids[0]}"


def test_slide_beyond_the_photo_count_becomes_null(client, auth_headers, fake_llm):
    """The model is asked for one slide per photo; an extra one has no photo."""
    lid = _listing_with_photos(client, auth_headers, count=1)
    fake_llm.draft = _draft(slide_count=2)
    slides = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()["slides"]
    assert slides[1]["listing_photo_id"] is None
    assert slides[1]["photo_url"] is None


def test_captioning_is_capped(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers, count=12)
    client.post(f"/api/listings/{lid}/package", headers=auth_headers)
    assert fake_llm.described == generation.MAX_CAPTIONED_PHOTOS


def test_generate_replaces_the_previous_package(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers)
    first = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()

    fake_llm.draft = _draft(slide_count=1, reel="A brand new script.")
    second = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()

    assert second["id"] != first["id"]
    assert second["reel_script"] == "A brand new script."
    assert len(second["slides"]) == 1
    assert client.get(f"/api/listings/{lid}/package", headers=auth_headers).json() == second


def test_generate_requires_a_photo(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers, count=0)
    resp = client.post(f"/api/listings/{lid}/package", headers=auth_headers)
    assert resp.status_code == 400
    assert fake_llm.described == 0


def test_llm_failure_is_502_and_keeps_the_old_package(
    client, auth_headers, fake_llm, monkeypatch
):
    lid = _listing_with_photos(client, auth_headers)
    original = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()

    def boom(*args):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(generation, "assemble_package", boom)
    assert client.post(f"/api/listings/{lid}/package", headers=auth_headers).status_code == 502
    assert client.get(f"/api/listings/{lid}/package", headers=auth_headers).json() == original


def test_get_before_generating_is_404(client, auth_headers):
    lid = _listing_with_photos(client, auth_headers)
    assert client.get(f"/api/listings/{lid}/package", headers=auth_headers).status_code == 404


def test_package_is_owner_scoped(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers)
    client.post(f"/api/listings/{lid}/package", headers=auth_headers)
    token = client.post(
        "/api/auth/signup", json={"email": "other@b.com", "password": "pw"}
    ).json()["token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/listings/{lid}/package", headers=other).status_code == 404
    assert client.post(f"/api/listings/{lid}/package", headers=other).status_code == 404


def test_package_requires_auth(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers)
    assert client.get(f"/api/listings/{lid}/package").status_code == 401
    assert client.post(f"/api/listings/{lid}/package").status_code == 401


def _edit_body(package, reel="An edited script."):
    """A PUT body echoing the package back with every piece of copy changed."""
    return {
        "reel_script": reel,
        "slides": [
            {"id": s["id"], "caption": f"Edited slide {i}"}
            for i, s in enumerate(package["slides"])
        ],
        "captions": [
            {"id": c["id"], "text": "Edited caption"} for c in package["captions"]
        ],
    }


def test_edits_persist_across_a_reload(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers)
    pkg = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()

    saved = client.put(
        f"/api/listings/{lid}/package", json=_edit_body(pkg), headers=auth_headers
    )
    assert saved.status_code == 200
    assert saved.json()["reel_script"] == "An edited script."
    assert [s["caption"] for s in saved.json()["slides"]] == [
        "Edited slide 0",
        "Edited slide 1",
    ]
    assert client.get(f"/api/listings/{lid}/package", headers=auth_headers).json() == saved.json()


def test_editing_keeps_the_slides_photo_mapping(client, auth_headers, fake_llm):
    """Edits touch caption text only - order and photo bindings are untouched."""
    lid = _listing_with_photos(client, auth_headers)
    pkg = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()
    edited = client.put(
        f"/api/listings/{lid}/package", json=_edit_body(pkg), headers=auth_headers
    ).json()
    assert [s["listing_photo_id"] for s in edited["slides"]] == [
        s["listing_photo_id"] for s in pkg["slides"]
    ]
    assert [s["order_index"] for s in edited["slides"]] == [0, 1]


def test_approve_flips_the_status(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers)
    client.post(f"/api/listings/{lid}/package", headers=auth_headers)
    approved = client.post(f"/api/listings/{lid}/package/approve", headers=auth_headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert client.get(f"/api/listings/{lid}/package", headers=auth_headers).json()["status"] == "approved"


def test_editing_an_approved_package_returns_it_to_draft(
    client, auth_headers, fake_llm
):
    lid = _listing_with_photos(client, auth_headers)
    pkg = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()
    client.post(f"/api/listings/{lid}/package/approve", headers=auth_headers)
    edited = client.put(
        f"/api/listings/{lid}/package", json=_edit_body(pkg), headers=auth_headers
    ).json()
    assert edited["status"] == "draft"


def test_editing_another_packages_row_is_rejected(client, auth_headers, fake_llm):
    """An id from a different package must not be writable through this one."""
    first = _listing_with_photos(client, auth_headers)
    second = _listing_with_photos(client, auth_headers)
    other = client.post(f"/api/listings/{second}/package", headers=auth_headers).json()
    mine = client.post(f"/api/listings/{first}/package", headers=auth_headers).json()

    body = _edit_body(mine)
    body["slides"][0]["id"] = other["slides"][0]["id"]
    assert client.put(
        f"/api/listings/{first}/package", json=body, headers=auth_headers
    ).status_code == 404

    # The rejected save left both packages exactly as they were.
    assert client.get(f"/api/listings/{first}/package", headers=auth_headers).json() == mine
    assert client.get(f"/api/listings/{second}/package", headers=auth_headers).json() == other


def test_editing_another_packages_caption_is_rejected(client, auth_headers, fake_llm):
    """The caption branch of the scoping guard, alongside the slide one above."""
    first = _listing_with_photos(client, auth_headers)
    second = _listing_with_photos(client, auth_headers)
    other = client.post(f"/api/listings/{second}/package", headers=auth_headers).json()
    mine = client.post(f"/api/listings/{first}/package", headers=auth_headers).json()

    body = _edit_body(mine)
    body["captions"][0]["id"] = other["captions"][0]["id"]
    assert client.put(
        f"/api/listings/{first}/package", json=body, headers=auth_headers
    ).status_code == 404
    assert client.get(f"/api/listings/{first}/package", headers=auth_headers).json() == mine


def test_editing_before_generating_is_404(client, auth_headers):
    lid = _listing_with_photos(client, auth_headers)
    body = {"reel_script": "No package to edit.", "slides": [], "captions": []}
    assert client.put(
        f"/api/listings/{lid}/package", json=body, headers=auth_headers
    ).status_code == 404
    assert client.post(
        f"/api/listings/{lid}/package/approve", headers=auth_headers
    ).status_code == 404


def test_edit_and_approve_are_owner_scoped(client, auth_headers, fake_llm):
    lid = _listing_with_photos(client, auth_headers)
    pkg = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()
    token = client.post(
        "/api/auth/signup", json={"email": "intruder@b.com", "password": "pw"}
    ).json()["token"]
    other = {"Authorization": f"Bearer {token}"}

    assert client.put(
        f"/api/listings/{lid}/package", json=_edit_body(pkg), headers=other
    ).status_code == 404
    assert client.post(
        f"/api/listings/{lid}/package/approve", headers=other
    ).status_code == 404
    assert client.put(f"/api/listings/{lid}/package", json=_edit_body(pkg)).status_code == 401
    assert client.post(f"/api/listings/{lid}/package/approve").status_code == 401


def test_regenerating_replaces_an_approved_package_with_a_draft(
    client, auth_headers, fake_llm
):
    lid = _listing_with_photos(client, auth_headers)
    client.post(f"/api/listings/{lid}/package", headers=auth_headers)
    client.post(f"/api/listings/{lid}/package/approve", headers=auth_headers)
    regenerated = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()
    assert regenerated["status"] == "draft"


def test_deleting_a_used_photo_clears_the_slide_reference(
    client, auth_headers, fake_llm
):
    lid = _listing_with_photos(client, auth_headers)
    slides = client.post(f"/api/listings/{lid}/package", headers=auth_headers).json()["slides"]
    photo_id = slides[0]["listing_photo_id"]

    assert client.delete(
        f"/api/listings/{lid}/photos/{photo_id}", headers=auth_headers
    ).status_code == 200
    refreshed = client.get(f"/api/listings/{lid}/package", headers=auth_headers).json()
    assert refreshed["slides"][0]["listing_photo_id"] is None
