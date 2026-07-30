"""Listing CRUD, ownership, and photo upload/validation/serving tests."""

PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"


def _other_headers(client):
    """Sign up a second user and return their auth header."""
    token = client.post(
        "/api/auth/signup", json={"email": "other@b.com", "password": "pw"}
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_and_get_listing(client, auth_headers):
    body = {"title": "Oceanfront Villa", "location": "Maui", "price": 4500000, "beds": 4}
    created = client.post("/api/listings", json=body, headers=auth_headers).json()
    assert created["id"] > 0
    assert created["title"] == "Oceanfront Villa"
    assert created["photos"] == []

    fetched = client.get(f"/api/listings/{created['id']}", headers=auth_headers).json()
    assert fetched["location"] == "Maui"
    assert fetched["price"] == 4500000


def test_create_requires_title(client, auth_headers):
    resp = client.post("/api/listings", json={"location": "Aspen"}, headers=auth_headers)
    assert resp.status_code == 422


def test_list_listings_newest_first(client, auth_headers):
    client.post("/api/listings", json={"title": "One"}, headers=auth_headers)
    client.post("/api/listings", json={"title": "Two"}, headers=auth_headers)
    rows = client.get("/api/listings", headers=auth_headers).json()
    assert [r["title"] for r in rows] == ["Two", "One"]
    assert rows[0]["photo_count"] == 0


def test_update_listing(client, auth_headers):
    lid = client.post(
        "/api/listings", json={"title": "Draft"}, headers=auth_headers
    ).json()["id"]
    updated = client.put(
        f"/api/listings/{lid}", json={"price": 999000, "beds": 3}, headers=auth_headers
    ).json()
    assert updated["price"] == 999000
    assert updated["beds"] == 3
    assert updated["title"] == "Draft"


def test_listing_is_owner_scoped(client, auth_headers):
    lid = client.post(
        "/api/listings", json={"title": "Private"}, headers=auth_headers
    ).json()["id"]
    other = _other_headers(client)
    assert client.get(f"/api/listings/{lid}", headers=other).status_code == 404
    assert client.put(f"/api/listings/{lid}", json={"beds": 1}, headers=other).status_code == 404


def test_listing_requires_auth(client):
    assert client.get("/api/listings").status_code == 401
    assert client.post("/api/listings", json={"title": "x"}).status_code == 401


def test_upload_and_fetch_photo(client, auth_headers):
    lid = client.post(
        "/api/listings", json={"title": "With photos"}, headers=auth_headers
    ).json()["id"]
    resp = client.post(
        f"/api/listings/{lid}/photos",
        files=[("files", ("front.png", PNG, "image/png"))],
        headers=auth_headers,
    )
    assert resp.status_code == 200
    photos = resp.json()["photos"]
    assert len(photos) == 1
    assert photos[0]["content_type"] == "image/png"

    # url is API-relative (/listings/...); the mounted API lives under /api.
    img = client.get("/api" + photos[0]["url"], headers=auth_headers)
    assert img.status_code == 200
    assert img.content == PNG


def test_upload_rejects_wrong_type(client, auth_headers):
    lid = client.post("/api/listings", json={"title": "x"}, headers=auth_headers).json()["id"]
    resp = client.post(
        f"/api/listings/{lid}/photos",
        files=[("files", ("note.txt", b"hello", "text/plain"))],
        headers=auth_headers,
    )
    assert resp.status_code == 415


def test_upload_rejects_oversize(client, auth_headers):
    lid = client.post("/api/listings", json={"title": "x"}, headers=auth_headers).json()["id"]
    big = b"x" * (5 * 1024 * 1024 + 1)
    resp = client.post(
        f"/api/listings/{lid}/photos",
        files=[("files", ("big.png", big, "image/png"))],
        headers=auth_headers,
    )
    assert resp.status_code == 413


def test_upload_rejects_over_twenty(client, auth_headers):
    lid = client.post("/api/listings", json={"title": "x"}, headers=auth_headers).json()["id"]
    files = [("files", (f"{i}.png", PNG, "image/png")) for i in range(21)]
    resp = client.post(f"/api/listings/{lid}/photos", files=files, headers=auth_headers)
    assert resp.status_code == 400


def test_photo_is_owner_scoped(client, auth_headers):
    lid = client.post("/api/listings", json={"title": "x"}, headers=auth_headers).json()["id"]
    url = client.post(
        f"/api/listings/{lid}/photos",
        files=[("files", ("a.png", PNG, "image/png"))],
        headers=auth_headers,
    ).json()["photos"][0]["url"]
    other = _other_headers(client)
    assert client.get("/api" + url, headers=other).status_code == 404


def test_delete_photo(client, auth_headers):
    lid = client.post("/api/listings", json={"title": "x"}, headers=auth_headers).json()["id"]
    url = client.post(
        f"/api/listings/{lid}/photos",
        files=[("files", ("a.png", PNG, "image/png"))],
        headers=auth_headers,
    ).json()["photos"][0]["url"]
    pid = url.rsplit("/", 1)[-1]
    resp = client.delete(f"/api/listings/{lid}/photos/{pid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["photos"] == []
    assert client.get("/api" + url, headers=auth_headers).status_code == 404


def test_delete_unknown_photo_is_404(client, auth_headers):
    lid = client.post("/api/listings", json={"title": "x"}, headers=auth_headers).json()["id"]
    assert client.delete(f"/api/listings/{lid}/photos/9999", headers=auth_headers).status_code == 404
