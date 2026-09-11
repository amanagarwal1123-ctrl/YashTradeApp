"""Extended shared tests for reviewed PDF import lifecycle, ownership, and recovery semantics."""

import asyncio
import hashlib
import io
import secrets
from datetime import timedelta
from pathlib import Path

import pytest

from shared import core as c
from shared import pdf_jobs as jobs
from shared.pdf_schema import field_box


FIXTURE_PDF = Path("/app/backend/fixtures/catalog-v1/sample.pdf")
CHUNK = 1024 * 1024


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def _chunks(data: bytes, size: int = CHUNK):
    return [data[i:i + size] for i in range(0, len(data), size)]


async def _admin_token(login_helper):
    return (await login_helper("9999813334"))["token"]


async def _init_upload(api_client, token: str, pdf: bytes, mode: str = "template_v1"):
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
            "mode": mode,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["upload_id"], sha, total_chunks


async def _upload_chunk(api_client, token: str, upload_id: str, index: int, payload: bytes, checksum: str | None = None):
    digest = checksum or hashlib.sha256(payload).hexdigest()
    return await api_client.post(
        f"/api/pdf-upload/{upload_id}/chunk?chunk_index={index}",
        headers={**_auth(token), "X-Chunk-Sha256": digest},
        files={"file": (f"chunk-{index}.bin", io.BytesIO(payload), "application/octet-stream")},
    )


async def _analyze_to_review(isolated_db, upload_id: str):
    lease = f"lease-{secrets.token_hex(8)}"
    await isolated_db["db"].import_jobs.update_one(
        {"id": upload_id},
        {"$set": {"phase": "analyzing", "lease": lease, "lease_until": c.stamp()}},
    )
    job = await isolated_db["db"].import_jobs.find_one({"id": upload_id}, {"_id": 0})
    await jobs.process_job(job)


@pytest.mark.asyncio
async def test_pdf_upload_out_of_order_duplicate_and_checksum_rejection(api_client, login_helper):
    # reviewed PDF upload API: init/chunk integrity and duplicate chunk idempotency
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    upload_id, _, total_chunks = await _init_upload(api_client, token, pdf)
    parts = _chunks(pdf)

    wrong = await _upload_chunk(api_client, token, upload_id, 0, parts[0], checksum="0" * 64)
    assert wrong.status_code == 422

    order = [2, 0, 1, 3] if total_chunks >= 4 else list(range(total_chunks - 1, -1, -1))
    for idx in order:
        r = await _upload_chunk(api_client, token, upload_id, idx, parts[idx])
        assert r.status_code == 200, r.text

    dup = await _upload_chunk(api_client, token, upload_id, order[0], parts[order[0]])
    assert dup.status_code == 200
    assert dup.json().get("duplicate") is True


@pytest.mark.asyncio
async def test_pdf_upload_pause_resume_cancel_and_post_cancel_block(api_client, login_helper):
    # reviewed PDF upload state machine: pause/resume/cancel controls
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    upload_id, _, _ = await _init_upload(api_client, token, pdf)

    paused = await api_client.post(f"/api/pdf-upload/{upload_id}/pause", headers=_auth(token))
    assert paused.status_code == 200
    assert paused.json()["phase"] == "paused"

    resumed = await api_client.post(f"/api/pdf-upload/{upload_id}/resume", headers=_auth(token))
    assert resumed.status_code == 200
    assert resumed.json()["phase"] == "uploading"

    cancelled = await api_client.post(f"/api/pdf-upload/{upload_id}/cancel", headers=_auth(token))
    assert cancelled.status_code == 200
    assert cancelled.json()["phase"] == "cancelled"

    part = _chunks(pdf)[0]
    blocked = await _upload_chunk(api_client, token, upload_id, 0, part)
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_pdf_owner_authorization_enforced(api_client, isolated_db, seeded_users, login_helper):
    # reviewed PDF importer ownership: only owning admin can access status
    token1 = await _admin_token(login_helper)
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
    upload_id, _, _ = await _init_upload(api_client, token1, FIXTURE_PDF.read_bytes())

    forbidden = await api_client.get(f"/api/pdf-upload/{upload_id}/status", headers=_auth(token2))
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_pdf_complete_analyze_preview_crop_rejection_and_stale_commit_version(
    api_client, isolated_db, login_helper
):
    # reviewed PDF importer flow: complete->analyze->preview + crop validation + stale commit guard
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    upload_id, _, _ = await _init_upload(api_client, token, pdf)

    for i, part in enumerate(_chunks(pdf)):
        r = await _upload_chunk(api_client, token, upload_id, i, part)
        assert r.status_code == 200

    done = await api_client.post(f"/api/pdf-upload/{upload_id}/complete", headers=_auth(token))
    assert done.status_code == 200
    assert done.json()["phase"] in {"queued", "analyzing", "review"}

    await _analyze_to_review(isolated_db, upload_id)

    preview = await api_client.get(f"/api/pdf-upload/{upload_id}/preview?page=1&limit=10", headers=_auth(token))
    assert preview.status_code == 200, preview.text
    rows = preview.json()["rows"]
    assert len(rows) >= 3
    row = rows[0]

    text_box = field_box(row["slot"])
    bad_crop = await api_client.patch(
        f"/api/pdf-upload/{upload_id}/rows/{row['id']}",
        headers=_auth(token),
        json={"version": row["version"], "crop_points": text_box},
    )
    assert bad_crop.status_code == 422

    stale = await api_client.post(
        f"/api/pdf-upload/{upload_id}/commit",
        headers=_auth(token),
        json={"version": 9999, "confirm": True, "allow_partial": False, "publish": False},
    )
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_pdf_commit_invalid_rows_partial_then_recoverable_recommit(api_client, isolated_db, login_helper):
    # reviewed PDF commit: invalid row handling, partial commit, and stable repeat commit
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    upload_id, _, _ = await _init_upload(api_client, token, pdf)
    for i, part in enumerate(_chunks(pdf)):
        await _upload_chunk(api_client, token, upload_id, i, part)
    await api_client.post(f"/api/pdf-upload/{upload_id}/complete", headers=_auth(token))
    await _analyze_to_review(isolated_db, upload_id)

    preview = await api_client.get(f"/api/pdf-upload/{upload_id}/preview?page=1&limit=10", headers=_auth(token))
    rows = preview.json()["rows"]
    victim = rows[0]

    invalidate = await api_client.patch(
        f"/api/pdf-upload/{upload_id}/rows/{victim['id']}",
        headers=_auth(token),
        json={"version": victim["version"], "fields": {"product_code": ""}},
    )
    assert invalidate.status_code == 200

    job = await api_client.get(f"/api/pdf-upload/{upload_id}/status", headers=_auth(token))
    strict_commit = await api_client.post(
        f"/api/pdf-upload/{upload_id}/commit",
        headers=_auth(token),
        json={"version": job.json()["version"], "confirm": True, "allow_partial": False, "publish": False},
    )
    assert strict_commit.status_code == 409

    job2 = await api_client.get(f"/api/pdf-upload/{upload_id}/status", headers=_auth(token))
    partial_commit = await api_client.post(
        f"/api/pdf-upload/{upload_id}/commit",
        headers=_auth(token),
        json={"version": job2.json()["version"], "confirm": True, "allow_partial": True, "publish": False},
    )
    assert partial_commit.status_code == 200, partial_commit.text
    result = partial_commit.json()
    assert result["failed"] >= 1

    # Fix the invalid row, then commit again; previously failed row should remain recoverable.
    refreshed = await api_client.get(f"/api/pdf-upload/{upload_id}/preview?page=1&limit=10", headers=_auth(token))
    bad = next(r for r in refreshed.json()["rows"] if r["id"] == victim["id"])
    fixed = await api_client.patch(
        f"/api/pdf-upload/{upload_id}/rows/{bad['id']}",
        headers=_auth(token),
        json={"version": bad["version"], "fields": {"product_code": "TEST-RECOVER-001", "title": "Recovered", "metal_type": "silver", "category": "payal"}},
    )
    assert fixed.status_code == 200

    job3 = await api_client.get(f"/api/pdf-upload/{upload_id}/status", headers=_auth(token))
    final_commit = await api_client.post(
        f"/api/pdf-upload/{upload_id}/commit",
        headers=_auth(token),
        json={"version": job3.json()["version"], "confirm": True, "allow_partial": True, "publish": False},
    )
    assert final_commit.status_code == 200
    second = await api_client.post(
        f"/api/pdf-upload/{upload_id}/commit",
        headers=_auth(token),
        json={"version": (await api_client.get(f"/api/pdf-upload/{upload_id}/status", headers=_auth(token))).json()["version"], "confirm": True, "allow_partial": True, "publish": False},
    )
    assert second.status_code == 200


@pytest.mark.asyncio
async def test_pdf_checkpoint_resume_process_job_from_next_page(api_client, isolated_db, login_helper):
    # parser worker checkpointing: resume from next_page without reprocessing prior pages
    token = await _admin_token(login_helper)
    pdf = FIXTURE_PDF.read_bytes()
    upload_id, _, _ = await _init_upload(api_client, token, pdf)
    for i, part in enumerate(_chunks(pdf)):
        await _upload_chunk(api_client, token, upload_id, i, part)
    await api_client.post(f"/api/pdf-upload/{upload_id}/complete", headers=_auth(token))

    lease = "lease-checkpoint"
    await isolated_db["db"].import_jobs.update_one({"id": upload_id}, {"$set": {
        "phase": "error", "error": "Temporary storage interruption", "resume_phase": "uploading", "next_page": 2}})
    retried = await api_client.post(f"/api/pdf-upload/{upload_id}/resume", headers=_auth(token))
    assert retried.status_code == 200
    assert retried.json()["phase"] == "queued"
    assert retried.json()["error"] is None
    await isolated_db["db"].import_jobs.update_one(
        {"id": upload_id},
        {"$set": {"phase": "analyzing", "lease": lease, "lease_until": c.stamp(), "next_page": 2}},
    )
    job = await isolated_db["db"].import_jobs.find_one({"id": upload_id}, {"_id": 0})
    await jobs.process_job(job)

    status = await api_client.get(f"/api/pdf-upload/{upload_id}/status", headers=_auth(token))
    assert status.status_code == 200
    assert status.json()["phase"] == "review"
    assert status.json()["pages_processed"] >= 2


@pytest.mark.asyncio
async def test_claim_race_with_asyncio_gather(api_client, isolated_db, login_helper):
    # query ledger race: concurrent claim should allow exactly one claimer
    now = c.stamp()
    await isolated_db["db"].requests.insert_one(
        {
            "id": "race-gather-1",
            "request_type": "callback",
            "status": "pending",
            "user_id": "u_cust1",
            "user_name": "Customer One",
            "user_phone": "9000000004",
            "user_city": "Delhi",
            "shop_name": "Shop One",
            "assignee_id": "",
            "assigned_to": "",
            "created_at": now,
            "updated_at": now,
            "pending_since": now,
            "version": 0,
            "events": [{"id": "e-race-gather", "type": "creation", "actor_id": "u_cust1", "actor_role": "customer", "timestamp": now, "status": "pending"}],
        }
    )
    tele1 = (await login_helper("9000000001"))["token"]
    tele2 = (await login_helper("9000000002"))["token"]

    r1, r2 = await asyncio.gather(
        api_client.post("/api/requests/race-gather-1/claim", headers=_auth(tele1)),
        api_client.post("/api/requests/race-gather-1/claim", headers=_auth(tele2)),
    )
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 409]


@pytest.mark.asyncio
async def test_phone_change_success_revokes_sessions_and_delete_blocks_reenroll(
    api_client, isolated_db, login_helper, monkeypatch
):
    # auth + deletion: successful phone change revokes, deletion tombstone blocks reenrollment
    monkeypatch.setenv("ENROLLMENT_INTEGRATION_KEY", "integration-key-1234567890-abcdef")
    token = (await login_helper("9000000004"))["token"]

    req = await api_client.post(
        "/api/auth/phone-change/request",
        headers=_auth(token),
        json={"new_phone": "9000000017"},
    )
    assert req.status_code == 200, req.text
    otp = isolated_db["sent_otps"][("9000000017", "phone_change")]

    verify = await api_client.post(
        "/api/auth/phone-change/verify",
        headers=_auth(token),
        json={"new_phone": "9000000017", "otp": otp, "challenge_id": req.json()["challenge_id"]},
    )
    assert verify.status_code == 200, verify.text

    me = await api_client.get("/api/auth/me", headers=_auth(token))
    assert me.status_code == 401

    await isolated_db["db"].otp_challenges.update_many(
        {"phone": "9000000017"},
        {"$set": {"created_at": c.now() - timedelta(seconds=61)}},
    )
    relogin = await login_helper("9000000017")
    new_token = relogin["token"]
    await isolated_db["db"].otp_challenges.update_many(
        {"phone": "9000000017"},
        {"$set": {"created_at": c.now() - timedelta(seconds=61)}},
    )
    delete_req = await api_client.post("/api/auth/delete-account/request", headers=_auth(new_token))
    assert delete_req.status_code == 200
    d_otp = isolated_db["sent_otps"][("9000000017", "account_deletion")]
    deleted = await api_client.post(
        "/api/auth/delete-account/confirm",
        headers=_auth(new_token),
        json={"otp": d_otp, "challenge_id": delete_req.json()["challenge_id"]},
    )
    assert deleted.status_code == 200

    # Re-enroll of deleted identity must be blocked by tombstone.
    send = await api_client.post(
        "/api/auth/send-otp",
        headers={"X-Integration-Key": "integration-key-1234567890-abcdef"},
        json={"phone": "9000000017", "purpose": "enrollment", "channel": "mobile"},
    )
    assert send.status_code == 409


@pytest.mark.asyncio
async def test_billing_cannot_write_request_mutations(api_client, isolated_db, login_helper):
    # role guard: billing is read-only for request mutation endpoints
    now = c.stamp()
    await isolated_db["db"].requests.insert_one(
        {
            "id": "billing-readonly-1",
            "request_type": "callback",
            "status": "pending",
            "user_id": "u_cust1",
            "user_name": "Customer One",
            "user_phone": "9000000004",
            "user_city": "Delhi",
            "shop_name": "Shop One",
            "assignee_id": "",
            "assigned_to": "",
            "created_at": now,
            "updated_at": now,
            "pending_since": now,
            "version": 0,
            "events": [{"id": "e-bill", "type": "creation", "actor_id": "u_cust1", "actor_role": "customer", "timestamp": now, "status": "pending"}],
        }
    )
    bill = (await login_helper("9000000003"))["token"]
    denied = await api_client.patch(
        "/api/requests/billing-readonly-1",
        headers=_auth(bill),
        json={"action": "update", "status": "in_progress", "version": 0},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_requests_visible_to_staff_roles_over_200_customer_created(api_client, isolated_db, login_helper):
    # staff listing: high-volume customer-created requests readable by admin/telecaller/billing
    now = c.stamp()
    rows = []
    for i in range(220):
        rows.append(
            {
                "id": f"vis-{i}",
                "request_type": "ask_price",
                "status": "pending",
                "user_id": "u_cust1",
                "user_name": "Customer One",
                "user_phone": "9000000004",
                "user_city": "Delhi",
                "shop_name": "Shop One",
                "assignee_id": "",
                "assigned_to": "",
                "created_at": now,
                "updated_at": now,
                "pending_since": now,
                "version": 0,
                "events": [{"id": f"e-vis-{i}", "type": "creation", "actor_id": "u_cust1", "actor_role": "customer", "timestamp": now, "status": "pending"}],
            }
        )
    await isolated_db["db"].requests.insert_many(rows)

    admin = (await login_helper("9999813334"))["token"]
    tele = (await login_helper("9000000001"))["token"]
    bill = (await login_helper("9000000003"))["token"]

    for token in (admin, tele, bill):
        listing = await api_client.get("/api/requests?page=1&limit=100&view=all", headers=_auth(token))
        assert listing.status_code == 200
        assert listing.json()["total"] >= 220
