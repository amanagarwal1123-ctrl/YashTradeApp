"""Iteration 29 live-preview RETEST (backend only) of iteration 28's two findings:
    B4-retest: review-scope deletion path converges required_acknowledgements=['website'] on
               DEL-review-customer-0001 (the previously-legacy row) and status 'pending';
               review__deletion_requests carries no phone/name; unprefixed counts unchanged;
               re-login recreates profile.
    B3-retest: /api/admin/review/status with a reviewer (customer) bearer -> 403 with
               code 'REVIEW_SCOPE_FORBIDDEN'; anonymous -> 401 AUTH_REQUIRED.
Startup reconciliation proof: neither review__integration_outbox nor integration_outbox has
any account_erased row still listing sms_provider/ai_provider in required_acknowledgements.
"""
import json
import pathlib
import re

import pytest
import requests
from pymongo import MongoClient

BASE = "https://yash-review-deploy.preview.emergentagent.com".rstrip("/")
KEY_FILE = "/tmp/yash-private/preview-review-access-2026-09-14.txt"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "jewellers_app"
UNPREFIXED = ["users", "requests", "sms_log", "deletion_requests", "integration_outbox"]


def _read_key():
    for line in pathlib.Path(KEY_FILE).read_text().splitlines():
        m = re.search(r"Reviewer ID:\s*store-review-customer\s+.*Access key:\s*(\S+)", line)
        if m:
            return m.group(1)
    raise RuntimeError("reviewer key not found")


@pytest.fixture(scope="module")
def rev_key():
    return _read_key()


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


def _login(rev_key):
    r = requests.post(
        f"{BASE}/api/auth/review/login",
        json={"reviewer_id": "store-review-customer", "access_key": rev_key},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["role"] == "customer"
    assert body["user"].get("review_environment") is True
    return body


# ---------- Startup reconciliation proof (read-only) ----------
def test_reconciliation_no_legacy_ack_review_scope(mongo):
    rows = list(mongo["review__integration_outbox"].find(
        {"type": "account_erased",
         "required_acknowledgements": {"$in": ["sms_provider", "ai_provider"]}},
        {"_id": 0, "id": 1, "required_acknowledgements": 1},
    ))
    assert rows == [], f"legacy review-scope rows still listing sms/ai: {rows}"


def test_reconciliation_no_legacy_ack_unprefixed(mongo):
    rows = list(mongo["integration_outbox"].find(
        {"type": "account_erased",
         "required_acknowledgements": {"$in": ["sms_provider", "ai_provider"]}},
        {"_id": 0, "id": 1, "required_acknowledgements": 1},
    ))
    assert rows == [], f"legacy unprefixed rows still listing sms/ai: {rows}"


# ---------- B3-retest owner-scope forbidden ----------
def test_b3_retest_review_scope_forbidden(rev_key):
    body = _login(rev_key)
    token = body["token"]
    r = requests.get(
        f"{BASE}/api/admin/review/status",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert r.status_code == 403, r.text
    payload = json.dumps(r.json())
    assert "REVIEW_SCOPE_FORBIDDEN" in payload, payload
    assert "PERMISSION_DENIED" not in payload, payload


def test_b3_retest_anonymous_unauthorised():
    r = requests.get(f"{BASE}/api/admin/review/status", timeout=30)
    assert r.status_code == 401, r.text
    payload = json.dumps(r.json())
    assert "AUTH_REQUIRED" in payload, payload


# ---------- B4-retest review-scope deletion converges ----------
def test_b4_retest_deletion_converges(rev_key, mongo):
    # snapshot unprefixed counts before
    before = {c: mongo[c].count_documents({}) for c in UNPREFIXED}

    body = _login(rev_key)
    token = body["token"]
    h = {"Authorization": f"Bearer {token}"}

    req = requests.post(f"{BASE}/api/auth/delete-account/request", headers=h, timeout=30)
    assert req.status_code == 200, req.text
    rq = req.json()
    otp = rq.get("simulated_otp")
    challenge_id = rq.get("challenge_id")
    assert otp and challenge_id, rq

    conf = requests.post(
        f"{BASE}/api/auth/delete-account/confirm",
        json={"otp": otp, "challenge_id": challenge_id},
        headers=h,
        timeout=30,
    )
    assert conf.status_code == 200, conf.text
    b = conf.json()
    assert b["status"] == "external_erasure_pending", b

    # Outbox row: canonical id, ack list is ['website'] exactly, status pending
    ob = mongo["review__integration_outbox"].find_one(
        {"id": "DEL-review-customer-0001"}, {"_id": 0})
    assert ob is not None, "outbox event missing"
    assert ob.get("required_acknowledgements") == ["website"], ob.get("required_acknowledgements")
    assert ob.get("status") == "pending", ob.get("status")
    assert ob.get("type") == "account_erased", ob

    # Deletion request: reference matches, status external_erasure_pending,
    # NO phone/name fields on the row
    dr = mongo["review__deletion_requests"].find_one(
        {"reference": "DEL-review-customer-0001"}, {"_id": 0})
    assert dr is not None, "deletion_requests row missing"
    assert dr.get("status") == "external_erasure_pending", dr.get("status")
    assert "phone" not in dr, f"phone leaked into deletion row: {dr}"
    assert "name" not in dr, f"name leaked into deletion row: {dr}"

    # Unprefixed collections must not have changed at all
    after = {c: mongo[c].count_documents({}) for c in UNPREFIXED}
    assert before == after, (before, after)

    # Re-login recreates the fresh profile
    r2 = requests.post(
        f"{BASE}/api/auth/review/login",
        json={"reviewer_id": "store-review-customer", "access_key": rev_key},
        timeout=30,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("profile_recreated") is True, r2.json()
