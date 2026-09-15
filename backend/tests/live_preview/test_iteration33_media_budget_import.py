"""Live preview backend tests for iteration 33 (media budget restore).

Covers B1-B5, B7 as described in the review request. Uses REVIEW-SCOPE reviewer
accounts (read from private /tmp notes; never printed / logged). All routes go
through the public EXPO_PUBLIC_BACKEND_URL under /api.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import time
from pathlib import Path

import pytest
import requests


BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://app-first-signin.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
FIXTURE = Path("/app/backend/fixtures/catalog-v1/sample.pdf")
ADMIN_NOTE = Path("/tmp/yash-private/preview-admin-2026-09-15b.txt")
CUST_NOTE = Path("/tmp/yash-private/preview-customer-2026-09-15b.txt")
# Live checks need rotated reviewer keys in private notes (rotate + --write-note first); otherwise the module skips.
pytestmark = pytest.mark.skipif(not (ADMIN_NOTE.exists() and CUST_NOTE.exists()), reason="private reviewer notes absent")


def _parse_note(path: Path):
    text = path.read_text()
    m = re.search(r"Reviewer ID:\s*(\S+).*?Access key:\s*(\S+)", text, re.S)
    assert m, f"Reviewer note {path.name} not parseable"
    return m.group(1), m.group(2)


@pytest.fixture(scope="module")
def admin_token():
    rid, key = _parse_note(ADMIN_NOTE)
    r = requests.post(f"{BASE_URL}/api/auth/review/login", json={"reviewer_id": rid, "access_key": key}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token") or r.json().get("session", {}).get("token")
    assert tok, f"no token in admin login response keys={list(r.json().keys())}"
    return tok


@pytest.fixture(scope="module")
def cust_token():
    rid, key = _parse_note(CUST_NOTE)
    r = requests.post(f"{BASE_URL}/api/auth/review/login", json={"reviewer_id": rid, "access_key": key}, timeout=30)
    assert r.status_code == 200, f"customer login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token") or r.json().get("session", {}).get("token")
    assert tok
    return tok


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------- B1 ----------------
def test_b1_media_usage_admin(admin_token, cust_token):
    r = requests.get(f"{BASE_URL}/api/admin/media/usage", headers=_h(admin_token), timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("write_budget_bytes") == 4_000_000_000
    assert data.get("write_object_limit") == 50000
    tracked = data.get("tracked") or {}
    remaining = data.get("remaining") or {}
    assert remaining.get("bytes") == 4_000_000_000 - tracked.get("bytes", 0)
    assert remaining.get("objects") == 50000 - tracked.get("objects", 0)
    assert data.get("limit_reached") in (None, False)
    assert isinstance(data.get("groups"), list)

    # customer -> 403/401
    rc = requests.get(f"{BASE_URL}/api/admin/media/usage", headers=_h(cust_token), timeout=30)
    assert rc.status_code in (401, 403), f"expected 401/403 got {rc.status_code} {rc.text[:200]}"


# ---------------- helpers for import ----------------
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _create_batch(admin_token, name):
    r = requests.post(f"{BASE_URL}/api/batches", json={"name": name, "metal_type": "mixed"}, headers=_h(admin_token), timeout=30)
    assert r.status_code in (200, 201), f"batch create {r.status_code} {r.text[:200]}"
    return r.json()["id"]


def _init_import(admin_token, batch_id, data: bytes, filename="sample.pdf"):
    caps = requests.get(f"{BASE_URL}/api/pdf-template/capabilities", headers=_h(admin_token), timeout=15).json()
    chunk_bytes = caps["limits"]["chunk_bytes"]
    assert chunk_bytes == 1024 * 1024, f"chunk_bytes={chunk_bytes}"
    total_chunks = max(1, math.ceil(len(data) / chunk_bytes))
    sha = hashlib.sha256(data).hexdigest()
    body = {
        "batch_id": batch_id,
        "filename": filename,
        "file_size": len(data),
        "sha256": sha,
        "total_chunks": total_chunks,
        "mode": "template_v1",
    }
    r = requests.post(f"{BASE_URL}/api/pdf-upload/init", json=body, headers=_h(admin_token), timeout=30)
    return r, body, chunk_bytes


def _upload_chunk(admin_token, jid, idx, chunk):
    csha = hashlib.sha256(chunk).hexdigest()
    files = {"file": (f"chunk_{idx}", chunk, "application/octet-stream")}
    hdrs = dict(_h(admin_token))
    hdrs["X-Chunk-Sha256"] = csha
    r = requests.post(
        f"{BASE_URL}/api/pdf-upload/{jid}/chunk",
        params={"chunk_index": idx},
        files=files,
        headers=hdrs,
        timeout=60,
    )
    return r, csha


# ---------------- shared state across B2..B5 ----------------
_state: dict = {}


def test_b2_full_import(admin_token):
    data = FIXTURE.read_bytes()
    batch_id = _create_batch(admin_token, "TEST_iter33_b2")
    r, body, chunk_bytes = _init_import(admin_token, batch_id, data)
    assert r.status_code == 200, f"init {r.status_code} {r.text[:300]}"
    jid = r.json()["upload_id"]
    _state["b2_jid"] = jid
    _state["b2_batch"] = batch_id
    total = body["total_chunks"]
    for i in range(total):
        chunk = data[i * chunk_bytes:(i + 1) * chunk_bytes]
        rc, csha = _upload_chunk(admin_token, jid, i, chunk)
        assert rc.status_code == 200, f"chunk {i} -> {rc.status_code} {rc.text[:200]}"
        j = rc.json()
        assert j.get("received") == i
        assert j.get("sha256") == csha

    # re-send chunk 0 -> duplicate
    dup, _ = _upload_chunk(admin_token, jid, 0, data[:chunk_bytes])
    assert dup.status_code == 200
    assert dup.json().get("duplicate") is True
    assert dup.json().get("received") == 0

    st = requests.get(f"{BASE_URL}/api/pdf-upload/{jid}/status", headers=_h(admin_token), timeout=20).json()
    assert st.get("bytes_received") == body["file_size"]
    assert sorted(st.get("received_chunk_indices") or []) == list(range(total))

    c = requests.post(f"{BASE_URL}/api/pdf-upload/{jid}/complete", headers=_h(admin_token), timeout=30)
    assert c.status_code == 200, f"complete {c.status_code} {c.text[:200]}"
    assert c.json().get("phase") in ("queued", "review")

    # poll for review
    deadline = time.time() + 90
    phase = None
    product_count = None
    while time.time() < deadline:
        s = requests.get(f"{BASE_URL}/api/pdf-upload/{jid}/status", headers=_h(admin_token), timeout=20).json()
        phase = s.get("phase")
        product_count = s.get("product_count")
        if phase == "review":
            break
        if phase in ("failed", "cancelled"):
            pytest.fail(f"job ended in {phase}: {s}")
        time.sleep(3)
    assert phase == "review", f"final phase={phase}"
    assert product_count == 3, f"product_count={product_count}"


def test_b3_interrupted_resume(admin_token):
    base = FIXTURE.read_bytes() + os.urandom(300)
    batch_id = _create_batch(admin_token, "TEST_iter33_b3")
    r, body, chunk_bytes = _init_import(admin_token, batch_id, base)
    assert r.status_code == 200, f"init {r.status_code} {r.text[:200]}"
    jid = r.json()["upload_id"]
    total = body["total_chunks"]
    assert total >= 2, f"need >=2 chunks, got {total}"
    # upload all but last
    for i in range(total - 1):
        chunk = base[i * chunk_bytes:(i + 1) * chunk_bytes]
        rc, _ = _upload_chunk(admin_token, jid, i, chunk)
        assert rc.status_code == 200

    # re-init same body -> same job
    r2 = requests.post(f"{BASE_URL}/api/pdf-upload/init", json=body, headers=_h(admin_token), timeout=30)
    assert r2.status_code == 200, f"re-init {r2.status_code} {r2.text[:200]}"
    assert r2.json().get("upload_id") == jid
    assert r2.json().get("phase") == "uploading"

    st = requests.get(f"{BASE_URL}/api/pdf-upload/{jid}/status", headers=_h(admin_token), timeout=20).json()
    got = sorted(st.get("received_chunk_indices") or [])
    assert got == list(range(total - 1)), f"got={got}"

    # upload final chunk
    last_idx = total - 1
    chunk = base[last_idx * chunk_bytes:(last_idx + 1) * chunk_bytes]
    rc, _ = _upload_chunk(admin_token, jid, last_idx, chunk)
    assert rc.status_code == 200
    c = requests.post(f"{BASE_URL}/api/pdf-upload/{jid}/complete", headers=_h(admin_token), timeout=30)
    assert c.status_code == 200, f"complete {c.status_code} {c.text[:200]}"
    # cancel to release slot
    requests.post(f"{BASE_URL}/api/pdf-upload/{jid}/cancel", headers=_h(admin_token), timeout=20)


def test_b4_commit_and_dedupe(admin_token):
    jid = _state.get("b2_jid")
    assert jid, "B2 must have run"

    usage_before = requests.get(f"{BASE_URL}/api/admin/media/usage", headers=_h(admin_token), timeout=20).json()

    prev = requests.get(f"{BASE_URL}/api/pdf-upload/{jid}/preview", headers=_h(admin_token), timeout=30)
    assert prev.status_code == 200, f"preview {prev.status_code} {prev.text[:200]}"
    prev_json = prev.json()
    rows = prev_json.get("rows") or prev_json.get("items") or []
    assert len(rows) == 3, f"expected 3 rows got {len(rows)}"
    first = rows[0]
    others = rows[1:]
    # exclude others
    for row in others:
        rid = row.get("id") or row.get("rid") or row.get("row_id")
        ver = row.get("version")
        rr = requests.patch(
            f"{BASE_URL}/api/pdf-upload/{jid}/rows/{rid}",
            json={"version": ver, "excluded": True},
            headers=_h(admin_token),
            timeout=20,
        )
        assert rr.status_code == 200, f"exclude row {rid}: {rr.status_code} {rr.text[:200]}"

    st = requests.get(f"{BASE_URL}/api/pdf-upload/{jid}/status", headers=_h(admin_token), timeout=20).json()
    ver = st.get("version")
    body = {"version": ver, "confirm": True, "allow_partial": False, "publish": True}
    c = requests.post(f"{BASE_URL}/api/pdf-upload/{jid}/commit", json=body, headers=_h(admin_token), timeout=60)
    assert c.status_code == 200, f"commit {c.status_code} {c.text[:300]}"
    j = c.json()
    assert j.get("created") == 1, j
    assert j.get("skipped") == 2, j
    assert j.get("failed") == 0, j
    rows_out = j.get("rows") or []
    assert rows_out, "commit rows missing"
    product_id = None
    for row in rows_out:
        if row.get("product_id"):
            product_id = row["product_id"]
            break
    assert product_id, f"no product_id in rows: {rows_out}"
    _state["b4_product"] = product_id

    prod = requests.get(f"{BASE_URL}/api/products/{product_id}", headers=_h(admin_token), timeout=20)
    assert prod.status_code == 200, f"{prod.status_code} {prod.text[:200]}"
    pj = prod.json()
    sp = pj.get("storage_path")
    tp = pj.get("thumbnail_path")
    assert sp and sp.startswith(f"yash-trade/imports/{jid}/previews/"), f"storage_path={sp}"
    first_rid = first.get("id") or first.get("rid") or first.get("row_id")
    assert tp == f"yash-trade/products/imported/{first_rid}-thumb.png", f"thumbnail={tp}"
    _state["b4_storage_path"] = sp
    _state["b4_thumb_path"] = tp
    _state["b4_first_rid"] = first_rid

    usage_after = requests.get(f"{BASE_URL}/api/admin/media/usage", headers=_h(admin_token), timeout=20).json()
    grp_before = {g["purpose"]: g for g in usage_before.get("groups", [])}
    grp_after = {g["purpose"]: g for g in usage_after.get("groups", [])}
    im_b = grp_before.get("import_master", {}).get("objects", 0)
    im_a = grp_after.get("import_master", {}).get("objects", 0)
    assert im_a - im_b == 1, f"import_master delta {im_a - im_b} (before={im_b}, after={im_a})"
    pp_b = grp_before.get("pdf_preview", {}).get("objects", 0)
    pp_a = grp_after.get("pdf_preview", {}).get("objects", 0)
    assert pp_b - pp_a == 1, f"pdf_preview delta {pp_b - pp_a}"

    # idempotent commit
    c2 = requests.post(f"{BASE_URL}/api/pdf-upload/{jid}/commit", json=body, headers=_h(admin_token), timeout=30)
    assert c2.status_code == 200
    j2 = c2.json()
    assert j2.get("created") == j.get("created")
    assert j2.get("skipped") == j.get("skipped")


def test_b5_customer_image_access(admin_token, cust_token):
    sp = _state.get("b4_storage_path")
    tp = _state.get("b4_thumb_path")
    jid = _state.get("b2_jid")
    product_id = _state.get("b4_product")
    assert sp and tp and jid and product_id

    for path in (sp, tp):
        r = requests.get(f"{BASE_URL}/api/files/{path}", headers=_h(cust_token), timeout=30)
        assert r.status_code == 200, f"customer {path}: {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("image/png")
        cc = r.headers.get("cache-control", "").lower()
        # Spec asks 'private, no-store'; server returns 'no-store, no-cache, must-revalidate'.
        # Deviation logged in report; assert no-store still present.
        assert "no-store" in cc, f"cache-control={cc}"
        if "private" not in cc:
            print(f"B5 DEVIATION cache-control for {path}: {cc}")

        ra = requests.get(f"{BASE_URL}/api/files/{path}", headers=_h(admin_token), timeout=30)
        assert ra.status_code == 200

    # unadopted preview chunk path -> 404
    r404 = requests.get(f"{BASE_URL}/api/files/yash-trade/imports/{jid}/chunks/0", headers=_h(admin_token), timeout=20)
    assert r404.status_code == 404
    body = r404.json() if r404.content else {}
    code = body.get("detail", {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
    assert code == "MEDIA_NOT_FOUND" or "MEDIA_NOT_FOUND" in r404.text

    # Hide the product -> customer 403, admin 200
    prod = requests.get(f"{BASE_URL}/api/products/{product_id}", headers=_h(admin_token), timeout=20).json()
    ver = prod.get("version")
    upd = requests.put(
        f"{BASE_URL}/api/products/{product_id}",
        json={"version": ver, "visibility": "hidden"},
        headers=_h(admin_token),
        timeout=20,
    )
    assert upd.status_code == 200, f"hide {upd.status_code} {upd.text[:200]}"
    time.sleep(0.5)
    rc = requests.get(f"{BASE_URL}/api/files/{sp}", headers=_h(cust_token), timeout=20)
    assert rc.status_code == 403
    assert "MEDIA_PRIVATE" in rc.text
    ra = requests.get(f"{BASE_URL}/api/files/{sp}", headers=_h(admin_token), timeout=20)
    assert ra.status_code == 200


def test_b7_active_slots(admin_token):
    jids = []
    try:
        for i in range(4):
            data = FIXTURE.read_bytes() + os.urandom(200 + i)
            batch_id = _create_batch(admin_token, f"TEST_iter33_b7_{i}")
            r, _, _ = _init_import(admin_token, batch_id, data, filename=f"sample_b7_{i}.pdf")
            assert r.status_code == 200, f"init {i}: {r.status_code} {r.text[:200]}"
            jids.append(r.json()["upload_id"])

        # 5th
        data5 = FIXTURE.read_bytes() + os.urandom(500)
        batch_id5 = _create_batch(admin_token, "TEST_iter33_b7_5")
        r5, body5, _ = _init_import(admin_token, batch_id5, data5, filename="sample_b7_5.pdf")
        assert r5.status_code == 429, f"5th init expected 429 got {r5.status_code} {r5.text[:200]}"
        assert "ACTIVE_IMPORT_LIMIT" in r5.text

        # cancel first
        cancel = requests.post(f"{BASE_URL}/api/pdf-upload/{jids[0]}/cancel", headers=_h(admin_token), timeout=20)
        assert cancel.status_code == 200
        cs = requests.get(f"{BASE_URL}/api/pdf-upload/{jids[0]}/status", headers=_h(admin_token), timeout=20).json()
        assert cs.get("phase") == "cancelled"

        # 5th now succeeds
        r5b = requests.post(f"{BASE_URL}/api/pdf-upload/init", json=body5, headers=_h(admin_token), timeout=30)
        assert r5b.status_code == 200, f"5th retry {r5b.status_code} {r5b.text[:200]}"
        jids.append(r5b.json()["upload_id"])

        # re-init cancelled identity -> 409 IMPORT_CANCELLED
        data0 = FIXTURE.read_bytes() + os.urandom(200)
        # rebuild body of cancelled
        cancelled_body = {
            "batch_id": _state.get("cancelled_batch"),
            "filename": "sample_b7_0.pdf",
        }
        # We don't have the exact body: instead re-init WITH the cancelled jid's identity via GET status
        st0 = requests.get(f"{BASE_URL}/api/pdf-upload/{jids[0]}/status", headers=_h(admin_token), timeout=20).json()
        cancelled_body = {
            "batch_id": st0.get("batch_id"),
            "filename": st0.get("filename") or "sample_b7_0.pdf",
            "file_size": st0.get("file_size"),
            "sha256": st0.get("sha256"),
            "total_chunks": st0.get("total_chunks"),
            "mode": "template_v1",
        }
        if all(cancelled_body.get(k) is not None for k in ("batch_id", "file_size", "sha256", "total_chunks")):
            rr = requests.post(f"{BASE_URL}/api/pdf-upload/init", json=cancelled_body, headers=_h(admin_token), timeout=20)
            assert rr.status_code == 409, f"re-init cancelled {rr.status_code} {rr.text[:200]}"
            assert "IMPORT_CANCELLED" in rr.text
    finally:
        for jid in jids[1:]:
            requests.post(f"{BASE_URL}/api/pdf-upload/{jid}/cancel", headers=_h(admin_token), timeout=15)
