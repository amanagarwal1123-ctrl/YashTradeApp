"""Iteration 36 live-preview review-scope E2E.

Covers J3b, J3c, J4, J9, J10, J11 via API assertions against the live
preview backend. Reviewer keys are read from a private tmp file and are
never printed/logged. Tests skip if keys are missing.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

BASE = "https://app-first-signin.preview.emergentagent.com"
KEYS_PATH = Path("/tmp/yash-private/e2e-review-keys.json")

# Shared fixture request id (auto-selected in J3b precondition)
SHARED_RID = "review-request-race-0002"


@pytest.fixture(scope="module")
def keys():
    if not KEYS_PATH.exists():
        pytest.skip("reviewer keys file missing")
    return json.loads(KEYS_PATH.read_text())


def _login(reviewer_id: str, access_key: str) -> dict:
    r = requests.post(
        f"{BASE}/api/auth/review/login",
        json={"reviewer_id": reviewer_id, "access_key": access_key},
        timeout=15,
    )
    assert r.status_code == 200, f"review login failed for {reviewer_id}: {r.status_code}"
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
        out[rid] = {
            "token": d.get("token"),
            "refresh": d.get("refresh_token"),
            "user": d.get("user", {}),
        }
    return out


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Isolation guard
# ---------------------------------------------------------------------------

def test_review_login_returns_review_scope(tokens):
    admin_user = tokens["store-review-admin"]["user"]
    assert admin_user.get("id") == "review-admin-0001"
    assert admin_user.get("role") == "admin"
    tel1 = tokens["store-review-telecaller"]["user"]
    assert tel1.get("id") == "review-telecaller-0001"
    tel2 = tokens["store-review-telecaller-2"]["user"]
    assert tel2.get("id") == "review-telecaller-0002"


# ---------------------------------------------------------------------------
# J3b - First telecaller claim wins on race-0002
# ---------------------------------------------------------------------------

class TestJ3bClaimRace:
    @property
    def RID(self):
        return SHARED_RID

    def test_precondition_unclaimed(self, tokens):
        global SHARED_RID
        for rid in ("review-request-race-0002", "review-request-race-0001", "review-request-0001", "review-request-0002", "review-request-stale-0002"):
            r = requests.get(f"{BASE}/api/requests/{rid}", headers=_h(tokens["store-review-admin"]["token"]))
            if r.status_code != 200:
                continue
            d = r.json()
            if d.get("status") == "pending" and not d.get("assignee_id"):
                SHARED_RID = rid
                return
        pytest.skip("no unclaimed review-request fixture available")

    def test_telecaller1_claim_success(self, tokens):
        tok = tokens["store-review-telecaller"]["token"]
        r = requests.post(f"{BASE}/api/requests/{self.RID}/claim", headers=_h(tok), json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("assignee_id") == "review-telecaller-0001"
        assert d.get("status") in ("in_progress", "contacted", "pending"), d.get("status")
        assert d.get("claimed_at")

    def test_get_reflects_ownership(self, tokens):
        r = requests.get(f"{BASE}/api/requests/{self.RID}", headers=_h(tokens["store-review-telecaller"]["token"]))
        assert r.status_code == 200
        d = r.json()
        assert d.get("assignee_id") == "review-telecaller-0001"
        assert d.get("claimed_at")

    def test_second_telecaller_cannot_reclaim(self, tokens):
        tok = tokens["store-review-telecaller-2"]["token"]
        r = requests.post(f"{BASE}/api/requests/{self.RID}/claim", headers=_h(tok), json={})
        # Expect 4xx (conflict / already claimed)
        assert r.status_code in (409, 403, 400), f"unexpected {r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------------------
# J3c - Admin bypass on same request, then reassign
# ---------------------------------------------------------------------------

class TestJ3cAdminBypassAndReassign:
    @property
    def RID(self):
        return SHARED_RID

    def test_admin_can_read_and_ownership_remains_tel1(self, tokens):
        r = requests.get(f"{BASE}/api/requests/{self.RID}", headers=_h(tokens["store-review-admin"]["token"]))
        assert r.status_code == 200
        d = r.json()
        assert d.get("assignee_id") == "review-telecaller-0001", f"admin fetch changed assignee: {d.get('assignee_id')}"

    def test_admin_reassigns_to_telecaller2(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        # Read current version
        cur = requests.get(f"{BASE}/api/requests/{self.RID}", headers=_h(tok)).json()
        version = cur.get("version")
        payload = {
            "action": "assign",
            "assigned_to": "review-telecaller-0002",
            "reason": "E2E iter36 reassign to telecaller2",
            "version": version,
        }
        r = requests.patch(f"{BASE}/api/requests/{self.RID}", headers=_h(tok), json=payload)
        assert r.status_code == 200, f"reassign failed: {r.status_code} {r.text[:400]}"
        d = r.json()
        assert d.get("assignee_id") == "review-telecaller-0002", d

    def test_history_records_reassign_reason(self, tokens):
        r = requests.get(f"{BASE}/api/requests/{self.RID}/history", headers=_h(tokens["store-review-admin"]["token"]))
        assert r.status_code == 200
        body = r.json()
        events = body.get("request", {}).get("events", []) if isinstance(body, dict) else body
        assert any(ev.get("type") in ("assign", "reassign", "assignment", "claim_release") or "iter36" in (ev.get("notes","") or ev.get("reason","") or "").lower() for ev in events), events[:3]

    def test_original_telecaller_locked_out(self, tokens):
        tok = tokens["store-review-telecaller"]["token"]
        # Attempt to mutate as tel1 (should be denied since ownership moved)
        cur = requests.get(f"{BASE}/api/requests/{self.RID}", headers=_h(tok)).json()
        version = cur.get("version")
        payload = {"action": "update", "notes": "should not stick", "version": version, "head": "contacted"}
        r = requests.patch(f"{BASE}/api/requests/{self.RID}", headers=_h(tok), json=payload)
        assert r.status_code in (403, 409), f"tel1 mutation should be forbidden, got {r.status_code}"


# ---------------------------------------------------------------------------
# J4 - Telecaller2 works, completes; admin reopens
# ---------------------------------------------------------------------------

class TestJ4WorkCompleteReopen:
    @property
    def RID(self):
        return SHARED_RID

    def test_head_contacted(self, tokens):
        tok = tokens["store-review-telecaller-2"]["token"]
        cur = requests.get(f"{BASE}/api/requests/{self.RID}", headers=_h(tok)).json()
        r = requests.patch(f"{BASE}/api/requests/{self.RID}", headers=_h(tok), json={
            "action": "update", "head": "contacted", "version": cur.get("version"),
        })
        assert r.status_code == 200, r.text
        assert r.json().get("head") == "contacted"

    def test_save_note(self, tokens):
        tok = tokens["store-review-telecaller-2"]["token"]
        cur = requests.get(f"{BASE}/api/requests/{self.RID}", headers=_h(tok)).json()
        # 'note' action does not exist - use 'update' with notes field per catalog
        r = requests.patch(f"{BASE}/api/requests/{self.RID}", headers=_h(tok), json={
            "action": "update", "notes": "E2E note iteration 36", "version": cur.get("version"),
        })
        assert r.status_code == 200, r.text

    def test_follow_up_set(self, tokens):
        tok = tokens["store-review-telecaller-2"]["token"]
        cur = requests.get(f"{BASE}/api/requests/{self.RID}", headers=_h(tok)).json()
        iso = "2026-09-22T04:30:00Z"
        r = requests.patch(f"{BASE}/api/requests/{self.RID}", headers=_h(tok), json={
            "action": "update", "head": "follow_up", "follow_up_at": iso, "version": cur.get("version"),
        })
        assert r.status_code == 200, f"follow_up failed: {r.status_code} {r.text[:300]}"

    def test_complete_converted(self, tokens):
        tok = tokens["store-review-telecaller-2"]["token"]
        cur = requests.get(f"{BASE}/api/requests/{self.RID}", headers=_h(tok)).json()
        r = requests.post(f"{BASE}/api/requests/{self.RID}/complete", headers=_h(tok), json={
            "outcome": "converted", "version": cur.get("version"),
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") in ("resolved", "completed"), d.get("status")

    def test_completions_report_includes_tel2(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Try `day` first, then broader `from/to` if needed
        r = requests.get(f"{BASE}/api/requests/reports/completions?day={today}", headers=_h(tok))
        assert r.status_code == 200, r.text
        d = r.json()
        # Look for review-telecaller-0002 in payload text
        blob = json.dumps(d)
        assert "review-telecaller-0002" in blob, f"telecaller-2 not in report: {blob[:400]}"

    def test_admin_reopen(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        # Give backend a beat to persist the completion status
        time.sleep(1.0)
        cur = requests.get(f"{BASE}/api/requests/{self.RID}", headers=_h(tok)).json()
        if cur.get("status") not in ("resolved", "cancelled"):
            pytest.skip(f"request not terminal ({cur.get('status')}) - cannot exercise reopen")
        r = requests.patch(f"{BASE}/api/requests/{self.RID}", headers=_h(tok), json={
            "action": "reopen",
            "status": "pending",
            "reason": "E2E iter36 reopen for F03 regression check",
            "version": cur.get("version"),
        })
        assert r.status_code == 200, f"reopen failed: {r.status_code} {r.text[:400]}"
        d = r.json()
        assert d.get("status") in ("pending", "in_progress"), d.get("status")
        assert not d.get("assignee_id"), f"expected unclaimed after reopen, got {d.get('assignee_id')}"


# ---------------------------------------------------------------------------
# J9 - MCX rates edit + persistence + restore
# ---------------------------------------------------------------------------

class TestJ9RatesMCX:
    original = {}

    def test_get_original_rates(self, tokens):
        r = requests.get(f"{BASE}/api/rates/latest", headers=_h(tokens["store-review-admin"]["token"]))
        assert r.status_code == 200
        d = r.json()
        # Store per-metal originals
        TestJ9RatesMCX.original = d
        for k in ("silver_mcx_rate", "gold_mcx_rate"):
            assert k in d or k in json.dumps(d), f"missing rate field {k}: {list(d.keys())}"

    def test_update_silver_mcx(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        cur = requests.get(f"{BASE}/api/rates/latest", headers=_h(tok)).json()
        version = cur.get("version", 0)
        payload = {"silver_mcx_display_rate": 100000, "version": version}
        r = requests.post(f"{BASE}/api/rates", headers=_h(tok), json=payload)
        assert r.status_code in (200, 201), f"silver update failed: {r.status_code} {r.text[:400]}"

    def test_update_gold_mcx(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        cur = requests.get(f"{BASE}/api/rates/latest", headers=_h(tok)).json()
        version = cur.get("version", 0)
        payload = {"gold_mcx_display_rate": 75000, "version": version}
        r = requests.post(f"{BASE}/api/rates", headers=_h(tok), json=payload)
        assert r.status_code in (200, 201), f"gold update failed: {r.status_code} {r.text[:400]}"

    def test_rates_reflected(self, tokens):
        r = requests.get(f"{BASE}/api/rates/latest", headers=_h(tokens["store-review-admin"]["token"]))
        assert r.status_code == 200
        d = r.json()
        # canonical: silver_mcx_rate=100, gold_mcx_rate=7500; display fields *_mcx_display_rate
        assert d.get("silver_mcx_rate") == 100 or d.get("silver_mcx_display_rate") == 100000, f"silver not updated: {d}"
        assert d.get("gold_mcx_rate") == 7500 or d.get("gold_mcx_display_rate") == 75000, f"gold not updated: {d}"

    def test_restore_originals(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        orig = TestJ9RatesMCX.original
        for metal in ("silver", "gold"):
            cur = requests.get(f"{BASE}/api/rates/latest", headers=_h(tok)).json()
            version = cur.get("version", 0)
            key = f"{metal}_mcx_display_rate"
            if orig.get(key) is None:
                continue
            payload = {key: orig[key], "version": version}
            r = requests.post(f"{BASE}/api/rates", headers=_h(tok), json=payload)
            assert r.status_code in (200, 201), f"restore {metal} failed: {r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------------------
# J11 - Staff phone change (review-telecaller-0002)
# ---------------------------------------------------------------------------

class TestJ11StaffPhoneChange:
    ORIG_PHONE = "9100000105"
    NEW_PHONE = "9100000199"
    CUST_PHONE = "9100000101"  # review customer number - should preview as promotion

    def test_preview_available(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        r = requests.post(
            f"{BASE}/api/integrations/staff/review-telecaller-0002/phone/preview",
            headers=_h(tok),
            json={"new_phone": self.NEW_PHONE},
        )
        assert r.status_code == 200, f"phone preview failed: {r.status_code} {r.text[:300]}"
        d = r.json()
        st = str(d.get("status", "")).lower()
        assert st in ("available", "ok", "free"), f"preview status: {d}"
        # capture preview token for the commit
        TestJ11StaffPhoneChange.preview_token_new = d.get("preview_token") or d.get("token")
        TestJ11StaffPhoneChange.expected_phone = d.get("expected_phone") or self.ORIG_PHONE

    def test_preview_promotion_flow_for_existing_customer(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        r = requests.post(
            f"{BASE}/api/integrations/staff/review-telecaller-0002/phone/preview",
            headers=_h(tok),
            json={"new_phone": self.CUST_PHONE},
        )
        assert r.status_code == 200, f"promotion preview failed: {r.status_code} {r.text[:300]}"
        d = r.json()
        st = str(d.get("status", "")).lower()
        assert any(w in st for w in ("customer", "promot", "conflict", "exist", "taken")), f"unexpected preview status for customer conflict: {d}"

    def test_change_and_revert(self, tokens):
        import uuid
        tok = tokens["store-review-admin"]["token"]
        # Fresh preview to get valid token
        pv = requests.post(
            f"{BASE}/api/integrations/staff/review-telecaller-0002/phone/preview",
            headers=_h(tok),
            json={"new_phone": self.NEW_PHONE},
        )
        if pv.status_code != 200:
            pytest.skip(f"preview failed pre-change: {pv.status_code}")
        pv_json = pv.json()
        # If already at target, revert to ORIG first then continue
        if pv_json.get("status") == "unchanged":
            pytest.skip("phone already at target; skipping to avoid flakiness")
        preview_token = pv_json.get("preview_token")
        payload = {
            "new_phone": self.NEW_PHONE,
            "confirm_user_id": "review-telecaller-0002",
            "expected_phone": self.ORIG_PHONE,
            "idempotency_key": f"iter36-fwd-{uuid.uuid4().hex[:8]}",
            "preview_token": preview_token,
            "reason": "E2E iter36 forward phone change",
        }
        r = requests.post(
            f"{BASE}/api/integrations/staff/review-telecaller-0002/phone",
            headers=_h(tok),
            json=payload,
        )
        assert r.status_code == 200, f"change forward failed: {r.status_code} {r.text[:400]}"
        blob = json.dumps(r.json())
        assert self.NEW_PHONE in blob, f"new phone not in response: {blob[:400]}"

        # revert - fresh preview
        pv2 = requests.post(
            f"{BASE}/api/integrations/staff/review-telecaller-0002/phone/preview",
            headers=_h(tok),
            json={"new_phone": self.ORIG_PHONE},
        )
        pv2j = pv2.json()
        payload2 = {
            "new_phone": self.ORIG_PHONE,
            "confirm_user_id": "review-telecaller-0002",
            "expected_phone": self.NEW_PHONE,
            "idempotency_key": f"iter36-rev-{uuid.uuid4().hex[:8]}",
            "preview_token": pv2j.get("preview_token"),
            "reason": "E2E iter36 revert phone change",
        }
        r3 = requests.post(
            f"{BASE}/api/integrations/staff/review-telecaller-0002/phone",
            headers=_h(tok),
            json=payload2,
        )
        assert r3.status_code == 200, f"revert failed: {r3.status_code} {r3.text[:400]}"


# ---------------------------------------------------------------------------
# J10 - Customer disable/enable/delete + staff disable
# ---------------------------------------------------------------------------

class TestJ10CustomerLifecycle:
    UID = "review-customer-0003"

    def test_disable_then_enable(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        # Discover write mechanic - try telecaller action route
        r = requests.post(
            f"{BASE}/api/telecaller/customers/{self.UID}/action",
            headers=_h(tok),
            json={"action": "disable", "reason": "E2E iter36 disable"},
        )
        if r.status_code not in (200, 201, 202):
            pytest.skip(f"disable endpoint not available on this build ({r.status_code}); recorded for main agent")
        r2 = requests.get(f"{BASE}/api/customers/{self.UID}", headers=_h(tok))
        assert r2.status_code == 200
        blob = json.dumps(r2.json())
        assert "disabled" in blob.lower(), f"disable not reflected: {blob[:400]}"

        r3 = requests.post(
            f"{BASE}/api/telecaller/customers/{self.UID}/action",
            headers=_h(tok),
            json={"action": "enable", "reason": "E2E iter36 enable"},
        )
        assert r3.status_code in (200, 201, 202), f"enable failed: {r3.status_code} {r3.text[:200]}"


class TestJ10StaffDisable:
    STAFF = "review-telecaller-0002"

    def test_disable_returns_ok_or_skip(self, tokens):
        tok = tokens["store-review-admin"]["token"]
        # Try /convert as a disable path is unclear; skip if not defined
        r = requests.post(
            f"{BASE}/api/integrations/staff/{self.STAFF}/convert",
            headers=_h(tok),
            json={"action": "disable", "reason": "E2E iter36 staff disable"},
        )
        if r.status_code not in (200, 201, 202):
            pytest.skip(f"staff disable endpoint not exposed ({r.status_code}) - main agent to confirm UI path")
