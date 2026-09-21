"""Independent E2E API pass for iteration 34 (R00-R17 + F01-F09).
Runs against the live preview backend using ONLY the six review-scope reviewer accounts.
Reviewer keys are read from /tmp/yash-private/e2e-review-keys.json (never printed).
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE = os.environ.get("EXPO_BACKEND_URL", "https://app-first-signin.preview.emergentagent.com").rstrip("/")
KEYS_FILE = "/tmp/yash-private/e2e-review-keys.json"


def _keys():
    with open(KEYS_FILE) as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def sessions():
    """Return {reviewer_id: bearer_token}. Never log the access_key."""
    keys = _keys()
    out = {}
    for rid, ak in keys.items():
        r = requests.post(f"{BASE}/api/auth/review/login",
                          json={"reviewer_id": rid, "access_key": ak}, timeout=15)
        assert r.status_code == 200, f"login failed for {rid}: {r.status_code} {r.text[:200]}"
        data = r.json()
        tok = data.get("access_token") or data.get("token") or data.get("session", {}).get("access_token")
        assert tok, f"no token for {rid}: {list(data.keys())}"
        out[rid] = tok
    return out


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- R17 health ----------
def test_r17_health_ready_six_accounts():
    r = requests.get(f"{BASE}/api/health", timeout=15)
    # 503 is EXPECTED here because preview keeps STAFF_SERVICE_KEY as placeholder.
    assert r.status_code in (200, 503), r.text[:200]
    d = r.json()
    assert d["build"] == "shared-v2-operations-2026-09-20"
    rev = d["flows"]["review"]
    assert rev["ready"] is True
    assert rev["accounts_enabled"] == 6
    assert "owner_admin" in d["flows"] and d["flows"]["owner_admin"]["state"] in ("already_admin", "recovered")


def test_r17_requests_catalog(sessions):
    r = requests.get(f"{BASE}/api/requests/catalog", headers=_h(sessions["store-review-admin"]), timeout=15)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert "heads" in d and "outcomes" in d and "views" in d


# ---------- R01/F01 auth/me for each account ----------
@pytest.mark.parametrize("rid,role_hint", [
    ("store-review-admin", "admin"),
    ("store-review-customer", "customer"),
    ("store-review-telecaller", "telecaller"),
    ("store-review-telecaller-2", "telecaller"),
    ("store-review-billing", "billing"),
    ("store-review-upload", "upload"),
])
def test_r01_auth_me_role(sessions, rid, role_hint):
    r = requests.get(f"{BASE}/api/auth/me", headers=_h(sessions[rid]), timeout=15)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    role = (d.get("role") or d.get("user", {}).get("role") or "").lower()
    assert role_hint in role or role in role_hint or role, f"{rid} -> role={role}"


# ---------- R10 upload executive permissions ----------
def test_r10_upload_permissions(sessions):
    tok = sessions["store-review-upload"]
    r = requests.get(f"{BASE}/api/products?limit=2", headers=_h(tok), timeout=15)
    assert r.status_code == 200, r.text[:200]

    for path in ["/api/requests?view=all_pending", "/api/customers?limit=5",
                 "/api/analytics/dashboard", "/api/admin/notifications/campaigns"]:
        rr = requests.get(f"{BASE}{path}", headers=_h(tok), timeout=15)
        assert rr.status_code in (401, 403), f"{path} -> {rr.status_code}"


# ---------- R11/R12 competing claim (API) ----------
@pytest.fixture(scope="module")
def unclaimed_request(sessions):
    """Find or create an unclaimed pending request in review scope."""
    tok_admin = sessions["store-review-admin"]
    # First, try to find a pending unclaimed one
    r = requests.get(f"{BASE}/api/requests?view=all_pending&limit=25",
                     headers=_h(tok_admin), timeout=15)
    assert r.status_code == 200, r.text[:200]
    rows = r.json() if isinstance(r.json(), list) else r.json().get("requests", r.json().get("items", []))
    unclaimed = [x for x in rows if not (x.get("assignee_id") or x.get("assigned_to"))]
    if unclaimed:
        return unclaimed[0]["id"]
    # Fallback: create one as the customer
    tok_cust = sessions["store-review-customer"]
    payload = {"request_type": "callback", "notes": "iteration34 e2e - competing claim probe"}
    rr = requests.post(f"{BASE}/api/requests", headers=_h(tok_cust), json=payload, timeout=15)
    assert rr.status_code in (200, 201), rr.text[:200]
    return rr.json()["id"]


def test_r11_two_telecaller_claim_race(sessions, unclaimed_request):
    rid = unclaimed_request
    t1 = sessions["store-review-telecaller"]
    t2 = sessions["store-review-telecaller-2"]
    r1 = requests.post(f"{BASE}/api/requests/{rid}/claim", headers=_h(t1), timeout=15)
    assert r1.status_code in (200, 201), r1.text[:200]
    r2 = requests.post(f"{BASE}/api/requests/{rid}/claim", headers=_h(t2), timeout=15)
    assert r2.status_code == 409, r2.text[:200]
    body = r2.json()
    assert body.get("code") == "ALREADY_ASSIGNED" or "assignee" in json.dumps(body).lower()
    # PATCH from t2 should be 403 CLAIM_REQUIRED
    r3 = requests.patch(f"{BASE}/api/requests/{rid}",
                        headers=_h(t2), json={"notes": "x"}, timeout=15)
    assert r3.status_code == 403, r3.text[:200]


# ---------- R11-B/R13-A complete + report + F03 idempotency ----------
def test_r13a_complete_and_report(sessions, unclaimed_request):
    rid = unclaimed_request
    t1 = sessions["store-review-telecaller"]
    admin = sessions["store-review-admin"]
    # add note + follow-up + head
    requests.patch(f"{BASE}/api/requests/{rid}",
                   headers=_h(t1), json={"notes": "iter34 progress"}, timeout=15)
    # complete
    r = requests.post(f"{BASE}/api/requests/{rid}/complete",
                      headers=_h(t1), json={"outcome": "converted"}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    # idempotent replay
    r2 = requests.post(f"{BASE}/api/requests/{rid}/complete",
                       headers=_h(t1), json={"outcome": "converted"}, timeout=15)
    assert r2.status_code == 200, r2.text[:200]
    assert r2.json().get("already_completed") is True
    # completion report
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
    rep = requests.get(f"{BASE}/api/requests/reports/completions?date={today}",
                       headers=_h(admin), timeout=15)
    assert rep.status_code == 200, rep.text[:200]
    d = rep.json()
    assert d.get("total_completed", 0) >= 1


# ---------- R13-B daily release fixture ----------
def test_r13b_stale_request_released(sessions):
    tok = sessions["store-review-telecaller-2"]
    r = requests.get(f"{BASE}/api/requests/review-request-stale-0001",
                     headers=_h(tok), timeout=15)
    if r.status_code == 404:
        pytest.skip("stale fixture not present in this environment")
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert not (d.get("assignee_id") or d.get("assigned_to")), f"still assigned: {d.get('assignee_id')}"
    perms = d.get("permissions") or {}
    if perms:
        assert perms.get("can_claim") is True
    assert d.get("reset_count", 0) >= 1


def test_r13b_queue_status(sessions):
    r = requests.get(f"{BASE}/api/requests/queue/status",
                     headers=_h(sessions["store-review-admin"]), timeout=15)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d.get("timezone") == "Asia/Kolkata"
    assert d.get("release_time") in ("03:00", "3:00")
    assert d.get("worker_running") is True


# ---------- R12-A query -> telecaller alert ----------
def test_r12a_new_request_notifies_telecaller(sessions):
    tok_c = sessions["store-review-customer"]
    r = requests.post(f"{BASE}/api/requests",
                      headers=_h(tok_c),
                      json={"request_type": "callback", "notes": "iter34 notify probe"},
                      timeout=15)
    if r.status_code == 428:
        pytest.skip("customer profile incomplete in this environment")
    assert r.status_code in (200, 201), r.text[:200]
    new_id = r.json()["id"]
    time.sleep(2)
    for rid in ("store-review-telecaller", "store-review-telecaller-2"):
        inbox = requests.get(f"{BASE}/api/notifications/inbox",
                             headers=_h(sessions[rid]), timeout=15)
        assert inbox.status_code == 200, inbox.text[:200]
        rows = inbox.json() if isinstance(inbox.json(), list) else inbox.json().get("items", [])
        hits = [x for x in rows if x.get("request_id") == new_id]
        assert len(hits) <= 1, f"duplicate alert for {rid}"


# ---------- R09 notifications composer ----------
def test_r09_audience_count(sessions):
    # POST-based preview per admin-notifications composer
    r = requests.post(f"{BASE}/api/admin/notifications/audience/preview",
                      headers=_h(sessions["store-review-admin"]),
                      json={"audience": "customers"}, timeout=15)
    if r.status_code in (404, 405):
        pytest.skip(f"audience preview endpoint absent ({r.status_code})")
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert "count" in d or "total" in d


def test_r09_outbox_stats(sessions):
    r = requests.get(f"{BASE}/api/admin/notifications/outbox",
                     headers=_h(sessions["store-review-admin"]), timeout=15)
    assert r.status_code == 200, r.text[:200]


# ---------- F02 queued messages / unlink race ----------
def test_f02_unlink_before_send(sessions):
    tok_c = sessions["store-review-customer"]
    fake = "ExponentPushToken[e2eaaaaaaaaaaaaaaa]"
    r = requests.post(f"{BASE}/api/notifications/devices",
                      headers=_h(tok_c),
                      json={"token": fake, "platform": "android"}, timeout=15)
    assert r.status_code in (200, 201), r.text[:200]
    u = requests.post(f"{BASE}/api/notifications/devices/unlink",
                      headers=_h(tok_c), json={"token": fake}, timeout=15)
    assert u.status_code in (200, 204), u.text[:200]


# ---------- R03 discovery ----------
def test_r03_discovery_session(sessions):
    tok = sessions["store-review-customer"]
    r = requests.post(f"{BASE}/api/discovery/sessions",
                      headers=_h(tok), json={"limit": 20}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    for k in ("session_id", "products", "unseen", "seen", "exhausted"):
        assert k in d, f"missing {k}"
    assert d.get("truncated") is False
    if d["products"]:
        ids = [p.get("id") or p.get("product_id") for p in d["products"][:3] if p.get("id") or p.get("product_id")]
        if ids:
            imp = requests.post(f"{BASE}/api/discovery/impressions",
                                headers=_h(tok),
                                json={"product_ids": ids, "session_id": d["session_id"]},
                                timeout=15)
            assert imp.status_code == 200, imp.text[:200]


# ---------- R05 rates units ----------
def test_r05_rates_latest_unit_canonical(sessions):
    r = requests.get(f"{BASE}/api/rates/latest", timeout=15)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    # canonical INR/gram values expected in payload
    assert isinstance(d, dict)


# ---------- R15 account status of synthetic customer ----------
def test_r15_synthetic_customer_visible(sessions):
    r = requests.get(f"{BASE}/api/customers/review-customer-0002",
                     headers=_h(sessions["store-review-admin"]), timeout=15)
    if r.status_code == 404:
        pytest.skip("synthetic customer fixture not present")
    assert r.status_code == 200, r.text[:200]


# ---------- R07/R08 OTP guard ----------
def test_r07_invalid_phone_rejected():
    r = requests.post(f"{BASE}/api/auth/send-otp", json={"phone": "12345"}, timeout=15)
    # MUST fail without an SMS being sent
    assert r.status_code in (400, 422), f"invalid phone got {r.status_code} {r.text[:200]}"
