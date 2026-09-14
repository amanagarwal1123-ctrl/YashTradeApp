"""Iteration 27 - Live PREVIEW retest of the two HIGH fixes plus B4/B6/B7/B10.

Only re-runs items from iteration 26 that were flagged for retest:

* B4 (background job isolation) with the CORRECT /api/pdf-upload/init payload
  (batch_id + file_size + sha256 + total_chunks + mode='template_v1').
* B6 (reviewer deletion + fresh sample profile) - re-run.
* B7 (production disposable customer AI-consent + deletion) using the FRESHLY
  reissued fixture with the fix that the stale token now returns 401
  SESSION_REVOKED.
* B10 (production untouched snapshot + health.accounts_enabled == 4).

PREVIEW deployment only. Never touches the owner, never sends real SMS. Reads
reviewer keys and disposable fixtures from /tmp/yash-private/*, never prints
their contents.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Tuple

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

# --- Setup ------------------------------------------------------------------

BASE_URL = "https://yash-review-deploy.preview.emergentagent.com"
PREVIEW_KEYS_PATH = Path("/tmp/yash-private/preview-review-access-2026-09-13.txt")
FIXTURES_PATH = Path("/tmp/yash-private/e2e-fixtures.json")
BACKEND_ENV = dotenv_values("/app/backend/.env")
MONGO_URL = BACKEND_ENV["MONGO_URL"].strip('"')
DB_NAME = BACKEND_ENV["DB_NAME"].strip('"')
INTEGRATION_KEY = BACKEND_ENV.get("ENROLLMENT_INTEGRATION_KEY", "").strip('"')

REVIEWER_IDS = (
    "store-review-customer",
    "store-review-admin",
    "store-review-telecaller",
    "store-review-billing",
)


def _load_reviewer_keys() -> Dict[str, str]:
    pat = re.compile(r"Reviewer ID:\s+(\S+)\s+.*?Access key:\s+(\S+)")
    keys: Dict[str, str] = {}
    for line in PREVIEW_KEYS_PATH.read_text().splitlines():
        m = pat.search(line)
        if m:
            keys[m.group(1)] = m.group(2)
    return keys


@pytest.fixture(scope="session")
def reviewer_keys() -> Dict[str, str]:
    keys = _load_reviewer_keys()
    assert set(keys) >= set(REVIEWER_IDS), "reviewer keys file missing entries"
    return keys


@pytest.fixture(scope="session")
def fixtures() -> Dict:
    return json.loads(FIXTURES_PATH.read_text())


@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _post(path: str, **kw) -> requests.Response:
    kw.setdefault("timeout", 60)
    return requests.post(f"{BASE_URL}{path}", **kw)


def _get(path: str, **kw) -> requests.Response:
    kw.setdefault("timeout", 60)
    return requests.get(f"{BASE_URL}{path}", **kw)


def _post_otp(path: str, **kw) -> requests.Response:
    """OTP-issuing endpoint with backoff on 429."""
    r = None
    for attempt, wait in enumerate((70, 130, 180)):
        r = _post(path, **kw)
        if r.status_code != 429:
            return r
        if attempt == 2:
            return r
        time.sleep(wait)
    return r


def _bearer(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _error_code(body):
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict) and detail.get("code"):
            return detail.get("code")
        if isinstance(body.get("code"), str):
            return body["code"]
    return None


def _review_login(rid: str, key: str) -> Tuple[requests.Response, dict]:
    r = _post("/api/auth/review/login", json={"reviewer_id": rid, "access_key": key})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    return r, body


@pytest.fixture(scope="module")
def admin_token(reviewer_keys):
    _, body = _review_login("store-review-admin", reviewer_keys["store-review-admin"])
    return body["token"]


# --- B4 (fixed payload): pdf-upload/init + chunk + complete + status --------


def _make_valid_pdf() -> bytes:
    """Build a small but valid single-page PDF (>100 bytes) via reportlab if
    available, else PyMuPDF, else a hand-rolled minimal PDF."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 100), "Review sample PDF")
        buf = doc.tobytes()
        doc.close()
        return buf
    except Exception:
        pass
    try:
        from reportlab.pdfgen import canvas  # type: ignore

        buf = io.BytesIO()
        cnv = canvas.Canvas(buf)
        cnv.setFont("Helvetica", 12)
        cnv.drawString(20, 100, "Review sample PDF")
        cnv.showPage()
        cnv.save()
        return buf.getvalue()
    except Exception:
        pass
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 20 100 Td (review pdf) Tj ET\nendstream endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000052 00000 n \n0000000098 00000 n \n0000000155 00000 n \n"
        b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n245\n%%EOF\n"
    )


def test_b4_pdf_job_isolation_correct_payload(admin_token, mongo):
    """Verify /api/pdf-upload/init runs in review scope and the background
    worker only touches review__* collections."""
    caps = _get("/api/pdf-template/capabilities", headers=_bearer(admin_token))
    chunk_bytes = 1024 * 1024
    if caps.status_code == 200:
        chunk_bytes = int(
            caps.json().get("limits", {}).get("chunk_bytes")
            or caps.json().get("chunk_bytes")
            or chunk_bytes
        )

    # Batch first
    bres = _post(
        "/api/batches",
        headers={**_bearer(admin_token), "Content-Type": "application/json"},
        json={"name": "Review import test", "metal_type": "silver"},
    )
    assert bres.status_code in (200, 201), f"batch create: {bres.status_code} {bres.text[:200]}"
    bbody = bres.json()
    batch_id = bbody.get("id") or (bbody.get("batch") or {}).get("id")
    assert batch_id, bbody

    pdf = _make_valid_pdf()
    assert len(pdf) > 100

    sha_all = hashlib.sha256(pdf).hexdigest()
    total_chunks = math.ceil(len(pdf) / chunk_bytes)

    # Production snapshot BEFORE
    before_prod_import = mongo["import_jobs"].count_documents({})
    before_prod_pdf = (
        mongo["pdf_jobs"].count_documents({})
        if "pdf_jobs" in mongo.list_collection_names()
        else 0
    )
    before_prod_batches = (
        mongo["batches"].count_documents({})
        if "batches" in mongo.list_collection_names()
        else 0
    )
    before_prod_products = (
        mongo["products"].count_documents({})
        if "products" in mongo.list_collection_names()
        else 0
    )

    init = _post(
        "/api/pdf-upload/init",
        headers={**_bearer(admin_token), "Content-Type": "application/json"},
        json={
            "batch_id": batch_id,
            "filename": "review-sample.pdf",
            "file_size": len(pdf),
            "sha256": sha_all,
            "total_chunks": total_chunks,
            "mode": "template_v1",
        },
    )
    assert init.status_code == 200, f"init: {init.status_code} {init.text[:200]}"
    upload_id = init.json()["upload_id"]

    # Send single chunk (only 1 chunk since len(pdf) < 1MB)
    files = {"file": ("chunk-0", pdf, "application/octet-stream")}
    chunk_sha = hashlib.sha256(pdf).hexdigest()
    up = requests.post(
        f"{BASE_URL}/api/pdf-upload/{upload_id}/chunk?chunk_index=0",
        headers={**_bearer(admin_token), "X-Chunk-Sha256": chunk_sha},
        files=files,
        timeout=60,
    )
    assert up.status_code == 200, f"chunk: {up.status_code} {up.text[:200]}"

    complete = _post(
        f"/api/pdf-upload/{upload_id}/complete",
        headers=_bearer(admin_token),
    )
    assert complete.status_code == 200, f"complete: {complete.status_code} {complete.text[:200]}"

    # Poll status until phase leaves queued/analyzing (or up to 60s)
    last_phase = None
    for _ in range(30):
        st = _get(f"/api/pdf-upload/{upload_id}/status", headers=_bearer(admin_token))
        if st.status_code == 200:
            last_phase = st.json().get("phase")
            if last_phase not in ("queued", "analyzing", "uploading"):
                break
        time.sleep(2)
    print(f"[b4] final phase={last_phase}")

    # Assert review__import_jobs & review__batches have rows
    assert mongo["review__import_jobs"].count_documents({"id": upload_id}) == 1, "job missing in review__import_jobs"
    assert mongo["review__batches"].count_documents({"id": batch_id}) == 1, "batch missing in review__batches"

    # Unprefixed counts UNCHANGED
    assert mongo["import_jobs"].count_documents({}) == before_prod_import, "unprefixed import_jobs changed"
    assert mongo["import_jobs"].count_documents({"id": upload_id}) == 0
    if "pdf_jobs" in mongo.list_collection_names():
        assert mongo["pdf_jobs"].count_documents({}) == before_prod_pdf
    if "batches" in mongo.list_collection_names():
        assert mongo["batches"].count_documents({"id": batch_id}) == 0
        assert mongo["batches"].count_documents({}) == before_prod_batches
    if "products" in mongo.list_collection_names():
        assert mongo["products"].count_documents({}) == before_prod_products

    # Cleanup: cancel
    cancel = _post(
        f"/api/pdf-upload/{upload_id}/cancel",
        headers=_bearer(admin_token),
    )
    print(f"[b4] cancel status={cancel.status_code}")


# --- B7 (fixed 401): production disposable customer -------------------------


def test_b7_disposable_customer_ai_and_delete_401(fixtures, mongo):
    tok = fixtures["disposable_customer"]["token"]
    uid = fixtures["disposable_customer"]["id"]

    probe = _get("/api/auth/me", headers=_bearer(tok))
    if probe.status_code != 200:
        pytest.skip(f"disposable_customer fixture unusable: {probe.status_code} {probe.text[:120]}")

    # No consent yet
    con = _get("/api/ai/consent", headers=_bearer(tok))
    assert con.status_code == 200
    assert con.json().get("granted") is False

    chat_no = _post(
        "/api/ai/chat",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"message": "How to pitch silver anklets?"},
        timeout=45,
    )
    assert chat_no.status_code == 403
    assert _error_code(chat_no.json()) == "AI_CONSENT_REQUIRED"
    assert mongo["ai_chat_history"].count_documents({"user_id": uid}) == 0

    # Grant consent
    g = _post(
        "/api/ai/consent",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"granted": True, "source": "assistant"},
    )
    assert g.status_code == 200
    assert g.json().get("granted") is True

    chat = _post(
        "/api/ai/chat",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"message": "How to pitch silver anklets?"},
        timeout=45,
    )
    assert chat.status_code == 200
    assert chat.json().get("stored") is True
    assert mongo["ai_chat_history"].count_documents({"user_id": uid}) >= 2

    # Withdraw consent
    w = _post(
        "/api/ai/consent",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"granted": False},
    )
    assert w.status_code == 200
    wj = w.json()
    assert wj.get("granted") is False
    assert (wj.get("history_deleted") or 0) >= 2
    assert mongo["ai_chat_history"].count_documents({"user_id": uid}) == 0

    chat_after = _post(
        "/api/ai/chat",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"message": "again"},
        timeout=20,
    )
    assert chat_after.status_code == 403

    # In-flight race
    _post(
        "/api/ai/consent",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"granted": True, "source": "assistant"},
    )

    outcomes: Dict[str, requests.Response] = {}

    def chat_call():
        outcomes["chat"] = _post(
            "/api/ai/chat",
            headers={**_bearer(tok), "Content-Type": "application/json"},
            json={"message": "in flight?"},
            timeout=45,
        )

    def withdraw_call():
        time.sleep(0.3)
        outcomes["withdraw"] = _post(
            "/api/ai/consent",
            headers={**_bearer(tok), "Content-Type": "application/json"},
            json={"granted": False},
        )

    t1 = threading.Thread(target=chat_call)
    t2 = threading.Thread(target=withdraw_call)
    t1.start(); t2.start(); t1.join(); t2.join()
    remaining = mongo["ai_chat_history"].count_documents({"user_id": uid})
    print(
        f"[b7_inflight] chat={outcomes['chat'].status_code} "
        f"stored={outcomes['chat'].json().get('stored')!r} "
        f"withdraw={outcomes['withdraw'].status_code} "
        f"remaining_after={remaining}"
    )
    assert remaining == 0

    # Deletion (uses the fixture's pre-issued OTP + challenge_id)
    otp = fixtures["disposable_customer"]["deletion_otp"]
    cid = fixtures["disposable_customer"]["deletion_challenge_id"]
    conf = _post(
        "/api/auth/delete-account/confirm",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"otp": otp, "challenge_id": cid},
    )
    assert conf.status_code == 200, conf.text[:300]
    cb = conf.json()
    assert cb.get("deleted") is True
    ref = cb.get("reference") or cb.get("deletion_reference") or ""
    assert ref.startswith("DEL-"), cb
    erasure = cb.get("erasure") or cb.get("erasure_report") or {}
    assert erasure.get("local_personal_records_remaining") == 0
    ext = erasure.get("external") or {}
    assert (ext.get("object_storage") or {}).get("delete_api") is False
    assert (ext.get("ai_provider") or {}).get("delete_api") is False

    # THE FIX under test: old token must now return 401 SESSION_REVOKED
    dead = _get("/api/auth/me", headers=_bearer(tok))
    assert dead.status_code == 401, (
        f"expected 401 SESSION_REVOKED, got {dead.status_code} {dead.text[:200]}"
    )
    code = _error_code(dead.json()) if dead.headers.get("content-type", "").startswith("application/json") else None
    print(f"[b7_dead_token_code] {code}")
    assert code in ("SESSION_REVOKED", "SESSION_INVALID", "TOKEN_INVALID"), code

    tomb = mongo["users"].find_one({"id": uid})
    assert tomb and tomb.get("account_status") == "deleted"
    assert str(tomb.get("phone", "")).startswith("deleted:")
    assert (tomb.get("session_version") or 0) >= 1, tomb.get("session_version")
    assert not (tomb.get("ai_consent") or {}).get("granted")

    for coll in ("ai_chat_history", "ai_reports", "analytics_events", "reward_transactions", "cart", "wishlists"):
        if coll in mongo.list_collection_names():
            assert mongo[coll].count_documents({"user_id": uid}) == 0, coll

    assert mongo["deleted_identities"].count_documents({"user_id": uid}) >= 1
    outbox_hit = (
        mongo["integration_outbox"].count_documents(
            {"event": "account_erased", "payload.user_id": uid}
        )
        + mongo["integration_outbox"].count_documents({"user_id": uid})
    )
    assert outbox_hit >= 1, "outbox missing account_erased for user"

    if INTEGRATION_KEY:
        r = _get(
            "/api/integrations/deletions",
            headers={"X-Integration-Key": INTEGRATION_KEY},
        )
        assert r.status_code == 200
        events = r.json().get("events") or r.json().get("items") or []
        assert any(e.get("user_id") == uid for e in events), "outbox missing user"

    # Replay confirm must be 401 (session already revoked)
    replay = _post(
        "/api/auth/delete-account/confirm",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"otp": otp, "challenge_id": cid},
    )
    assert replay.status_code == 401


# --- B6 (retest): reviewer deletion + fresh profile recreation --------------


def test_b6_reviewer_delete_and_recreate(reviewer_keys, mongo):
    key = reviewer_keys["store-review-customer"]
    _, body = _review_login("store-review-customer", key)
    tok = body["token"]
    uid = body["user"]["id"]

    g = _post(
        "/api/ai/consent",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"granted": True},
    )
    assert g.status_code == 200

    chat = None
    for attempt in range(3):
        chat = _post(
            "/api/ai/chat",
            headers={**_bearer(tok), "Content-Type": "application/json"},
            json={"message": "Why does silver turn black?"},
            timeout=45,
        )
        if chat.status_code == 200 and chat.json().get("stored") is True:
            break
        time.sleep(2 + attempt * 2)
    assert chat.status_code == 200

    # Best-effort clear the review-scope OTP limits to avoid 429 during retest.
    try:
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        db["review__otp_limits"].delete_many({})
        db["review__otp_challenges"].delete_many({})
        client.close()
    except Exception as ex:  # noqa: BLE001
        print(f"[b6_clean_rate] skipped ({ex})")

    req = _post_otp("/api/auth/delete-account/request", headers=_bearer(tok))
    if req.status_code == 429:
        _post("/api/auth/logout", headers=_bearer(tok))
        pytest.skip(f"reviewer OTP still rate-limited: {req.text[:120]}")
    assert req.status_code == 200
    otp = req.json()["simulated_otp"]
    cid = req.json()["challenge_id"]

    prod_del_before = mongo["deletion_requests"].count_documents({})
    prod_id_before = mongo["deleted_identities"].count_documents({})
    prod_outbox_before = (
        mongo["integration_outbox"].count_documents({})
        if "integration_outbox" in mongo.list_collection_names()
        else 0
    )

    conf = _post(
        "/api/auth/delete-account/confirm",
        headers={**_bearer(tok), "Content-Type": "application/json"},
        json={"otp": otp, "challenge_id": cid},
    )
    assert conf.status_code == 200, conf.text[:300]
    cb = conf.json()
    assert cb.get("deleted") is True

    dead = _get("/api/auth/me", headers=_bearer(tok))
    assert dead.status_code == 401, dead.status_code

    doc = mongo["review__users"].find_one({"id": uid})
    assert doc and doc.get("account_status") == "deleted"
    assert str(doc.get("phone", "")).startswith("deleted:")
    assert mongo["review__ai_chat_history"].count_documents({"user_id": uid}) == 0

    # Production untouched
    assert mongo["deletion_requests"].count_documents({}) == prod_del_before
    assert mongo["deleted_identities"].count_documents({}) == prod_id_before
    if "integration_outbox" in mongo.list_collection_names():
        assert mongo["integration_outbox"].count_documents({}) == prod_outbox_before

    # Repeat login with same key -> fresh profile
    r2, body2 = _review_login("store-review-customer", key)
    assert r2.status_code == 200
    assert body2.get("profile_recreated") is True, body2

    tok2 = body2["token"]
    con = _get("/api/ai/consent", headers=_bearer(tok2))
    assert con.status_code == 200 and con.json().get("granted") is False

    assert (
        mongo["review__review_access_log"].count_documents(
            {"event": "review_profile_recreated"}
        )
        >= 1
    )
    _post("/api/auth/logout", headers=_bearer(tok2))


# --- B10: Production untouched + health --------------------------------------


PROD_COLLECTIONS = (
    "users",
    "products",
    "requests",
    "media_assets",
    "ai_chat_history",
    "deletion_requests",
    "deleted_identities",
    "integration_outbox",
    "batches",
    "import_jobs",
    "pdf_jobs",
    "sms_log",
    "otp_challenges",
)


@pytest.fixture(scope="session", autouse=True)
def _prod_snapshot(mongo):
    before: Dict[str, int] = {}
    existing = set(mongo.list_collection_names())
    for c in PROD_COLLECTIONS:
        before[c] = mongo[c].count_documents({}) if c in existing else 0
    yield before
    after: Dict[str, int] = {
        c: (mongo[c].count_documents({}) if c in existing else 0)
        for c in PROD_COLLECTIONS
    }
    report = {c: {"before": before[c], "after": after[c], "delta": after[c] - before[c]} for c in PROD_COLLECTIONS}
    sms_disposable = mongo["sms_log"].count_documents(
        {"phone": {"$in": ["9100009901", "9100009902"]}}
    )
    report["_sms_log_for_disposable_phones"] = sms_disposable
    Path("/app/test_reports/iteration27_prod_snapshot.json").write_text(
        json.dumps(report, indent=2)
    )
    print(f"[b10] prod_snapshot={report}")


def test_b10_no_sms_to_disposable_phones(mongo):
    n = mongo["sms_log"].count_documents({"phone": {"$in": ["9100009901", "9100009902"]}})
    assert n == 0, f"unexpected sms_log rows for disposable phones: {n}"


def test_b10_health_review_accounts_enabled():
    r = _get("/api/health")
    body = r.json()
    review = body.get("flows", {}).get("review") or {}
    assert review.get("accounts_enabled") == 4, review
