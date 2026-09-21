"""Iteration 38 live-preview review-scope E2E (API assertions).

Covers only the API portions of C1-C8 (browser evidence separate).
Reviewer keys are read from /tmp/yash-private/e2e-review-keys.json in code
and are NEVER printed/logged.  Auto-skips when the keys file is missing.
"""

import json
import os
import time
import uuid
from pathlib import Path

import pytest
import requests

BASE = "https://app-first-signin.preview.emergentagent.com"
KEYS_PATH = Path("/tmp/yash-private/e2e-review-keys.json")


@pytest.fixture(scope="module")
def keys():
    if not KEYS_PATH.exists():
        pytest.skip("reviewer keys file missing")
    return json.loads(KEYS_PATH.read_text())


def _login(reviewer_id, access_key):
    r = requests.post(
        f"{BASE}/api/auth/review/login",
        json={"reviewer_id": reviewer_id, "access_key": access_key},
        timeout=15,
    )
    assert r.status_code == 200, f"review login failed {reviewer_id}: {r.status_code}"
    return r.json()


@pytest.fixture(scope="module")
def tokens(keys):
    ids = [
        "store-review-admin",
        "store-review-telecaller",
        "store-review-telecaller-2",
        "store-review-customer",
    ]
    out = {}
    for rid in ids:
        d = _login(rid, keys[rid])
        out[rid] = {"token": d.get("token"), "user": d.get("user", {})}
    return out


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# -------- C1: customer creates request; tele1 claims; tele2 claim 409 -----
@pytest.fixture(scope="module")
def rid(tokens):
    cust_tok = tokens["store-review-customer"]["token"]
    payload = {
        "request_type": "call",
        "notes": f"iter38 C1 request {uuid.uuid4().hex[:8]}",
    }
    r = requests.post(f"{BASE}/api/requests", json=payload, headers=_h(cust_tok), timeout=15)
    assert r.status_code in (200, 201), f"create request {r.status_code}: {r.text}"
    body = r.json()
    rid_ = body.get("id") or body.get("request_id") or body.get("request", {}).get("id")
    assert rid_, f"no id in response: {body}"
    return rid_


def test_c1_claim_race(tokens, rid):
    tele1 = tokens["store-review-telecaller"]["token"]
    tele2 = tokens["store-review-telecaller-2"]["token"]

    # tele1 claims first
    r1 = requests.post(f"{BASE}/api/requests/{rid}/claim", headers=_h(tele1), json={}, timeout=15)
    assert r1.status_code == 200, f"tele1 claim {r1.status_code}: {r1.text}"
    # tele2 claim -> 409
    r2 = requests.post(f"{BASE}/api/requests/{rid}/claim", headers=_h(tele2), json={}, timeout=15)
    assert r2.status_code == 409, f"tele2 claim should be 409, got {r2.status_code}"
    body = r2.json()
    assert "ALREADY_ASSIGNED" in json.dumps(body), f"expected ALREADY_ASSIGNED, got {body}"


# -------- C2: admin reassignment -----------------------------------------
def test_c2_admin_reassignment(tokens, rid):
    admin = tokens["store-review-admin"]["token"]
    cur = requests.get(f"{BASE}/api/requests/{rid}", headers=_h(admin), timeout=15).json()
    payload = {
        "action": "assign",
        "assigned_to": "review-telecaller-0002",
        "reason": "iteration 38 reassignment",
        "version": cur.get("version"),
    }
    r = requests.patch(
        f"{BASE}/api/requests/{rid}", json=payload, headers=_h(admin), timeout=15
    )
    assert r.status_code == 200, f"reassign {r.status_code}: {r.text}"
    detail = r.json()
    assignee = detail.get("assignee_id")
    assert assignee == "review-telecaller-0002", f"assignee={assignee}"


# -------- C3: complete/reopen/complete + report counting -----------------
def _report_total(admin_tok):
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = requests.get(
        f"{BASE}/api/requests/reports/completions?day={today}",
        headers=_h(admin_tok),
        timeout=15,
    )
    assert r.status_code == 200, f"report {r.status_code}: {r.text}"
    return r.json()


def test_c3_complete_reopen_complete(tokens, rid):
    admin = tokens["store-review-admin"]["token"]
    tele2 = tokens["store-review-telecaller-2"]["token"]

    # complete first via /complete endpoint
    cur = requests.get(f"{BASE}/api/requests/{rid}", headers=_h(tele2), timeout=15).json()
    r = requests.post(
        f"{BASE}/api/requests/{rid}/complete",
        json={"outcome": "converted", "version": cur.get("version")},
        headers=_h(tele2),
        timeout=15,
    )
    assert r.status_code == 200, f"complete1 {r.status_code}: {r.text}"

    time.sleep(1)
    before = _report_total(admin)
    total_after_c1 = before.get("total_records") or before.get("total") or before.get("count") or 0

    # reopen (PATCH action=reopen)
    cur = requests.get(f"{BASE}/api/requests/{rid}", headers=_h(admin), timeout=15).json()
    r = requests.patch(
        f"{BASE}/api/requests/{rid}",
        json={
            "action": "reopen",
            "status": "pending",
            "reason": "iteration 38 reopen",
            "version": cur.get("version"),
        },
        headers=_h(admin),
        timeout=15,
    )
    assert r.status_code == 200, f"reopen {r.status_code}: {r.text}"

    time.sleep(1)
    mid = _report_total(admin)
    total_after_reopen = mid.get("total_records") or mid.get("total") or mid.get("count") or 0
    # G02: reopened completion should not be counted
    assert total_after_reopen == total_after_c1 - 1, (
        f"reopen did not decrement count: was {total_after_c1}, now {total_after_reopen}"
    )

    # tele2 re-claims and completes again
    rc = requests.post(f"{BASE}/api/requests/{rid}/claim", headers=_h(tele2), json={}, timeout=15)
    assert rc.status_code == 200, f"reclaim {rc.status_code}: {rc.text}"
    cur = requests.get(f"{BASE}/api/requests/{rid}", headers=_h(tele2), timeout=15).json()
    r = requests.post(
        f"{BASE}/api/requests/{rid}/complete",
        json={"outcome": "converted", "version": cur.get("version")},
        headers=_h(tele2),
        timeout=15,
    )
    assert r.status_code == 200, f"complete2 {r.status_code}: {r.text}"

    time.sleep(1)
    after = _report_total(admin)
    total_after_c2 = after.get("total_records") or after.get("total") or after.get("count") or 0
    assert total_after_c2 == total_after_c1, (
        f"count wrong after second complete: was {total_after_c1}, now {total_after_c2}"
    )

    # completions ledger has >=2 rows (first superseded)
    g = requests.get(f"{BASE}/api/requests/{rid}", headers=_h(admin), timeout=15)
    assert g.status_code == 200
    detail = g.json()
    comps = detail.get("completions") or []
    assert len(comps) >= 2, f"expected >=2 completions rows, got {len(comps)}: {comps}"
    superseded = [c for c in comps if c.get("superseded_at")]
    active = [c for c in comps if not c.get("superseded_at")]
    assert superseded and active, f"expected one superseded and one active, got: {comps}"


# -------- C5: staff disable/enable ---------------------------------------
def test_c5_disable_enable_telecaller(tokens):
    admin = tokens["store-review-admin"]["token"]
    tele2_tok = tokens["store-review-telecaller-2"]["token"]

    # disable via legacy DELETE
    r = requests.delete(
        f"{BASE}/api/executives/review-telecaller-0002",
        headers=_h(admin),
        timeout=15,
    )
    if r.status_code == 404:
        r = requests.delete(
            f"{BASE}/api/integrations/staff/review-telecaller-0002",
            headers=_h(admin),
            timeout=15,
        )
    assert r.status_code in (200, 204), f"disable {r.status_code}: {r.text}"

    time.sleep(2)
    # tele2 bearer -> 401
    me = requests.get(f"{BASE}/api/auth/me", headers=_h(tele2_tok), timeout=15)
    assert me.status_code == 401, f"disabled tele2 /me should 401, got {me.status_code}"

    # re-enable via PATCH account_status=active
    r = requests.patch(
        f"{BASE}/api/integrations/staff/review-telecaller-0002",
        json={"account_status": "active"},
        headers=_h(admin),
        timeout=15,
    )
    if r.status_code == 404:
        r = requests.put(
            f"{BASE}/api/executives/review-telecaller-0002",
            json={"account_status": "active"},
            headers=_h(admin),
            timeout=15,
        )
    assert r.status_code in (200, 204), f"enable {r.status_code}: {r.text}"


# -------- C6: discovery session -----------------------------------------
def test_c6_discovery_session(tokens):
    cust = tokens["store-review-customer"]["token"]
    r = requests.post(
        f"{BASE}/api/discovery/sessions",
        json={},
        headers=_h(cust),
        timeout=15,
    )
    assert r.status_code == 200, f"discovery sessions {r.status_code}: {r.text}"
    body = r.json()
    for k in ("session_id", "products"):
        assert k in body, f"missing key {k} in {list(body.keys())}"


# -------- C8: G01 session isolation via /auth/me -------------------------
def test_c8_session_isolation(tokens, keys):
    # Login customer -> capture id
    cust = _login("store-review-customer", keys["store-review-customer"])
    r = requests.get(f"{BASE}/api/auth/me", headers=_h(cust["token"]), timeout=15)
    assert r.status_code == 200 and r.json().get("id") == "review-customer-0001"

    # Login telecaller (separate) -> different id
    tele = _login("store-review-telecaller", keys["store-review-telecaller"])
    r = requests.get(f"{BASE}/api/auth/me", headers=_h(tele["token"]), timeout=15)
    assert r.status_code == 200 and r.json().get("id") == "review-telecaller-0001"
    # Different tokens
    assert cust["token"] != tele["token"]
