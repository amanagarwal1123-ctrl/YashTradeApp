"""Follow-up shared regressions: legacy units, bounded catalog pagination, PDF authoring, and source privacy."""

import asyncio
import base64
import hashlib
import io
import json
import math
import statistics
import time
from datetime import timedelta
from pathlib import Path

import fitz
import pytest
from PIL import Image
from fastapi import HTTPException

from shared import core as c
from shared import commerce
from shared import media_lifecycle as lifecycle
from shared import pdf_jobs as jobs
from shared import media_cache
from shared.pdf_parser import analyze_page


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


async def _admin_token(login_helper):
    return (await login_helper("9999813334"))["token"]


async def _seed_media_asset(isolated_db, path: str, owner_id: str = "u_admin"):
    # module: shared media accounting/ownership for product images in regression tests
    now = c.stamp()
    blob = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=")
    isolated_db["object_store"][path] = (blob, "image/png")
    await isolated_db["db"].media_assets.update_one(
        {"path": path},
        {
            "$set": {
                "path": path,
                "owner_id": owner_id,
                "content_type": "image/png",
                "size_bytes": len(blob),
                "sha256": c.digest(blob.hex()),
                "purpose": "manual_master",
                "write_state": "stored",
                "thumbnail_path": path.replace(".png", "-thumb.png"),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


@pytest.mark.asyncio
async def test_legacy_weight_and_edit_regressions(api_client, isolated_db, login_helper):
    # module: shared commerce + units for legacy weight/labour compatibility and changed ambiguous rejection
    token = await _admin_token(login_helper)
    await _seed_media_asset(isolated_db, "yash-trade/products/manual/test-w1.png")
    await _seed_media_asset(isolated_db, "yash-trade/products/manual/test-w2.png")

    now = c.stamp()
    await isolated_db["db"].products.insert_many(
        [
            {
                "id": "legacy-weight-1",
                "product_code": "TEST-WEIGHT-LEGACY-001",
                "title": "TEST Legacy Pair Weight",
                "metal_type": "silver",
                "category": "payal",
                "approx_weight": "45-55 grams per pair",
                "purity": "925",
                "images": ["/api/files/yash-trade/products/manual/test-w1.png"],
                "visibility": "hidden",
                "version": 0,
                "is_deleted": False,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "legacy-weight-2",
                "product_code": "TEST-WEIGHT-LEGACY-002",
                "title": "TEST Legacy Pair Weight Optional Purity",
                "metal_type": "silver",
                "category": "payal",
                "approx_weight": "25-35 grams per pair",
                "images": ["/api/files/yash-trade/products/manual/test-w1.png"],
                "visibility": "hidden",
                "version": 0,
                "is_deleted": False,
                "created_at": now,
                "updated_at": now,
            },
        ]
    )
    row = await isolated_db["db"].products.find_one({"id": "legacy-weight-1"}, {"_id": 0})
    row2 = await isolated_db["db"].products.find_one({"id": "legacy-weight-2"}, {"_id": 0})
    assert row["approx_weight"] == "45-55 grams per pair"
    assert row2["approx_weight"] == "25-35 grams per pair"

    title_only = await api_client.put(
        "/api/products/legacy-weight-1",
        headers=_auth(token),
        json={"version": 0, "title": "TEST Legacy Pair Weight v2"},
    )
    assert title_only.status_code == 200, title_only.text
    assert title_only.json()["approx_weight"] == "45-55 grams per pair"
    assert title_only.json().get("purity") == "925"

    image_only = await api_client.put(
        "/api/products/legacy-weight-1",
        headers=_auth(token),
        json={
            "version": title_only.json()["version"],
            "images": ["/api/files/yash-trade/products/manual/test-w2.png"],
        },
    )
    assert image_only.status_code == 200, image_only.text
    assert image_only.json()["approx_weight"] == "45-55 grams per pair"

    title_only_2 = await api_client.put(
        "/api/products/legacy-weight-2",
        headers=_auth(token),
        json={"version": 0, "title": "TEST Legacy Pair Weight Optional Purity v2"},
    )
    assert title_only_2.status_code == 200, title_only_2.text
    assert title_only_2.json()["approx_weight"] == "25-35 grams per pair"
    assert title_only_2.json().get("purity", "") == ""

    image_only_2 = await api_client.put(
        "/api/products/legacy-weight-2",
        headers=_auth(token),
        json={
            "version": title_only_2.json()["version"],
            "images": ["/api/files/yash-trade/products/manual/test-w2.png"],
        },
    )
    assert image_only_2.status_code == 200, image_only_2.text
    assert image_only_2.json()["approx_weight"] == "25-35 grams per pair"

    reject = await api_client.put(
        "/api/products/legacy-weight-1",
        headers=_auth(token),
        json={"version": image_only.json()["version"], "approx_weight": "45-55"},
    )
    assert reject.status_code == 422
    body = reject.json()
    if isinstance(body.get("detail"), dict):
        assert body["detail"].get("code") == "PRODUCT_VALIDATION"
    else:
        assert "approx_weight" in str(body.get("detail", ""))

    unchanged = await isolated_db["db"].products.find_one({"id": "legacy-weight-1"}, {"_id": 0})
    assert unchanged["approx_weight"] == "45-55 grams per pair"
    assert unchanged["version"] == image_only.json()["version"]


@pytest.mark.asyncio
async def test_rate_slab_legacy_display_versioning_and_role_scope(api_client, isolated_db, login_helper):
    # module: shared commerce rate-list edits/soft-delete + labour basis INR/kg, INR/10g, INR/piece
    billing = (await login_helper("9000000003"))["token"]
    tele = (await login_helper("9000000001"))["token"]

    created = await api_client.post(
        "/api/rate-list",
        headers=_auth(billing),
        json={"metal_type": "silver", "item_name": "TEST Legacy Slab", "labour_kg": "₹850/kg", "wastage": "2"},
    )
    assert created.status_code == 200, created.text
    slab = created.json()
    assert slab["labour_display"] == "INR 850/kg"
    assert slab["labour"]["basis"] == "kg"

    per10 = await api_client.put(
        f"/api/rate-list/{slab['id']}",
        headers=_auth(billing),
        json={"version": slab["version"], "labour": "INR 50/10g"},
    )
    assert per10.status_code == 200, per10.text
    assert per10.json()["labour_display"] == "INR 50/10g"

    per_piece = await api_client.put(
        f"/api/rate-list/{slab['id']}",
        headers=_auth(billing),
        json={"version": per10.json()["version"], "labour": "₹20/piece"},
    )
    assert per_piece.status_code == 200, per_piece.text
    assert per_piece.json()["labour_display"] == "INR 20/piece"

    stale = await api_client.put(
        f"/api/rate-list/{slab['id']}",
        headers=_auth(billing),
        json={"version": 0, "item_name": "TEST stale"},
    )
    assert stale.status_code == 409

    missing = await api_client.put(
        f"/api/rate-list/{slab['id']}",
        headers=_auth(billing),
        json={"item_name": "TEST missing version"},
    )
    assert missing.status_code == 428

    denied = await api_client.put(
        f"/api/rate-list/{slab['id']}",
        headers=_auth(tele),
        json={"version": per_piece.json()["version"], "item_name": "TEST denied"},
    )
    assert denied.status_code == 403

    required = await api_client.post(
        "/api/rate-list",
        headers=_auth(billing),
        json={"metal_type": "silver", "item_name": "   "},
    )
    assert required.status_code == 422

    now = c.stamp()
    await isolated_db["db"].rate_slabs.insert_one(
        {
            "id": "legacy-ambiguous-slab",
            "metal_type": "silver",
            "item_name": "TEST Legacy Ambiguous",
            "labour_kg": "eight hundred fifty rupees",
            "version": 0,
            "created_at": now,
            "updated_at": now,
            "is_deleted": False,
        }
    )
    listed = await api_client.get("/api/rate-list")
    assert listed.status_code == 200
    found = next(s for s in listed.json()["slabs"] if s["id"] == "legacy-ambiguous-slab")
    assert found["unit_review_required"] is True


@pytest.mark.asyncio
async def test_catalog_10k_stable_pagination_search_filters_and_benchmark(api_client, isolated_db, login_helper):
    # module: shared catalog bounded indexed pagination + 10k metadata benchmark (isolated_db only)
    admin = await _admin_token(login_helper)
    tele = (await login_helper("9000000001"))["token"]
    now = c.stamp()
    bulk = []
    for i in range(10_000):
        bulk.append(
            {
                "id": f"meta-{i:05d}",
                "product_code": f"TESTMETA-{i:05d}",
                "title": f"TEST META TITLE {i:05d}",
                "metal_type": "silver" if i % 2 == 0 else "gold",
                "category": "payal" if i % 3 == 0 else "chain",
                "visibility": "hidden" if i % 10 == 0 else "all",
                "is_deleted": False,
                "created_at": now,
                "updated_at": now,
                "version": 0,
                "images": [],
                "thumbnail_path": "",
                "storage_path": "",
                "description": f"Synthetic benchmark metadata row {i:05d}",
                "master_path": f"yash-trade/products/imported/meta-{i:05d}.png",
                "thumb_path": f"yash-trade/products/imported/meta-{i:05d}-thumb.png",
                "master_size_bytes": 345678,
                "thumbnail_size_bytes": 45678,
                "metadata_path": f"yash-trade/products/imported/meta-{i:05d}.json",
            }
        )
    await isolated_db["db"].products.insert_many(bulk)

    p1 = await api_client.get("/api/products?mode=catalog&page=1&limit=100&include_hidden=true", headers=_auth(admin))
    p1b = await api_client.get("/api/products?mode=catalog&page=1&limit=100&include_hidden=true", headers=_auth(admin))
    assert p1.status_code == 200 and p1b.status_code == 200
    ids_a = [p["id"] for p in p1.json()["products"]]
    ids_b = [p["id"] for p in p1b.json()["products"]]
    assert ids_a == ids_b
    assert len(ids_a) == 100

    all_ids = []
    for page in range(1, 101):
        res = await api_client.get(f"/api/products?mode=catalog&page={page}&limit=100&include_hidden=true", headers=_auth(admin))
        assert res.status_code == 200
        all_ids.extend([p["id"] for p in res.json()["products"]])
    assert len(all_ids) == 10_000
    assert len(set(all_ids)) == 10_000

    not_pageable = await api_client.get("/api/products?mode=discovery&page=2&limit=40", headers=_auth(admin))
    assert not_pageable.status_code == 422
    too_high = await api_client.get("/api/products?page=1&limit=101", headers=_auth(admin))
    assert too_high.status_code == 422
    tele_hidden = await api_client.get("/api/products?include_hidden=true", headers=_auth(tele))
    assert tele_hidden.status_code == 403

    search_started = time.perf_counter()
    numeric_needle = await api_client.get("/api/products?search=09999&include_hidden=true", headers=_auth(admin))
    numeric_search_ms = (time.perf_counter() - search_started) * 1000
    assert numeric_needle.status_code == 200
    assert numeric_needle.json()["total"] >= 1

    search_started = time.perf_counter()
    full_sku = await api_client.get("/api/products?search=TESTMETA-09999&include_hidden=true", headers=_auth(admin))
    words_search_ms = (time.perf_counter() - search_started) * 1000
    assert full_sku.status_code == 200
    # Text index tokenization is OR-based for this query; capture and report true behavior.
    assert full_sku.json()["total"] == 10_000

    exact_sku = await api_client.get("/api/products?product_code=TESTMETA-09999&include_hidden=true", headers=_auth(admin))
    assert exact_sku.status_code == 200
    assert exact_sku.json()["total"] == 1
    assert exact_sku.json()["products"][0]["product_code"] == "TESTMETA-09999"

    filtered = await api_client.get("/api/products?metal_type=silver&category=payal&page=1&limit=100")
    assert filtered.status_code == 200
    assert all(p["metal_type"] == "silver" and p["category"] == "payal" for p in filtered.json()["products"])

    async def one_call():
        start = time.perf_counter()
        res = await api_client.get("/api/products?page=1&limit=100&include_hidden=true", headers=_auth(admin))
        elapsed_ms = (time.perf_counter() - start) * 1000
        return elapsed_ms, len(res.content), res.status_code

    sequential = []
    for _ in range(8):
        sequential.append(await one_call())
    sequential_latencies = [x[0] for x in sequential]

    concurrent = await asyncio.gather(*[one_call() for _ in range(8)])
    latencies = [x[0] for x in concurrent]
    payloads = [x[1] for x in concurrent]
    assert all(x[2] == 200 for x in concurrent)

    explain_raw = await isolated_db["db"].command(
        "explain",
        {"find": "products", "filter": {"$text": {"$search": "TESTMETA-09999"}}},
    )
    explain = {
        "winning_stage": explain_raw.get("queryPlanner", {}).get("winningPlan", {}).get("stage"),
        "parsed_terms": explain_raw.get("queryPlanner", {}).get("winningPlan", {}).get("parsedTextQuery", {}).get("terms", []),
        "n_returned": explain_raw.get("executionStats", {}).get("nReturned"),
        "keys_examined": explain_raw.get("executionStats", {}).get("totalKeysExamined"),
        "docs_examined": explain_raw.get("executionStats", {}).get("totalDocsExamined"),
    }

    p95_idx = max(0, math.ceil(0.95 * len(latencies)) - 1)
    payload_p95_idx = max(0, math.ceil(0.95 * len(payloads)) - 1)

    benchmark = {
        "dataset_size": 10000,
        "page_limit": 100,
        "pages_checked": 100,
        "unique_ids": len(set(all_ids)),
        "stable_page_1": ids_a == ids_b,
        "latency_ms_sequential_p50": round(statistics.median(sequential_latencies), 3),
        "latency_ms_sequential_p95": round(sorted(sequential_latencies)[p95_idx], 3),
        "latency_ms_p50": round(statistics.median(latencies), 3),
        "latency_ms_p95": round(sorted(latencies)[p95_idx], 3),
        "payload_bytes_p50": int(statistics.median(payloads)),
        "payload_bytes_p95": int(sorted(payloads)[payload_p95_idx]),
        "search_semantics": {
            "numeric_needle_total": numeric_needle.json()["total"],
            "full_sku_query": "TESTMETA-09999",
            "full_sku_total": full_sku.json()["total"],
            "note": "Mongo text search tokenizes query and OR-matches terms; not exact SKU semantics",
        },
        "concurrency": 8,
        "single_query_latency_ms": {"numeric_text": round(numeric_search_ms, 3), "broad_sku_words": round(words_search_ms, 3)},
        "explain": explain,
    }
    Path("/app/test_reports/catalog_10k_benchmark_iteration16.json").write_text(json.dumps(benchmark, indent=2))


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_source_preview_rotation_mapping_offline(rotation, tmp_path: Path):
    # module: offline parser/source preview mapping keeps upright dimensions across rotated page metadata
    src = Path("/app/backend/fixtures/catalog-v1/sample.pdf")
    path = tmp_path / f"rot-{rotation}.pdf"
    with fitz.open(src) as doc:
        page = doc[1]
        page.set_rotation(rotation)
        doc.save(path)
    rows = analyze_page(str(path), 1, "template_v1")
    assert len(rows) == 2
    assert all(r.get("rotation") == rotation for r in rows)
    assert all(Image.open(io.BytesIO(r["image"])).size == (1024, 1024) for r in rows)


@pytest.mark.asyncio
async def test_media_tracked_put_maps_failure_states_and_provider_402(isolated_db, monkeypatch):
    # module: shared media lifecycle tracked_put unknown-state + provider payment-required mapping
    path = "yash-trade/products/manual/fail-402.png"

    class Provider402(Exception):
        def __init__(self):
            self.response = type("Resp", (), {"status_code": 402})()

    def fail_402(*_args, **_kwargs):
        raise Provider402()

    monkeypatch.setattr(c, "put_object", fail_402, raising=False)
    with pytest.raises(HTTPException) as err_402:
        await lifecycle.tracked_put(path, b"abc", "image/png", "manual_master", "u_admin")
    assert err_402.value.status_code == 402

    row = await isolated_db["db"].media_assets.find_one({"path": path}, {"_id": 0})
    assert row["write_state"] == "unknown"
    assert row["last_error"] == "Provider402"

    path2 = "yash-trade/products/manual/fail-generic.png"

    def fail_generic(*_args, **_kwargs):
        raise RuntimeError("temporary transport failure")

    monkeypatch.setattr(c, "put_object", fail_generic, raising=False)
    with pytest.raises(HTTPException) as err_503:
        await lifecycle.tracked_put(path2, b"abcd", "image/png", "manual_master", "u_admin")
    assert err_503.value.status_code == 503

    row2 = await isolated_db["db"].media_assets.find_one({"path": path2}, {"_id": 0})
    assert row2["write_state"] == "unknown"
    assert row2["last_error"] == "RuntimeError"


@pytest.mark.asyncio
async def test_media_budget_quota_high_watermark_and_usage_contract(api_client, isolated_db, login_helper, monkeypatch):
    # module: media accounting budget/quota enforcement + /admin/media/usage high-watermark contract
    monkeypatch.setenv("MEDIA_WRITE_BUDGET_BYTES", "100")
    monkeypatch.setenv("MEDIA_WRITE_OBJECT_LIMIT", "2")
    token = await _admin_token(login_helper)

    await isolated_db["db"].media_assets.insert_many(
        [
            {
                "path": "yash-trade/products/manual/existing-1.png",
                "size_bytes": 81,
                "content_type": "image/png",
                "owner_id": "u_admin",
                "purpose": "manual_master",
                "write_state": "stored",
                "created_at": c.stamp(),
                "updated_at": c.stamp(),
            },
            {
                "path": "yash-trade/products/manual/existing-2.png",
                "size_bytes": None,
                "content_type": "image/png",
                "owner_id": "u_admin",
                "purpose": "thumbnail",
                "write_state": "stored",
                "created_at": c.stamp(),
                "updated_at": c.stamp(),
            },
        ]
    )

    with pytest.raises(HTTPException) as budget_err:
        await lifecycle.tracked_put(
            "yash-trade/products/manual/exceed-budget.png",
            b"x" * 25,
            "image/png",
            "manual_master",
            "u_admin",
        )
    assert budget_err.value.status_code == 413

    usage = await api_client.get("/api/admin/media/usage", headers=_auth(token))
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["high_watermark"] is True
    assert body["provider_delete_supported"] is False
    assert body["inventory_complete"] is False
    assert body["groups"]


@pytest.mark.asyncio
async def test_media_lifecycle_audit_preserves_references_and_blocks_unreferenced(isolated_db):
    # module: lifecycle candidate audit keeps referenced/shared/chunk assets and blocks unreferenced when provider delete unsupported
    old = (c.now() - timedelta(days=8)).isoformat()

    assets = [
        {"path": "yash-trade/products/imported/shared-master.png", "thumbnail_path": "yash-trade/products/imported/shared-thumb.png", "created_at": old, "size_bytes": 100, "purpose": "import_master"},
        {"path": "yash-trade/products/imported/shared-thumb.png", "created_at": old, "size_bytes": 10, "purpose": "thumbnail"},
        {"path": "yash-trade/imports/job-active/chunks/0", "job_id": "job-active", "created_at": old, "size_bytes": 50, "purpose": "pdf_chunk"},
        {"path": "yash-trade/imports/job-done/chunks/0", "job_id": "job-done", "created_at": old, "size_bytes": 50, "purpose": "pdf_chunk"},
        {"path": "yash-trade/products/imported/orphan.png", "created_at": old, "size_bytes": 11, "purpose": "import_master"},
    ]
    for a in assets:
        a.setdefault("content_type", "image/png")
        a.setdefault("owner_id", "u_admin")
        a.setdefault("write_state", "stored")
        a.setdefault("updated_at", c.stamp())
    await isolated_db["db"].media_assets.insert_many(assets)

    await isolated_db["db"].products.insert_many(
        [
            {
                "id": "p-ref-shared",
                "product_code": "TEST-REF-SHARED",
                "title": "TEST shared",
                "metal_type": "silver",
                "category": "payal",
                "visibility": "all",
                "images": ["/api/files/yash-trade/products/imported/shared-master.png"],
                "storage_path": "",
                "thumbnail_path": "",
                "is_deleted": False,
                "created_at": c.stamp(),
                "updated_at": c.stamp(),
                "version": 0,
            },
            {
                "id": "p-ref-job",
                "product_code": "TEST-REF-JOB",
                "title": "TEST job",
                "metal_type": "silver",
                "category": "payal",
                "visibility": "hidden",
                "images": [],
                "storage_path": "",
                "thumbnail_path": "",
                "source_upload_id": "job-done",
                "is_deleted": False,
                "created_at": c.stamp(),
                "updated_at": c.stamp(),
                "version": 0,
            },
        ]
    )
    await isolated_db["db"].import_jobs.insert_many(
        [
            {"id": "job-active", "phase": "analyzing", "created_at": c.stamp(), "updated_at": c.stamp()},
            {"id": "job-done", "phase": "committed", "created_at": c.stamp(), "updated_at": c.stamp()},
        ]
    )

    await lifecycle.audit_candidates()

    kept_master = await isolated_db["db"].media_assets.find_one({"path": "yash-trade/products/imported/shared-master.png"}, {"_id": 0})
    kept_thumb = await isolated_db["db"].media_assets.find_one({"path": "yash-trade/products/imported/shared-thumb.png"}, {"_id": 0})
    kept_active_chunk = await isolated_db["db"].media_assets.find_one({"path": "yash-trade/imports/job-active/chunks/0"}, {"_id": 0})
    kept_done_chunk = await isolated_db["db"].media_assets.find_one({"path": "yash-trade/imports/job-done/chunks/0"}, {"_id": 0})
    orphan = await isolated_db["db"].media_assets.find_one({"path": "yash-trade/products/imported/orphan.png"}, {"_id": 0})

    assert kept_master["deletion_state"] == "retained_reference"
    assert kept_thumb["deletion_state"] == "retained_reference"
    assert kept_active_chunk["deletion_state"] == "retained_reference"
    assert kept_done_chunk["deletion_state"] == "retained_reference"
    assert orphan["deletion_state"] == "blocked_provider_unsupported"
    assert orphan["remote_deleted"] is False


@pytest.mark.asyncio
async def test_corrupt_png_syntaxerror_returns_422(api_client, login_helper, monkeypatch):
    # module: image upload validation maps PIL SyntaxError to 422 INVALID_IMAGE
    token = await _admin_token(login_helper)

    class BrokenImage:
        format = "PNG"
        width = 1
        height = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def verify(self):
            raise SyntaxError("corrupt png stream")

    monkeypatch.setattr(commerce.Image, "open", lambda *_a, **_k: BrokenImage())
    upload = await api_client.post(
        "/api/products/upload-image",
        headers=_auth(token),
        files={"file": ("bad.png", io.BytesIO(b"not-really-png"), "image/png")},
    )
    assert upload.status_code == 422
    body = upload.json()
    if isinstance(body.get("detail"), dict):
        assert body["detail"]["code"] == "INVALID_IMAGE"
    else:
        assert "valid supported image" in str(body.get("detail", ""))


@pytest.mark.asyncio
async def test_media_cache_rechecks_visibility_after_unpublish(api_client, isolated_db, login_helper):
    # module: media cache must re-authorize after visibility change; stale public cache cannot bypass role checks
    media_cache._cache.clear()
    admin = await _admin_token(login_helper)
    customer = (await login_helper("9000000004"))["token"]

    path = "yash-trade/products/manual/cache-recheck.png"
    blob = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=")
    isolated_db["object_store"][path] = (blob, "image/png")
    await isolated_db["db"].media_assets.update_one(
        {"path": path},
        {
            "$set": {
                "path": path,
                "owner_id": "u_admin",
                "content_type": "image/png",
                "size_bytes": len(blob),
                "sha256": c.digest(blob.hex()),
                "purpose": "manual_master",
                "write_state": "stored",
                "updated_at": c.stamp(),
            },
            "$setOnInsert": {"created_at": c.stamp()},
        },
        upsert=True,
    )
    create = await api_client.post(
        "/api/products",
        headers=_auth(admin),
        json={
            "product_code": "TEST-CACHE-001",
            "title": "TEST Cache Product",
            "metal_type": "silver",
            "category": "payal",
            "images": [f"/api/files/{path}"],
            "visibility": "all",
        },
    )
    assert create.status_code == 200, create.text

    warm = await api_client.get(f"/api/files/{path}", headers=_auth(customer))
    assert warm.status_code == 200

    hide = await api_client.put(
        f"/api/products/{create.json()['id']}",
        headers=_auth(admin),
        json={"version": create.json()["version"], "visibility": "hidden"},
    )
    assert hide.status_code == 200

    blocked = await api_client.get(f"/api/files/{path}", headers=_auth(customer))
    assert blocked.status_code == 403
    admin_ok = await api_client.get(f"/api/files/{path}", headers=_auth(admin))
    assert admin_ok.status_code == 200


@pytest.mark.asyncio
async def test_pdf_source_rebuild_after_local_cache_loss(api_client, isolated_db, login_helper):
    # module: source reconstruction rebuilds from retained chunks if local assembled file was removed
    token = await _admin_token(login_helper)
    sample = Path("/app/backend/fixtures/catalog-v1/sample.pdf").read_bytes()
    sha = hashlib.sha256(sample).hexdigest()
    total = (len(sample) + 1024 * 1024 - 1) // (1024 * 1024)

    init = await api_client.post(
        "/api/pdf-upload/init",
        headers=_auth(token),
        json={
            "batch_id": "b1",
            "filename": "sample.pdf",
            "file_size": len(sample),
            "sha256": sha,
            "total_chunks": total,
            "mode": "template_v1",
        },
    )
    assert init.status_code == 200, init.text
    jid = init.json()["upload_id"]

    for idx in range(total):
        part = sample[idx * 1024 * 1024 : (idx + 1) * 1024 * 1024]
        up = await api_client.post(
            f"/api/pdf-upload/{jid}/chunk?chunk_index={idx}",
            headers={**_auth(token), "X-Chunk-Sha256": hashlib.sha256(part).hexdigest()},
            files={"file": (f"chunk-{idx}.bin", part, "application/octet-stream")},
        )
        assert up.status_code == 200, up.text

    job = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0})
    source_1 = await jobs.assemble(job)
    assert source_1.exists()
    source_1.unlink(missing_ok=True)
    source_2 = await jobs.assemble(job)
    assert source_2.exists()
    with source_2.open("rb") as file:
        assert hashlib.file_digest(file, "sha256").hexdigest() == sha


@pytest.mark.asyncio
async def test_chunk_storage_failure_then_retry_isolated(api_client, login_helper, monkeypatch):
    # module: isolated chunk upload simulation where storage fails once and retry succeeds
    token = await _admin_token(login_helper)
    sample = Path("/app/backend/fixtures/catalog-v1/sample.pdf").read_bytes()
    chunk0 = sample[: 1024 * 1024]
    sha = hashlib.sha256(sample).hexdigest()
    init = await api_client.post(
        "/api/pdf-upload/init",
        headers=_auth(token),
        json={
            "batch_id": "b1",
            "filename": "sample.pdf",
            "file_size": len(sample),
            "sha256": sha,
            "total_chunks": (len(sample) + 1024 * 1024 - 1) // (1024 * 1024),
            "mode": "template_v1",
        },
    )
    assert init.status_code == 200
    jid = init.json()["upload_id"]

    original_put = c.put_object
    once = {"failed": False}

    def flaky_put(path, data, content_type):
        if "/chunks/0" in path and not once["failed"]:
            once["failed"] = True
            raise RuntimeError("simulated storage outage")
        return original_put(path, data, content_type)

    monkeypatch.setattr(c, "put_object", flaky_put, raising=False)
    first = await api_client.post(
        f"/api/pdf-upload/{jid}/chunk?chunk_index=0",
        headers={**_auth(token), "X-Chunk-Sha256": hashlib.sha256(chunk0).hexdigest()},
        files={"file": ("chunk-0.bin", chunk0, "application/octet-stream")},
    )
    assert first.status_code == 503

    second = await api_client.post(
        f"/api/pdf-upload/{jid}/chunk?chunk_index=0",
        headers={**_auth(token), "X-Chunk-Sha256": hashlib.sha256(chunk0).hexdigest()},
        files={"file": ("chunk-0.bin", chunk0, "application/octet-stream")},
    )
    assert second.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["encrypted", "truncated"])
async def test_pdf_process_job_safe_errors_for_encrypted_and_truncated(kind, api_client, isolated_db, login_helper):
    # module: parser/worker safe error mapping for encrypted and truncated PDF sources
    token = await _admin_token(login_helper)
    sample = Path("/app/backend/fixtures/catalog-v1/sample.pdf").read_bytes()

    if kind == "encrypted":
        temp = Path("/tmp/iter16-encrypted.pdf")
        with fitz.open(stream=sample, filetype="pdf") as doc:
            doc.save(temp, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
        payload = temp.read_bytes()
    else:
        payload = sample[:-256]

    sha = hashlib.sha256(payload).hexdigest()
    total = (len(payload) + 1024 * 1024 - 1) // (1024 * 1024)
    init = await api_client.post(
        "/api/pdf-upload/init",
        headers=_auth(token),
        json={
            "batch_id": "b1",
            "filename": f"{kind}.pdf",
            "file_size": len(payload),
            "sha256": sha,
            "total_chunks": total,
            "mode": "template_v1",
        },
    )
    assert init.status_code == 200
    jid = init.json()["upload_id"]
    for idx in range(total):
        part = payload[idx * 1024 * 1024 : (idx + 1) * 1024 * 1024]
        up = await api_client.post(
            f"/api/pdf-upload/{jid}/chunk?chunk_index={idx}",
            headers={**_auth(token), "X-Chunk-Sha256": hashlib.sha256(part).hexdigest()},
            files={"file": (f"chunk-{idx}.bin", part, "application/octet-stream")},
        )
        assert up.status_code == 200
    done = await api_client.post(f"/api/pdf-upload/{jid}/complete", headers=_auth(token))
    assert done.status_code == 200

    await isolated_db["db"].import_jobs.update_one(
        {"id": jid},
        {"$set": {"phase": "analyzing", "lease": f"lease-{kind}", "lease_until": c.stamp()}},
    )
    job = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0})
    await jobs.process_job(job)
    latest = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0})
    if kind == "encrypted":
        assert latest["phase"] == "error"
        assert any(
            str(latest.get("error", "")).startswith(prefix)
            for prefix in ("ENCRYPTED_OR_INVALID:", "INVALID_PDF:", "UNSUPPORTED_LAYOUT:", "RENDER_RESOURCE_LIMIT:")
        )
    else:
        # Truncated sources must not crash worker flow; they either fail safely or remain reviewable.
        assert latest["phase"] in {"error", "review"}


@pytest.mark.asyncio
async def test_pdf_authoring_validations_and_owner_photo_gate(api_client, isolated_db, login_helper):
    # module: shared PDF authoring v1 export with labelled fields, duplicate validation, and owner-only photo usage
    token = await _admin_token(login_helper)
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), (220, 180, 90)).save(stream, format="PNG")
    png = stream.getvalue()
    upload = await api_client.post(
        "/api/products/upload-image",
        headers=_auth(token),
        files={"file": ("test.png", png, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    photo_path = upload.json()["storage_path"]

    valid = {
        "product_code": "TEST-AUTH-001",
        "title": "TEST Authoring Product",
        "metal_type": "silver",
        "category": "payal",
        "photo_path": photo_path,
    }
    exported = await api_client.post("/api/pdf-template/export", headers=_auth(token), json={"products": [valid]})
    assert exported.status_code == 200, exported.text
    assert exported.headers.get("content-type", "").startswith("application/pdf")

    dup = await api_client.post(
        "/api/pdf-template/export",
        headers=_auth(token),
        json={"products": [valid, {**valid, "title": "TEST Duplicate"}]},
    )
    assert dup.status_code == 422

    unknown = await api_client.post(
        "/api/pdf-template/export",
        headers=_auth(token),
        json={"products": [{**valid, "unknown_field": "x"}]},
    )
    assert unknown.status_code == 422

    now = c.stamp()
    await isolated_db["db"].users.insert_one(
        {
            "id": "u_admin2",
            "phone": "9999813335",
            "phone_normalized": "9999813335",
            "name": "Second Admin",
            "role": "admin",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "HQ2",
            "location": "Delhi",
        }
    )
    token2 = (await login_helper("9999813335"))["token"]
    foreign = await api_client.post("/api/pdf-template/export", headers=_auth(token2), json={"products": [valid]})
    assert foreign.status_code == 422


@pytest.mark.asyncio
async def test_private_source_preview_and_import_file_block(api_client, isolated_db, login_helper):
    # module: private source preview metadata/png owner-only access and imports path lockout
    token = await _admin_token(login_helper)
    sample = Path("/app/backend/fixtures/catalog-v1/sample.pdf").read_bytes()
    sha = hashlib.sha256(sample).hexdigest()
    init = await api_client.post(
        "/api/pdf-upload/init",
        headers=_auth(token),
        json={
            "batch_id": "b1",
            "filename": "sample.pdf",
            "file_size": len(sample),
            "sha256": sha,
            "total_chunks": (len(sample) + 1024 * 1024 - 1) // (1024 * 1024),
            "mode": "template_v1",
        },
    )
    assert init.status_code == 200, init.text
    jid = init.json()["upload_id"]

    for idx in range((len(sample) + 1024 * 1024 - 1) // (1024 * 1024)):
        part = sample[idx * 1024 * 1024 : (idx + 1) * 1024 * 1024]
        up = await api_client.post(
            f"/api/pdf-upload/{jid}/chunk?chunk_index={idx}",
            headers={**_auth(token), "X-Chunk-Sha256": hashlib.sha256(part).hexdigest()},
            files={"file": (f"chunk-{idx}.bin", part, "application/octet-stream")},
        )
        assert up.status_code == 200, up.text
    complete = await api_client.post(f"/api/pdf-upload/{jid}/complete", headers=_auth(token))
    assert complete.status_code == 200

    await isolated_db["db"].import_jobs.update_one(
        {"id": jid},
        {"$set": {"phase": "analyzing", "lease": "lease-owner", "lease_until": c.stamp()}},
    )
    leased = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0})
    await jobs.process_job(leased)

    meta = await api_client.get(f"/api/pdf-upload/{jid}/pages/1/image?metadata=true", headers=_auth(token))
    assert meta.status_code == 200
    assert meta.json()["rotation"] == 0

    now = c.stamp()
    await isolated_db["db"].users.insert_one(
        {
            "id": "u_admin2",
            "phone": "9999813335",
            "phone_normalized": "9999813335",
            "name": "Second Admin",
            "role": "admin",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "HQ2",
            "location": "Delhi",
        }
    )
    token2 = (await login_helper("9999813335"))["token"]
    forbidden_admin = await api_client.get(f"/api/pdf-upload/{jid}/pages/1/image?metadata=true", headers=_auth(token2))
    assert forbidden_admin.status_code == 403

    customer = (await login_helper("9000000004"))["token"]
    forbidden_customer = await api_client.get(f"/api/pdf-upload/{jid}/pages/1/image", headers=_auth(customer))
    assert forbidden_customer.status_code == 403

    imports_public = await api_client.get(f"/api/files/yash-trade/imports/{jid}/chunks/0", headers=_auth(token))
    assert imports_public.status_code == 404
