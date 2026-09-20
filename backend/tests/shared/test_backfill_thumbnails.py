"""tools/backfill_thumbnails.py: dry run writes nothing; apply is idempotent, compare-and-set, checkpointed/resumable and
never touches products whose only photo is an external URL."""

import importlib.util
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from shared import core as c

SPEC = importlib.util.spec_from_file_location("backfill_thumbnails", Path(__file__).resolve().parents[2] / "tools" / "backfill_thumbnails.py")
backfill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backfill)


def _jpeg(width, height):
    out = io.BytesIO()
    Image.new("RGB", (width, height), (20, 120, 200)).save(out, "JPEG", quality=90)
    return out.getvalue()


async def _seed(isolated_db):
    db, store = isolated_db["db"], isolated_db["object_store"]
    rows = []
    for i in range(3):
        pid = f"bf-master-{i}"
        store[f"yash-trade/originals/{pid}.jpg"] = (_jpeg(1600, 1200), "image/jpeg")
        rows.append({"id": pid, "title": pid, "storage_path": f"yash-trade/originals/{pid}.jpg", "thumbnail_path": "", "images": [],
                     "metal_type": "silver", "category": "chain", "visibility": "all", "is_deleted": False, "created_at": c.stamp()})
    store["yash-trade/thumbs/bf-ok.jpg"] = (_jpeg(400, 300), "image/jpeg")
    rows.append({"id": "bf-ok", "title": "has thumb", "storage_path": "yash-trade/originals/bf-ok.jpg", "thumbnail_path": "yash-trade/thumbs/bf-ok.jpg",
                 "images": [], "visibility": "all", "is_deleted": False, "created_at": c.stamp()})
    rows.append({"id": "bf-ext", "title": "external", "images": ["https://images.example.com/x.jpg"], "visibility": "all", "is_deleted": False, "created_at": c.stamp()})
    rows.append({"id": "bf-deleted", "title": "deleted", "storage_path": "yash-trade/originals/gone.jpg", "is_deleted": True, "created_at": c.stamp()})
    rows.append({"id": "bf-none", "title": "no image", "images": [], "visibility": "hidden", "is_deleted": False, "created_at": c.stamp()})
    await db.products.insert_many(rows)
    return db, store


@pytest.mark.asyncio
async def test_dry_run_reports_candidates_and_writes_nothing(isolated_db, seeded_users):
    db, store = await _seed(isolated_db)
    before = dict(store)
    report, candidates = await backfill.scan(verify=True, verify_limit=10)
    assert report["scanned"] == 6 and report["with_thumbnail"] == 1
    assert report["candidates"] == {"missing_thumbnail_with_master": 3, "external_images_only": 1, "no_image": 1}
    assert report["verify"] == {"checked": 1, "unreadable": []}
    assert {cand["id"] for cand in candidates} == {"bf-master-0", "bf-master-1", "bf-master-2", "bf-ext", "bf-none"}
    assert store == before, "a dry run never writes an object"
    assert await db.products.count_documents({"thumbnail_path": {"$nin": ["", None]}}) == 1
    assert await db.media_assets.count_documents({}) == 0


@pytest.mark.asyncio
async def test_apply_is_checkpointed_idempotent_and_compare_and_set(isolated_db, seeded_users, tmp_path):
    db, store = await _seed(isolated_db)
    ckpt = tmp_path / "ckpt.json"
    _, candidates = await backfill.scan(verify=False, verify_limit=0)
    # first run bounded to two products: the checkpoint records exactly those
    result = await backfill.apply(candidates, str(ckpt), limit=2, include_external=False)
    assert result["created"] == 2 and result["errors"] == [] and result["checkpoint_entries"] == 2
    done = json.loads(ckpt.read_text())["done"]
    assert set(done) == {"bf-master-0", "bf-master-1"}
    for pid in done:
        doc = await db.products.find_one({"id": pid}, {"_id": 0})
        assert doc["thumbnail_path"] == f"yash-trade/thumbs/{pid}.jpg" and doc["thumbnail_backfilled_at"]
        data, kind = store[doc["thumbnail_path"]]
        with Image.open(io.BytesIO(data)) as im:
            assert im.width == 400 and im.height == 300 and kind == "image/jpeg"
        assert (await db.media_assets.find_one({"path": doc["thumbnail_path"]}, {"_id": 0}))["purpose"] == "thumbnail"
    # resume: the remaining candidate is written, the done ones are skipped, the external one is still untouched
    _, candidates = await backfill.scan(verify=False, verify_limit=0)
    result = await backfill.apply(candidates, str(ckpt), limit=10, include_external=False)
    assert result["created"] == 1 and result["skipped_done"] == 0 and result["skipped_external"] == 1  # done products are no longer candidates
    assert (await db.products.find_one({"id": "bf-ext"}, {"_id": 0})).get("thumbnail_path") is None
    assert "yash-trade/thumbs/bf-ext.jpg" not in store
    # third run: nothing left to do; an existing thumbnail is never replaced (compare-and-set)
    _, candidates = await backfill.scan(verify=False, verify_limit=0)
    assert not [cand for cand in candidates if cand["category"] == "missing_thumbnail_with_master"]
    ok_before = await db.products.find_one({"id": "bf-ok"}, {"_id": 0})
    result = await backfill.apply(candidates, str(ckpt), limit=10, include_external=False)
    assert result["created"] == 0 and result["errors"] == []
    assert await db.products.find_one({"id": "bf-ok"}, {"_id": 0}) == ok_before
    assert await db.products.count_documents({"id": "bf-deleted", "thumbnail_path": {"$exists": True}}) == 0
    # idempotent object writes: re-running the generator for a done product reuses the identical object
    from shared.media_lifecycle import tracked_put
    data = await backfill.generate({"storage_path": "yash-trade/originals/bf-master-0.jpg"})
    assert (await tracked_put("yash-trade/thumbs/bf-master-0.jpg", data, "image/jpeg", "thumbnail", backfill.ACTOR)).get("reused") is True


@pytest.mark.asyncio
async def test_apply_repairs_unreadable_thumbnail_objects_only_for_that_product(isolated_db, seeded_users, tmp_path):
    db, store = await _seed(isolated_db)
    await db.products.insert_one({"id": "bf-broken", "title": "broken", "storage_path": "yash-trade/originals/bf-broken.jpg",
                                  "thumbnail_path": "yash-trade/thumbs/lost.jpg", "images": [], "visibility": "all", "is_deleted": False, "created_at": c.stamp()})
    store["yash-trade/originals/bf-broken.jpg"] = (_jpeg(1000, 1000), "image/jpeg")
    report, candidates = await backfill.scan(verify=True, verify_limit=50)
    assert report["verify"]["unreadable"] == [{"id": "bf-broken", "thumbnail_path": "yash-trade/thumbs/lost.jpg", "error": "FileNotFoundError"}]
    repair = [cand for cand in candidates if cand["category"] == "thumbnail_object_unreadable"]
    result = await backfill.apply(repair, str(tmp_path / "c.json"), limit=10, include_external=False)
    assert result["created"] == 1
    assert (await db.products.find_one({"id": "bf-broken"}, {"_id": 0}))["thumbnail_path"] == "yash-trade/thumbs/bf-broken.jpg"
    assert "yash-trade/thumbs/bf-broken.jpg" in store
