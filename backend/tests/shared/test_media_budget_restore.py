"""Restoring uploads under the media write budget: limit reporting, atomic budget under concurrent writes,
identical-rewrite reuse, interrupted/resumed imports without duplicate objects, adopted preview as the customer-visible
master, and release of active import slots."""

import asyncio
import hashlib
import io
import time
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

from shared import core as c
from shared import media_lifecycle as lifecycle
from shared import pdf_jobs as jobs

FIXTURE_PDF = Path("/app/backend/fixtures/catalog-v1/sample.pdf")
CHUNK = 1024 * 1024


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _chunks(data, size=CHUNK):
    return [data[i:i + size] for i in range(0, len(data), size)]


async def _admin_token(login_helper):
    return (await login_helper("9999813334"))["token"]


async def _init(api_client, token, pdf, batch_id="b1", filename="sample.pdf"):
    return await api_client.post("/api/pdf-upload/init", headers=_auth(token), json={
        "batch_id": batch_id, "filename": filename, "file_size": len(pdf), "sha256": hashlib.sha256(pdf).hexdigest(),
        "total_chunks": len(_chunks(pdf)), "mode": "template_v1"})


async def _chunk(api_client, token, jid, index, payload):
    return await api_client.post(f"/api/pdf-upload/{jid}/chunk?chunk_index={index}",
        headers={**_auth(token), "X-Chunk-Sha256": hashlib.sha256(payload).hexdigest()},
        files={"file": (f"chunk-{index}.bin", io.BytesIO(payload), "application/octet-stream")})


async def _analyze(isolated_db, jid):
    await isolated_db["db"].import_jobs.update_one({"id": jid}, {"$set": {"phase": "analyzing", "lease": "lease-test", "lease_until": c.stamp()}})
    await jobs.process_job(await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0}))
    return await isolated_db["db"].import_jobs.find_one({"id": jid}, {"_id": 0})


def _count_puts(monkeypatch):
    calls = []
    original = c.put_object

    def counting(path, data, content_type):
        calls.append(path)
        return original(path, data, content_type)

    monkeypatch.setattr(c, "put_object", counting, raising=False)
    return calls


@pytest.mark.asyncio
async def test_budget_error_names_limit_usage_and_configured_value(api_client, isolated_db, login_helper, monkeypatch):
    monkeypatch.setenv("MEDIA_WRITE_BUDGET_BYTES", "100")
    monkeypatch.setenv("MEDIA_WRITE_OBJECT_LIMIT", "5")
    token = await _admin_token(login_helper)
    await isolated_db["db"].media_assets.insert_one({"path": "yash-trade/products/manual/existing.png", "size_bytes": 81,
        "sha256": "0" * 64, "purpose": "manual_master", "write_state": "stored", "created_at": c.stamp(), "updated_at": c.stamp()})

    with pytest.raises(HTTPException) as err:
        await lifecycle.tracked_put("yash-trade/products/manual/too-big.png", b"x" * 25, "image/png", "manual_master", "u_admin")
    body = err.value.detail
    assert err.value.status_code == 413 and body["code"] == "MEDIA_WRITE_BUDGET"
    assert body["limit"] == "MEDIA_WRITE_BUDGET_BYTES" and body["used"] == 81 and body["requested"] == 25 and body["configured"] == 100
    assert "MEDIA_WRITE_BUDGET_BYTES=100" in body["detail"] and "81 tracked bytes" in body["detail"]
    assert await isolated_db["db"].media_assets.count_documents({}) == 1, "a refused write records nothing"

    monkeypatch.setenv("MEDIA_WRITE_BUDGET_BYTES", "1000000")
    monkeypatch.setenv("MEDIA_WRITE_OBJECT_LIMIT", "1")
    with pytest.raises(HTTPException) as err2:
        await lifecycle.tracked_put("yash-trade/products/manual/one-more.png", b"y", "image/png", "manual_master", "u_admin")
    assert err2.value.detail["limit"] == "MEDIA_WRITE_OBJECT_LIMIT" and err2.value.detail["used"] == 1 and err2.value.detail["configured"] == 1
    # Overwriting an existing path is not a new object: the object limit does not refuse it.
    await lifecycle.tracked_put("yash-trade/products/manual/existing.png", b"z" * 10, "image/png", "manual_master", "u_admin")

    usage = await api_client.get("/api/admin/media/usage", headers=_auth(token))
    assert usage.status_code == 200, usage.text
    data = usage.json()
    assert data["limit_reached"] == "MEDIA_WRITE_OBJECT_LIMIT"
    assert data["remaining"] == {"bytes": 1000000 - 10, "objects": 0}
    assert data["write_budget_bytes"] == 1000000 and data["write_object_limit"] == 1

    # The HTTP surface (admin photo upload) carries the same structured body.
    monkeypatch.setenv("MEDIA_WRITE_BUDGET_BYTES", "10")
    monkeypatch.setenv("MEDIA_WRITE_OBJECT_LIMIT", "100")
    from PIL import Image
    buffer = io.BytesIO(); Image.new("RGB", (64, 64), "white").save(buffer, "JPEG")
    res = await api_client.post("/api/products/upload-image", headers=_auth(token), files={"file": ("p.jpg", buffer.getvalue(), "image/jpeg")})
    assert res.status_code == 413, res.text
    assert res.json()["code"] == "MEDIA_WRITE_BUDGET" and res.json()["limit"] == "MEDIA_WRITE_BUDGET_BYTES"
    assert "MEDIA_WRITE_BUDGET_BYTES=10" in res.json()["detail"]


@pytest.mark.asyncio
async def test_concurrent_writes_run_in_parallel_without_lock_collisions_and_budget_stays_atomic(isolated_db, monkeypatch):
    monkeypatch.setenv("MEDIA_WRITE_BUDGET_BYTES", "1000000")
    monkeypatch.setenv("MEDIA_WRITE_OBJECT_LIMIT", "1000")
    original = c.put_object

    def slow_put(path, data, content_type):
        time.sleep(0.5)  # a real transfer; must not serialise every other writer behind the budget lock
        return original(path, data, content_type)

    monkeypatch.setattr(c, "put_object", slow_put, raising=False)
    started = time.monotonic()
    results = await asyncio.gather(*[lifecycle.tracked_put(f"yash-trade/imports/j1/previews/{i}.png", bytes([i]) * 10, "image/png",
        "pdf_preview", "u_admin", "j1") for i in range(4)], return_exceptions=True)
    elapsed = time.monotonic() - started
    assert all(isinstance(r, dict) for r in results), results  # no 409 OPERATION_IN_PROGRESS between simultaneous writers
    assert elapsed < 1.5, f"writes were serialised behind the lock: {elapsed:.2f}s"
    assert await isolated_db["db"].media_assets.count_documents({"write_state": "stored"}) == 4

    # Atomic enforcement: six simultaneous 10-byte writes against 30 remaining bytes admit exactly three.
    monkeypatch.setattr(c, "put_object", original, raising=False)
    monkeypatch.setenv("MEDIA_WRITE_BUDGET_BYTES", str(40 + 30))
    outcomes = await asyncio.gather(*[lifecycle.tracked_put(f"yash-trade/products/manual/c{i}.png", bytes([i]) * 10, "image/png",
        "manual_master", "u_admin") for i in range(6)], return_exceptions=True)
    ok = [o for o in outcomes if isinstance(o, dict)]
    refused = [o for o in outcomes if isinstance(o, HTTPException)]
    assert len(ok) == 3 and len(refused) == 3, outcomes
    assert all(o.status_code == 413 and o.detail["limit"] == "MEDIA_WRITE_BUDGET_BYTES" for o in refused)
    totals = await lifecycle.usage_totals()
    assert totals == {"bytes": 70, "objects": 7}


@pytest.mark.asyncio
async def test_identical_rewrite_reused_only_when_confirmed_stored(isolated_db, monkeypatch):
    calls = _count_puts(monkeypatch)
    path = "yash-trade/imports/j2/chunks/0"
    first = await lifecycle.tracked_put(path, b"same-bytes", "application/octet-stream", "pdf_chunk", "u_admin", "j2")
    second = await lifecycle.tracked_put(path, b"same-bytes", "application/octet-stream", "pdf_chunk", "u_admin", "j2")
    assert first.get("reused") is None and second["reused"] is True
    assert calls == [path], "confirmed identical object is not written twice"
    assert (await lifecycle.usage_totals()) == {"bytes": 10, "objects": 1}

    # An uncertain outcome is never trusted: it is rewritten and reconciled to 'stored'.
    await isolated_db["db"].media_assets.update_one({"path": path}, {"$set": {"write_state": "unknown", "last_error": "Timeout"}})
    third = await lifecycle.tracked_put(path, b"same-bytes", "application/octet-stream", "pdf_chunk", "u_admin", "j2")
    assert third.get("reused") is None and calls == [path, path]
    asset = await isolated_db["db"].media_assets.find_one({"path": path}, {"_id": 0})
    assert asset["write_state"] == "stored" and asset["size_bytes"] == 10
    assert (await lifecycle.usage_totals()) == {"bytes": 10, "objects": 1}

    # Different bytes on the same path are a real overwrite: written, and the ledger follows the new size.
    await lifecycle.tracked_put(path, b"different-bytes!", "application/octet-stream", "pdf_chunk", "u_admin", "j2")
    assert len(calls) == 3
    assert (await lifecycle.usage_totals()) == {"bytes": 16, "objects": 1}


@pytest.mark.asyncio
async def test_interrupted_upload_resumes_without_duplicates_and_adopted_master_serves_customers(api_client, isolated_db, login_helper, monkeypatch):
    calls = _count_puts(monkeypatch)
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    parts = _chunks(pdf)
    assert len(parts) >= 2, "fixture must span several chunks to exercise resume"
    jid = (await _init(api_client, token, pdf)).json()["upload_id"]
    for i in range(len(parts) - 1):
        assert (await _chunk(api_client, token, jid, i, parts[i])).status_code == 200

    # Interruption: the client restarts, re-initialises the same file and asks which chunks were acknowledged.
    again = await _init(api_client, token, pdf)
    assert again.status_code == 200 and again.json()["upload_id"] == jid and again.json()["phase"] == "uploading"
    status = (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=_auth(token))).json()
    assert status["received_chunk_indices"] == list(range(len(parts) - 1))
    puts_before = len(calls)
    dup = await _chunk(api_client, token, jid, 0, parts[0])
    assert dup.status_code == 200 and dup.json()["duplicate"] is True
    assert len(calls) == puts_before, "an acknowledged chunk is not stored again"

    # Interruption between the storage write and the manifest acknowledgement: the object is stored, the manifest is not.
    last = len(parts) - 1
    await lifecycle.tracked_put(f"yash-trade/imports/{jid}/chunks/{last}", parts[last], "application/octet-stream", "pdf_chunk", "u_admin", jid)
    puts_before = len(calls)
    resumed = await _chunk(api_client, token, jid, last, parts[last])
    assert resumed.status_code == 200 and resumed.json().get("duplicate") is None
    assert len(calls) == puts_before, "the confirmed identical chunk was reused instead of re-written"
    status = (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=_auth(token))).json()
    assert status["bytes_received"] == len(pdf) and status["received_chunk_indices"] == list(range(len(parts)))
    assert await isolated_db["db"].media_assets.count_documents({"purpose": "pdf_chunk", "job_id": jid}) == len(parts)
    assert (await api_client.post(f"/api/pdf-upload/{jid}/complete", headers=_auth(token))).status_code == 200

    job = await _analyze(isolated_db, jid)
    assert job["phase"] == "review"
    rows = await isolated_db["db"].import_rows.find({"job_id": jid}, {"_id": 0}).to_list(20)
    keeper, excluded = rows[0], rows[1]
    await isolated_db["db"].import_rows.update_many({"job_id": jid, "id": {"$ne": keeper["id"]}}, {"$set": {"excluded": True}})
    previews_before = await isolated_db["db"].media_assets.count_documents({"purpose": "pdf_preview"})

    version = (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=_auth(token))).json()["version"]
    commit = await api_client.post(f"/api/pdf-upload/{jid}/commit", headers=_auth(token),
        json={"version": version, "confirm": True, "allow_partial": False, "publish": False})
    assert commit.status_code == 200 and commit.json()["created"] == 1, commit.text
    product = await isolated_db["db"].products.find_one({"source_upload_id": jid}, {"_id": 0})
    assert product["storage_path"] == keeper["preview_path"], "the confirmed preview is the permanent master"
    assert product["thumbnail_path"] == f"yash-trade/products/imported/{keeper['id']}-thumb.png"
    assert await isolated_db["db"].media_assets.count_documents({"path": f"yash-trade/products/imported/{keeper['id']}.png"}) == 0
    assert f"yash-trade/products/imported/{keeper['id']}.png" not in calls, "no second copy of identical bytes"
    master_asset = await isolated_db["db"].media_assets.find_one({"path": product["storage_path"]}, {"_id": 0})
    assert master_asset["purpose"] == "import_master" and master_asset["permanent"] is True and master_asset["adopted_from"] == "pdf_preview"
    assert await isolated_db["db"].media_assets.count_documents({"purpose": "pdf_preview"}) == previews_before - 1

    # Hidden draft: only administrators may read the adopted master; customers and anonymous readers may not.
    admin_read = await api_client.get(f"/api/files/{product['storage_path']}", headers=_auth(token))
    assert admin_read.status_code == 200 and admin_read.headers["content-type"].startswith("image/png")
    customer = (await login_helper("9000000004"))["token"]
    assert (await api_client.get(f"/api/files/{product['storage_path']}", headers=_auth(customer))).status_code == 403
    assert (await api_client.get(f"/api/files/{product['storage_path']}")).status_code in {401, 403}

    # Published: customers read master and thumbnail through the ordinary media route.
    await isolated_db["db"].products.update_one({"id": product["id"]}, {"$set": {"visibility": "all"}})
    for path in (product["storage_path"], product["thumbnail_path"]):
        public = await api_client.get(f"/api/files/{path}")
        assert public.status_code == 200 and public.headers["content-type"].startswith("image/png"), path
        assert public.headers["cache-control"] == "private, max-age=86400" and public.headers["etag"]
    assert (await api_client.get(f"/api/files/{product['storage_path']}", headers=_auth(customer))).status_code == 200
    # Previews nobody adopted, and source chunks, stay behind the owner-bound job routes.
    assert (await api_client.get(f"/api/files/{excluded['preview_path']}", headers=_auth(token))).status_code == 404
    assert (await api_client.get(f"/api/files/yash-trade/imports/{jid}/chunks/0", headers=_auth(token))).status_code == 404

    # Lifecycle audit keeps the adopted master as a live reference even after the import is finished.
    old = (c.now() - timedelta(days=30)).isoformat()
    await isolated_db["db"].media_assets.update_many({"job_id": jid}, {"$set": {"created_at": old}})
    await lifecycle.audit_candidates()
    audited = await isolated_db["db"].media_assets.find_one({"path": product["storage_path"]}, {"_id": 0, "deletion_state": 1, "remote_deleted": 1})
    assert audited["deletion_state"] == "retained_reference" and audited["remote_deleted"] is False

    # Recommitting the finished import is idempotent: no extra products, no extra objects.
    puts_before = len(calls)
    recommit = await api_client.post(f"/api/pdf-upload/{jid}/commit", headers=_auth(token),
        json={"version": version, "confirm": True, "allow_partial": False, "publish": False})
    assert recommit.status_code == 200 and recommit.json() == commit.json()
    assert len(calls) == puts_before and await isolated_db["db"].products.count_documents({"source_upload_id": jid}) == 1


@pytest.mark.asyncio
async def test_uncertain_preview_is_copied_not_adopted(api_client, isolated_db, login_helper, monkeypatch):
    calls = _count_puts(monkeypatch)
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    jid = (await _init(api_client, token, pdf)).json()["upload_id"]
    for i, part in enumerate(_chunks(pdf)):
        assert (await _chunk(api_client, token, jid, i, part)).status_code == 200
    assert (await api_client.post(f"/api/pdf-upload/{jid}/complete", headers=_auth(token))).status_code == 200
    assert (await _analyze(isolated_db, jid))["phase"] == "review"
    rows = await isolated_db["db"].import_rows.find({"job_id": jid}, {"_id": 0}).to_list(20)
    keeper = rows[0]
    await isolated_db["db"].import_rows.update_many({"job_id": jid, "id": {"$ne": keeper["id"]}}, {"$set": {"excluded": True}})
    # The preview's ledger row says the write outcome is unknown: it must not become a permanent master.
    await isolated_db["db"].media_assets.update_one({"path": keeper["preview_path"]}, {"$set": {"write_state": "unknown"}})
    version = (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=_auth(token))).json()["version"]
    commit = await api_client.post(f"/api/pdf-upload/{jid}/commit", headers=_auth(token),
        json={"version": version, "confirm": True, "allow_partial": False, "publish": True})
    assert commit.status_code == 200 and commit.json()["created"] == 1, commit.text
    product = await isolated_db["db"].products.find_one({"source_upload_id": jid}, {"_id": 0})
    assert product["storage_path"] == f"yash-trade/products/imported/{keeper['id']}.png"
    assert product["storage_path"] in calls
    assert (await api_client.get(f"/api/files/{product['storage_path']}")).status_code == 200
    preview_asset = await isolated_db["db"].media_assets.find_one({"path": keeper["preview_path"]}, {"_id": 0, "purpose": 1})
    assert preview_asset["purpose"] == "pdf_preview"


@pytest.mark.asyncio
async def test_active_import_slots_release_on_cancel_and_commit(api_client, isolated_db, login_helper):
    token = await _admin_token(login_helper)
    files = [FIXTURE_PDF.read_bytes() + bytes([i]) * 200 for i in range(6)]  # distinct identities, valid PDF prefix irrelevant here
    ids = []
    for i in range(4):
        res = await _init(api_client, token, files[i], filename=f"file-{i}.pdf")
        assert res.status_code == 200, res.text
        ids.append(res.json()["upload_id"])
    fifth = await _init(api_client, token, files[4], filename="file-4.pdf")
    assert fifth.status_code == 429 and fifth.json()["code"] == "ACTIVE_IMPORT_LIMIT"
    # Re-initialising one of the active imports (resume) is never blocked by the limit.
    assert (await _init(api_client, token, files[0], filename="file-0.pdf")).status_code == 200

    cancelled = await api_client.post(f"/api/pdf-upload/{ids[0]}/cancel", headers=_auth(token))
    assert cancelled.status_code == 200 and cancelled.json()["phase"] == "cancelled"
    fifth = await _init(api_client, token, files[4], filename="file-4.pdf")
    assert fifth.status_code == 200, "a cancelled import releases its slot"
    ids.append(fifth.json()["upload_id"])

    sixth = await _init(api_client, token, files[5], filename="file-5.pdf")
    assert sixth.status_code == 429
    await isolated_db["db"].import_jobs.update_one({"id": ids[1]}, {"$set": {"phase": "committed", "result": {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "rows": []}}})
    sixth = await _init(api_client, token, files[5], filename="file-5.pdf")
    assert sixth.status_code == 200, "a committed import releases its slot"
    # Imports parked in review or paused still hold their slot until finished or cancelled.
    await isolated_db["db"].import_jobs.update_one({"id": ids[2]}, {"$set": {"phase": "review"}})
    await isolated_db["db"].import_jobs.update_one({"id": ids[3]}, {"$set": {"phase": "paused", "resume_phase": "uploading"}})
    blocked = await _init(api_client, token, FIXTURE_PDF.read_bytes() + b"\x07" * 300, filename="file-6.pdf")
    assert blocked.status_code == 429
    active = await isolated_db["db"].import_jobs.count_documents({"owner_id": "u_admin", "phase": {"$in": ["uploading", "queued", "analyzing", "review", "paused"]}})
    assert active == 4
