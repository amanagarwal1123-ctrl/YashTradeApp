"""Controlled follow-up races for reviewed PDF importer (SIMULATED restart/lease scenarios)."""

import asyncio
import hashlib
import io
from datetime import timedelta
from pathlib import Path

import pytest
from pymongo import ReturnDocument

from shared import core as c
from shared import media_lifecycle as lifecycle
from shared import pdf_jobs as jobs


FIXTURE_PDF = Path("/app/backend/fixtures/catalog-v1/sample.pdf")
CHUNK = 1024 * 1024


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def _chunks(data: bytes, size: int = CHUNK):
    return [data[i:i + size] for i in range(0, len(data), size)]


async def _admin_token(login_helper):
    return (await login_helper("9000000000"))["token"]


async def _init_upload(api_client, token: str, pdf: bytes):
    sha = hashlib.sha256(pdf).hexdigest()
    total_chunks = len(_chunks(pdf))
    res = await api_client.post(
        "/api/pdf-upload/init",
        headers=_auth(token),
        json={
            "batch_id": "b1",
            "filename": "sample.pdf",
            "file_size": len(pdf),
            "sha256": sha,
            "total_chunks": total_chunks,
            "mode": "template_v1",
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["upload_id"]


async def _upload_chunk(api_client, token: str, upload_id: str, index: int, payload: bytes):
    return await api_client.post(
        f"/api/pdf-upload/{upload_id}/chunk?chunk_index={index}",
        headers={**_auth(token), "X-Chunk-Sha256": hashlib.sha256(payload).hexdigest()},
        files={"file": (f"chunk-{index}.bin", io.BytesIO(payload), "application/octet-stream")},
    )


async def _review_ready_job(api_client, isolated_db, login_helper):
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    jid = await _init_upload(api_client, token, pdf)
    for i, part in enumerate(_chunks(pdf)):
        r = await _upload_chunk(api_client, token, jid, i, part)
        assert r.status_code == 200, r.text
    done = await api_client.post(f"/api/pdf-upload/{jid}/complete", headers=_auth(token))
    assert done.status_code == 200, done.text
    lease = f"lease-{jid[:8]}"
    await isolated_db["db"].import_jobs.update_one(
        {"id": jid},
        {"$set": {"phase": "analyzing", "lease": lease, "lease_until": c.stamp()}},
    )
    job = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0})
    await jobs.process_job(job)
    latest = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0})
    assert latest["phase"] == "review"
    return token, jid


@pytest.mark.asyncio
async def test_chunk_put_race_single_manifest_entry_and_retry_consistency(api_client, isolated_db, login_helper):
    # module: reviewed PDF chunk upload race semantics + idempotent receipt consistency
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    jid = await _init_upload(api_client, token, pdf)
    chunk0 = _chunks(pdf)[0]

    r1, r2 = await asyncio.gather(
        _upload_chunk(api_client, token, jid, 0, chunk0),
        _upload_chunk(api_client, token, jid, 0, chunk0),
    )
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses in ([200, 200], [200, 409])

    if r1.status_code == 200 and r2.status_code == 200:
        assert (r1.json().get("duplicate") is True) ^ (r2.json().get("duplicate") is True)

    retry = await _upload_chunk(api_client, token, jid, 0, chunk0)
    assert retry.status_code == 200
    assert retry.json().get("duplicate") is True

    job = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0, "manifest": 1, "bytes_received": 1})
    assert list(job["manifest"].keys()) == ["0"]
    assert job["bytes_received"] == len(chunk0)
    assert job["manifest"]["0"]["sha256"] == hashlib.sha256(chunk0).hexdigest()


@pytest.mark.asyncio
async def test_commit_race_same_version_idempotent_result_no_duplicate_products(api_client, isolated_db, login_helper):
    # module: reviewed PDF commit race on same version (exactly one publish outcome per row/SKU)
    token, jid = await _review_ready_job(api_client, isolated_db, login_helper)
    status = await api_client.get(f"/api/pdf-upload/{jid}/status", headers=_auth(token))
    assert status.status_code == 200
    version = status.json()["version"]
    payload = {"version": version, "confirm": True, "allow_partial": False, "publish": False}

    c1, c2 = await asyncio.gather(
        api_client.post(f"/api/pdf-upload/{jid}/commit", headers=_auth(token), json=payload),
        api_client.post(f"/api/pdf-upload/{jid}/commit", headers=_auth(token), json=payload),
    )

    ok = [r for r in (c1, c2) if r.status_code == 200]
    conflicts = [r for r in (c1, c2) if r.status_code == 409]
    assert all(r.status_code in {200, 409} for r in (c1, c2))
    assert len(ok) >= 1
    assert len(conflicts) <= 1
    if len(ok) == 2:
        assert ok[0].json() == ok[1].json()

    retry = await api_client.post(
        f"/api/pdf-upload/{jid}/commit",
        headers=_auth(token),
        json={"version": (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=_auth(token))).json()["version"], "confirm": True, "allow_partial": False, "publish": False},
    )
    assert retry.status_code == 200
    assert retry.json() == ok[0].json()

    products = await isolated_db["db"].products.find({"source_upload_id": jid}, {"_id": 0, "product_code": 1}).to_list(100)
    codes = [p["product_code"] for p in products]
    assert len(codes) == len(set(codes))
    assert len(codes) == 3


@pytest.mark.asyncio
async def test_commit_cancel_race_single_terminal_outcome_and_consistent_publication(api_client, isolated_db, login_helper):
    # module: reviewed PDF commit-vs-cancel lock race (single terminal state, consistent jobs/products)
    token, jid = await _review_ready_job(api_client, isolated_db, login_helper)
    version = (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=_auth(token))).json()["version"]

    commit_task = api_client.post(
        f"/api/pdf-upload/{jid}/commit",
        headers=_auth(token),
        json={"version": version, "confirm": True, "allow_partial": False, "publish": False},
    )
    cancel_task = api_client.post(f"/api/pdf-upload/{jid}/cancel", headers=_auth(token))
    commit_res, cancel_res = await asyncio.gather(commit_task, cancel_task)

    job = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0, "phase": 1})
    products = await isolated_db["db"].products.count_documents({"source_upload_id": jid})
    assert job["phase"] in {"cancelled", "committed"}

    if job["phase"] == "cancelled":
        assert products == 0
        assert commit_res.status_code == 409
        assert cancel_res.status_code == 200
    else:
        assert products == 3
        assert commit_res.status_code == 200
        assert cancel_res.status_code == 409


@pytest.mark.asyncio
async def test_thumbnail_write_failure_then_retry_recovers_exactly_one_product(api_client, isolated_db, login_helper, monkeypatch):
    # module: media write unknown-state during commit, then retry recovery to one complete product variant set
    token, jid = await _review_ready_job(api_client, isolated_db, login_helper)
    rows = await isolated_db["db"].import_rows.find({"job_id": jid}, {"_id": 0, "id": 1}).to_list(10)
    keeper = rows[0]["id"]
    await isolated_db["db"].import_rows.update_many({"job_id": jid, "id": {"$ne": keeper}}, {"$set": {"excluded": True}})

    original_put = c.put_object
    fail_once = {"done": False}

    def fail_thumb_once(path, data, content_type):
        if path.endswith("-thumb.png") and not fail_once["done"]:
            fail_once["done"] = True
            raise RuntimeError("simulated thumbnail provider failure")
        return original_put(path, data, content_type)

    monkeypatch.setattr(c, "put_object", fail_thumb_once, raising=False)

    version = (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=_auth(token))).json()["version"]
    first = await api_client.post(
        f"/api/pdf-upload/{jid}/commit",
        headers=_auth(token),
        json={"version": version, "confirm": True, "allow_partial": False, "publish": False},
    )
    assert first.status_code == 200
    assert first.json()["failed"] == 1
    assert await isolated_db["db"].products.count_documents({"source_upload_id": jid}) == 0

    keeper_row = await isolated_db["db"].import_rows.find_one({"id": keeper}, {"_id": 0, "preview_path": 1})
    master = keeper_row["preview_path"]  # the confirmed preview is adopted as the permanent master (no second copy)
    thumb = f"yash-trade/products/imported/{keeper}-thumb.png"
    master_asset = await isolated_db["db"].media_assets.find_one({"path": master}, {"_id": 0, "write_state": 1, "purpose": 1})
    thumb_asset = await isolated_db["db"].media_assets.find_one({"path": thumb}, {"_id": 0, "write_state": 1})
    assert master_asset and master_asset["write_state"] == "stored" and master_asset["purpose"] == "import_master"
    assert thumb_asset and thumb_asset["write_state"] == "unknown"
    assert await isolated_db["db"].media_assets.count_documents({"path": f"yash-trade/products/imported/{keeper}.png"}) == 0

    monkeypatch.setattr(c, "put_object", original_put, raising=False)
    v2 = (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=_auth(token))).json()["version"]
    second = await api_client.post(
        f"/api/pdf-upload/{jid}/commit",
        headers=_auth(token),
        json={"version": v2, "confirm": True, "allow_partial": False, "publish": False},
    )
    assert second.status_code == 200, second.text
    assert second.json()["failed"] == 0
    assert second.json()["created"] == 1

    products = await isolated_db["db"].products.find({"source_upload_id": jid}, {"_id": 0, "id": 1, "storage_path": 1, "thumbnail_path": 1}).to_list(10)
    assert len(products) == 1
    assert products[0]["storage_path"] == master
    assert products[0]["thumbnail_path"] == thumb

    master_asset2 = await isolated_db["db"].media_assets.find_one({"path": master}, {"_id": 0, "write_state": 1})
    thumb_asset2 = await isolated_db["db"].media_assets.find_one({"path": thumb}, {"_id": 0, "write_state": 1})
    assert master_asset2["write_state"] == "stored"
    assert thumb_asset2["write_state"] == "stored"


@pytest.mark.asyncio
async def test_simulated_expired_lease_checkpoint_recovery_without_row_duplication(api_client, isolated_db, login_helper):
    # module: SIMULATED worker restart harness for expired lease + next_page checkpoint continuity (not process kill/cloud restart)
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    jid = await _init_upload(api_client, token, pdf)
    for i, part in enumerate(_chunks(pdf)):
        r = await _upload_chunk(api_client, token, jid, i, part)
        assert r.status_code == 200
    done = await api_client.post(f"/api/pdf-upload/{jid}/complete", headers=_auth(token))
    assert done.status_code == 200

    stale_lease = "lease-stale"
    stale_until = (c.now() - timedelta(seconds=5)).isoformat()
    await isolated_db["db"].import_jobs.update_one(
        {"id": jid},
        {"$set": {"phase": "analyzing", "lease": stale_lease, "lease_until": stale_until, "next_page": 2, "resume_phase": "analyzing"}},
    )

    job0 = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0})
    source = await jobs.assemble(job0)
    page0 = await jobs.run_parser(source, 1, job0["mode"])
    assert len(page0["rows"]) == 2, "Checkpoint a real products page, not the empty guide"
    for row in page0["rows"]:
        rid = c.digest(f"{jid}:1:{row['block_id']}")[:32]
        path = f"yash-trade/imports/{jid}/previews/{rid}.png"
        await lifecycle.tracked_put(path, Path(row.pop("image_file")).read_bytes(), "image/png", "pdf_preview", job0["owner_id"], jid)
        await isolated_db["db"].import_rows.update_one(
            {"_id": rid},
            {
                "$setOnInsert": {
                    "id": rid,
                    "job_id": jid,
                    **row,
                    "preview_path": path,
                    "version": 0,
                    "excluded": False,
                    "duplicate_policy": "skip",
                }
            },
            upsert=True,
        )

    claimed = await isolated_db["db"].import_jobs.find_one_and_update(
        {
            "$or": [
                {"phase": "queued"},
                {"phase": "analyzing", "lease_until": {"$lt": c.stamp()}},
            ]
        },
        {
            "$set": {
                "phase": "analyzing",
                "lease": "lease-recovered",
                "lease_until": (c.now() + timedelta(seconds=90)).isoformat(),
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    assert claimed is not None
    assert claimed["id"] == jid
    assert claimed["next_page"] == 2
    assert claimed["phase"] == "analyzing"
    assert claimed.get("resume_phase") == "analyzing"

    baseline_rows = await isolated_db["db"].import_rows.count_documents({"job_id": jid})
    await jobs.process_job(claimed)
    latest = await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0, "phase": 1, "next_page": 1, "total_pages": 1})
    assert latest["phase"] == "review"
    assert latest["next_page"] >= 2
    assert latest["total_pages"] >= 1

    all_rows = await isolated_db["db"].import_rows.find({"job_id": jid}, {"_id": 0, "id": 1, "page": 1}).to_list(200)
    assert len(all_rows) == len({r["id"] for r in all_rows})
    assert await isolated_db["db"].import_rows.count_documents({"job_id": jid, "page": 2}) == len(page0["rows"])
    assert baseline_rows == 2
    assert len(all_rows) == 3
