"""HTTP cache policy and display variants for /api/files: public catalogue/banner media may be cached by the signed-in
device for a day (write-once paths, ETag revalidation); hidden / deleted / admin-only media stays no-store."""

import io

import pytest
from PIL import Image

from shared import core as c

PUBLIC = "private, max-age=86400"
PRIVATE = "private, no-store"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _jpeg(width, height, color=(200, 30, 30)):
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, "JPEG", quality=90)
    return out.getvalue()


async def _product(isolated_db, pid, visibility="all", width=1600, deleted=False):
    master, thumb = f"yash-trade/originals/{pid}.jpg", f"yash-trade/thumbs/{pid}.jpg"
    isolated_db["object_store"][master] = (_jpeg(width, int(width * 0.75)), "image/jpeg")
    isolated_db["object_store"][thumb] = (_jpeg(400, 300), "image/jpeg")
    await isolated_db["db"].products.insert_one({"id": pid, "title": pid, "metal_type": "silver", "category": "chain", "images": [],
        "storage_path": master, "thumbnail_path": thumb, "visibility": visibility, "is_deleted": deleted, "post_type": "product",
        "created_at": c.stamp(), "updated_at": c.stamp()})
    return master, thumb


@pytest.mark.asyncio
async def test_public_media_is_cacheable_with_etag_and_conditional_requests(api_client, isolated_db, seeded_users):
    master, thumb = await _product(isolated_db, "p-public")
    res = await api_client.get(f"/api/files/{master}")
    assert res.status_code == 200 and res.headers["cache-control"] == PUBLIC and res.headers["vary"] == "Authorization"
    etag = res.headers["etag"]
    assert etag.startswith('"') and len(etag) > 10
    # unchanged bytes -> 304 without a body; a different validator -> full body again
    again = await api_client.get(f"/api/files/{master}", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == etag and again.headers["cache-control"] == PUBLIC
    other = await api_client.get(f"/api/files/{master}", headers={"If-None-Match": '"stale", W/"x"'})
    assert other.status_code == 200 and other.headers["etag"] == etag
    # the stored thumbnail is public too and has its own validator
    t = await api_client.get(f"/api/files/{thumb}")
    assert t.status_code == 200 and t.headers["cache-control"] == PUBLIC and t.headers["etag"] != etag


@pytest.mark.asyncio
async def test_display_variants_are_bounded_and_sized_from_the_master(api_client, isolated_db, seeded_users):
    master, _ = await _product(isolated_db, "p-variant", width=1600)
    full = await api_client.get(f"/api/files/{master}")
    card = await api_client.get(f"/api/files/{master}?w=800")
    small = await api_client.get(f"/api/files/{master}?w=400")
    assert card.status_code == 200 and small.status_code == 200
    with Image.open(io.BytesIO(card.content)) as im:
        assert im.width == 800 and im.height == 600 and im.format == "JPEG"
    with Image.open(io.BytesIO(small.content)) as im:
        assert im.width == 400 and im.height == 300
    assert len(small.content) < len(card.content) < len(full.content)
    # each variant is its own cacheable representation
    assert len({full.headers["etag"], card.headers["etag"], small.headers["etag"]}) == 3
    assert card.headers["cache-control"] == PUBLIC
    assert (await api_client.get(f"/api/files/{master}?w=800", headers={"If-None-Match": card.headers["etag"]})).status_code == 304
    # only the two display widths exist (bounded CPU and cache keys); a master already small enough is served as-is
    bad = await api_client.get(f"/api/files/{master}?w=123")
    assert bad.status_code == 422 and bad.json()["code"] == "INVALID_VARIANT"
    small_master, _ = await _product(isolated_db, "p-small", width=300)
    as_is = await api_client.get(f"/api/files/{small_master}?w=800")
    assert as_is.status_code == 200 and as_is.content == isolated_db["object_store"][small_master][0]


@pytest.mark.asyncio
async def test_hidden_deleted_and_admin_only_media_is_never_cacheable(api_client, isolated_db, login_helper):
    admin = (await login_helper("9000000000"))["token"]
    customer = (await login_helper("9000000004"))["token"]
    hidden, _ = await _product(isolated_db, "p-hidden", visibility="hidden")
    res = await api_client.get(f"/api/files/{hidden}", headers=_auth(admin))
    assert res.status_code == 200 and res.headers["cache-control"] == PRIVATE
    assert (await api_client.get(f"/api/files/{hidden}?w=400", headers=_auth(admin))).headers["cache-control"] == PRIVATE
    assert (await api_client.get(f"/api/files/{hidden}", headers=_auth(customer))).status_code == 403
    assert (await api_client.get(f"/api/files/{hidden}")).status_code in {401, 403}
    deleted, _ = await _product(isolated_db, "p-deleted", deleted=True)
    assert (await api_client.get(f"/api/files/{deleted}", headers=_auth(customer))).status_code == 403
    # visibility changes take effect on the very next request: the server never serves a hidden product publicly
    public, _ = await _product(isolated_db, "p-toggle")
    first = await api_client.get(f"/api/files/{public}", headers=_auth(customer))
    assert first.status_code == 200 and first.headers["cache-control"] == PUBLIC
    await isolated_db["db"].products.update_one({"id": "p-toggle"}, {"$set": {"visibility": "hidden"}})
    assert (await api_client.get(f"/api/files/{public}", headers=_auth(customer))).status_code == 403
    assert (await api_client.get(f"/api/files/{public}", headers=_auth(customer), params={"w": 400})).status_code == 403
    # a conditional request for a now-hidden image is refused as well (no 304 leak)
    assert (await api_client.get(f"/api/files/{public}", headers={**_auth(customer), "If-None-Match": first.headers["etag"]})).status_code == 403


@pytest.mark.asyncio
async def test_replacing_a_photo_produces_a_new_url_never_a_rewritten_one(api_client, isolated_db, login_helper):
    admin = (await login_helper("9000000000"))["token"]
    data = _jpeg(1200, 900)
    first = await api_client.post("/api/products/upload-image", headers=_auth(admin), files={"file": ("a.jpg", data, "image/jpeg")})
    second = await api_client.post("/api/products/upload-image", headers=_auth(admin), files={"file": ("a.jpg", data, "image/jpeg")})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["storage_path"] != second.json()["storage_path"] and first.json()["thumbnail_path"] != second.json()["thumbnail_path"]
    assert all(v.startswith("yash-trade/products/manual/") for r in (first, second) for v in (r.json()["storage_path"], r.json()["thumbnail_path"]))
    # existing objects are never overwritten with different bytes through the media layer
    from shared.media_lifecycle import tracked_put
    path = first.json()["storage_path"]
    before = isolated_db["object_store"][path][0]
    reused = await tracked_put(path, before, "image/jpeg", "manual_master", "u_admin")
    assert reused.get("reused") is True and isolated_db["object_store"][path][0] == before


@pytest.mark.asyncio
async def test_banner_media_follows_the_active_flag(api_client, isolated_db, login_helper):
    admin = (await login_helper("9000000000"))["token"]
    path = "yash-trade/banners/b1.jpg"
    isolated_db["object_store"][path] = (_jpeg(1200, 545), "image/jpeg")
    await isolated_db["db"].banners.insert_one({"id": "b1", "title": "Festive", "image_url": f"/api/files/{path}", "is_active": True})
    res = await api_client.get(f"/api/files/{path}")
    assert res.status_code == 200 and res.headers["cache-control"] == PUBLIC
    await isolated_db["db"].banners.update_one({"id": "b1"}, {"$set": {"is_active": False}})
    assert (await api_client.get(f"/api/files/{path}")).status_code in {401, 403}
    assert (await api_client.get(f"/api/files/{path}", headers=_auth(admin))).headers["cache-control"] == PRIVATE
