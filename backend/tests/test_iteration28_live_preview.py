"""Iteration 28 live preview: reviewer entry (Login->Help->App review access),
AI consent v2026-09-14 wording, deletion outbox/ttl, assets, and instructions."""
import os
import re
import json
import pathlib
import subprocess
import pytest
import requests
from pymongo import MongoClient

BASE = "https://app-first-signin.preview.emergentagent.com".rstrip("/")
KEY_FILE = "/tmp/yash-private/preview-review-access-2026-09-14.txt"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "jewellers_app"


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
def bearer(rev_key):
    r = requests.post(f"{BASE}/api/auth/review/login",
                      json={"reviewer_id": "store-review-customer", "access_key": rev_key}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["role"] == "customer"
    assert body["user"].get("review_environment") is True
    return body["token"]


# ---------- B1 health ----------
def test_b1_health():
    r = requests.get(f"{BASE}/api/health", timeout=30)
    assert r.status_code == 503
    j = r.json()
    assert j["flows"]["review"]["ready"] is True
    assert j["flows"]["owner_admin"]["state"] == "already_admin"


# ---------- B2 AI consent ----------
def test_b2_consent_shape(bearer):
    r = requests.get(f"{BASE}/api/ai/consent", headers={"Authorization": f"Bearer {bearer}"}, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["current_version"] == "2026-09-14"
    assert j["recipients"][0]["name"] == "Anthropic PBC"
    ds = j["recipients"][0]["data_sent"]
    assert any("choose to write" in x for x in ds), ds
    assert not any("session identifier" in x for x in ds), ds
    dns = j["recipients"][0]["data_not_sent"]
    assert any("not attached automatically" in x for x in dns), dns
    ret = j["recipients"][0].get("retention", "")
    assert "retention period" in ret, ret
    we = j.get("withdrawal_effects", [])
    assert any("provider" in x and "erased" in x for x in we), we


def test_b2_consent_grant_withdraw(bearer):
    h = {"Authorization": f"Bearer {bearer}"}
    r = requests.post(f"{BASE}/api/ai/consent", json={"granted": True, "source": "profile"}, headers=h, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["granted"] is True
    assert j["version"] == "2026-09-14"
    r = requests.post(f"{BASE}/api/ai/consent", json={"granted": False, "source": "profile"}, headers=h, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["granted"] is False
    pc = j.get("provider_copy", "")
    assert pc.startswith("not erased"), pc


def test_b2_chat_gated(bearer):
    h = {"Authorization": f"Bearer {bearer}"}
    r = requests.post(f"{BASE}/api/ai/chat", json={"message": "hi"}, headers=h, timeout=30)
    assert r.status_code == 403
    j = r.json()
    code = j.get("code") or j.get("detail", {}).get("code") if isinstance(j.get("detail"), dict) else j.get("code")
    body = json.dumps(j)
    assert "AI_CONSENT_REQUIRED" in body


# ---------- B3 owner-only + instructions ----------
def test_b3_owner_scope_forbidden(bearer):
    r = requests.get(f"{BASE}/api/admin/review/status", headers={"Authorization": f"Bearer {bearer}"}, timeout=30)
    assert r.status_code == 403
    assert "REVIEW_SCOPE_FORBIDDEN" in r.text


def test_b3_review_seed_texts():
    from shared import review_seed as r
    joined_sign = "\n".join(r.SIGN_IN_STEPS)
    joined_form = "\n".join(r.STORE_FORM_TEXT)
    assert "Help" in joined_sign
    assert "App review access" in joined_sign
    assert "Open reviewer sign-in" in joined_sign
    assert "Store reviewer access" not in joined_sign
    assert "Help" in joined_form
    assert "App review access" in joined_form
    assert "Store reviewer access" not in joined_form


def test_b3_private_note_phrase():
    txt = pathlib.Path(KEY_FILE).read_text()
    assert "tap 'Help' (link under the footer), then 'App review access'" in txt


# ---------- B4 review-scope deletion ----------
def test_b4_deletion_flow_and_outbox(rev_key):
    # fresh login to get a bearer we can burn
    r = requests.post(f"{BASE}/api/auth/review/login",
                      json={"reviewer_id": "store-review-customer", "access_key": rev_key}, timeout=30)
    assert r.status_code == 200
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    # snapshot unprefixed counts before
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    UNPREFIXED = ["users", "requests", "sms_log", "deletion_requests", "integration_outbox"]
    before = {c: db[c].count_documents({}) for c in UNPREFIXED}

    req = requests.post(f"{BASE}/api/auth/delete-account/request", headers=h, timeout=30)
    assert req.status_code == 200, req.text
    rq = req.json()
    otp = rq.get("simulated_otp")
    challenge_id = rq.get("challenge_id")
    assert otp and challenge_id

    conf = requests.post(f"{BASE}/api/auth/delete-account/confirm",
                         json={"otp": otp, "challenge_id": challenge_id}, headers=h, timeout=30)
    assert conf.status_code == 200, conf.text
    body = conf.json()
    assert body["status"] == "external_erasure_pending", body
    er = body["erasure"]
    kb = er["retained_by_app"]
    for k in ("deleted_identities", "deletion_requests", "requests", "integration_outbox"):
        assert k in kb, kb
    assert er["external"]["sms_provider"]["erasure"] == "not_requested"
    assert er["external"]["ai_provider"]["erasure"] == "not_requested"
    assert "pseudonymous" not in er["external"]["ai_provider"].get("detail", "")
    assert "SMS-provider and AI-provider copies are not erased" in body.get("detail", ""), body.get("detail")

    # Mongo checks
    ob = db["review__integration_outbox"].find_one({"id": "DEL-review-customer-0001"})
    assert ob is not None, "outbox event missing"
    assert ob.get("required_acknowledgements") == ["website"], ob.get("required_acknowledgements")
    assert ob.get("status") == "pending", ob.get("status")

    sms_rows = list(db["review__sms_log"].find({}))
    for row in sms_rows:
        assert row.get("expires_at") is not None

    after = {c: db[c].count_documents({}) for c in UNPREFIXED}
    assert before == after, (before, after)

    # re-login recreates fresh profile
    r2 = requests.post(f"{BASE}/api/auth/review/login",
                       json={"reviewer_id": "store-review-customer", "access_key": rev_key}, timeout=30)
    assert r2.status_code == 200
    assert r2.json().get("profile_recreated") is True


# ---------- B5 assets ----------
def test_b5_assets():
    import json as _json
    app_json = _json.loads(pathlib.Path("/app/frontend/app.json").read_text())
    cfg = app_json["expo"]
    fe = pathlib.Path("/app/frontend")
    icon = fe / cfg["icon"]
    android_icon = fe / cfg["android"]["icon"]
    adaptive = fe / cfg["android"]["adaptiveIcon"]["foregroundImage"]
    favicon = fe / cfg["web"]["favicon"]
    splash_entry = next(p for p in cfg["plugins"] if isinstance(p, list) and p[0] == "expo-splash-screen")
    splash = fe / splash_entry[1]["image"]
    for p in (icon, android_icon, adaptive, favicon, splash):
        assert p.exists(), f"missing asset: {p}"

    from PIL import Image
    for p in (icon, android_icon, adaptive, splash):
        img = Image.open(p)
        assert img.size == (1024, 1024), f"{p}: expected 1024x1024, got {img.size}"
    splash_img = Image.open(splash)
    assert splash_img.mode == "RGBA", f"splash mode: {splash_img.mode}"

    # legacy templates removed
    for gone in ("assets/images/react-logo.png", "assets/images/splash-image.png", "assets/images/app-image.png"):
        assert not (fe / gone).exists(), f"stale template still present: {gone}"
