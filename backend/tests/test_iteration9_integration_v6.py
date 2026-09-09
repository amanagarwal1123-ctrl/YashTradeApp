"""
Iteration 9 - Build 2026.09.09-integration-v6
Tests: /api/health integration block, integrations endpoints (upsert/get/delete),
in-app account deletion (request/confirm), admin deletion-requests list, staff blocked,
restore demo customer, regression on profile / telecaller list / products.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://yash-tryon-test.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
INTEGRATION_KEY = "CVO6i5qVspaaYOtn9Esh-KPOHmrgtI9Z4-KYFFtSJGUxeKmR"
BUILD = "2026.09.09-integration-v6"

HDR = {"X-Integration-Key": INTEGRATION_KEY}
SYNTH_PHONE = "8888800077"
DEMO_WEB = "8888800001"


def _login(phone):
    r1 = requests.post(f"{API}/auth/send-otp", json={"phone": phone}, timeout=15)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": "1234"}, timeout=15)
    assert r2.status_code == 200, r2.text
    tok = r2.json().get("token") or r2.json().get("access_token")
    assert tok
    return tok


# ---------------- Health ----------------
class TestHealth:
    def test_health_integration_block(self):
        r = requests.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["build"] == BUILD, j["build"]
        integ = j["integration"]
        assert integ["enabled"] is True
        assert integ["header"] == "X-Integration-Key"
        assert integ["enrollments_path"] == "/api/integrations/enrollments"
        assert integ["delete_path"] == "/api/integrations/customers/{phone}"
        assert j["warnings"] == []
        assert "ENROLLMENT_INTEGRATION_KEY" in j["env_keys_present"]


# ---------------- Integration auth ----------------
class TestIntegrationAuth:
    def test_post_without_header_401(self):
        r = requests.post(f"{API}/integrations/enrollments", json={"phone": SYNTH_PHONE, "name": "x"}, timeout=15)
        assert r.status_code == 401, r.status_code

    def test_post_wrong_key_401(self):
        r = requests.post(f"{API}/integrations/enrollments",
                          headers={"X-Integration-Key": "wrong"},
                          json={"phone": SYNTH_PHONE, "name": "x"}, timeout=15)
        assert r.status_code == 401

    def test_get_without_header_401(self):
        r = requests.get(f"{API}/integrations/customers/{SYNTH_PHONE}", timeout=15)
        assert r.status_code == 401


# ---------------- Integration upsert flow ----------------
class TestIntegrationUpsert:
    def test_full_upsert_and_delete_flow(self):
        # Preclean: delete if exists (ignore result)
        requests.delete(f"{API}/integrations/customers/{SYNTH_PHONE}", headers=HDR, timeout=15)
        # actually also fully wipe - but delete keeps record; okay for test since we assert created flag or not

        body = {
            "phone": SYNTH_PHONE, "name": "Ramesh Kumar", "shop_name": "Kumar Jewellers",
            "location": "Chandni Chowk, Delhi", "city": "Delhi",
            "registration_source": "website",
            "registered_at": "2026-09-09T10:15:00+00:00",
            "onboarding_status": "registered",
            "phone_verified": True, "consent_terms": True, "consent_privacy": True,
        }
        r = requests.post(f"{API}/integrations/enrollments", headers=HDR, json=body, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "created" in j
        c = j["customer"]
        assert c["phone"] == SYNTH_PHONE
        assert c["name"] == "Ramesh Kumar"
        assert c["shop_name"] == "Kumar Jewellers"
        assert c["location"] == "Chandni Chowk, Delhi"
        assert c["city"] == "Delhi"
        assert c["registration_source"] == "website"
        assert c["onboarding_status"] == "registered"
        assert c["registered_at"].startswith("2026-09-09")
        assert c["role"] == "customer"
        assert c["account_status"] == "active"
        assert c["has_logged_in"] is False

        # Second upsert with 12-digit 91-prefix phone and empty shop_name — shop_name must NOT blank existing
        body2 = {"phone": "91" + SYNTH_PHONE, "name": "Ramesh K.", "shop_name": ""}
        r2 = requests.post(f"{API}/integrations/enrollments", headers=HDR, json=body2, timeout=15)
        assert r2.status_code == 200, r2.text
        j2 = r2.json()
        assert j2["created"] is False
        c2 = j2["customer"]
        assert c2["name"] == "Ramesh K."
        assert c2["shop_name"] == "Kumar Jewellers", f"shop_name should not be blanked: {c2}"

        # Invalid phone
        rbad = requests.post(f"{API}/integrations/enrollments", headers=HDR,
                             json={"phone": "12345", "name": "x"}, timeout=15)
        assert rbad.status_code == 400, rbad.status_code

        # Staff conflict
        rstaff = requests.post(f"{API}/integrations/enrollments", headers=HDR,
                               json={"phone": "9999999999", "name": "x"}, timeout=15)
        assert rstaff.status_code == 409, rstaff.status_code

        # GET
        rget = requests.get(f"{API}/integrations/customers/{SYNTH_PHONE}", headers=HDR, timeout=15)
        assert rget.status_code == 200
        cg = rget.json()["customer"]
        assert cg["phone"] == SYNTH_PHONE
        assert cg["name"] == "Ramesh K."


# ---------------- Integration delete ----------------
class TestIntegrationDelete:
    def test_delete_flow(self):
        # Delete synth
        r = requests.delete(f"{API}/integrations/customers/{SYNTH_PHONE}", headers=HDR, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["deleted"] is True
        assert j["reference"].startswith("DEL-"), j["reference"]
        removed = j["removed"]
        for k in ["cart", "wishlists", "ai_chat_history", "reward_transactions", "telecaller_activity"]:
            assert k in removed, f"missing {k} in removed"
        kept = j["kept"]
        for k in ["name", "shop_name", "location", "phone"]:
            assert k in kept, f"missing {k} in kept"

        # GET returns 200 with account_status=deleted and preserved fields
        rget = requests.get(f"{API}/integrations/customers/{SYNTH_PHONE}", headers=HDR, timeout=15)
        assert rget.status_code == 200
        c = rget.json()["customer"]
        assert c["account_status"] == "deleted"
        assert c["name"] == "Ramesh K."
        assert c["shop_name"] == "Kumar Jewellers"
        assert c["location"] == "Chandni Chowk, Delhi"
        assert c["phone"] == SYNTH_PHONE
        assert c.get("reward_points", 0) == 0

        # send-otp on deleted synth -> 404 (no SMS)
        rotp = requests.post(f"{API}/auth/send-otp", json={"phone": SYNTH_PHONE}, timeout=15)
        assert rotp.status_code == 404, rotp.status_code

        # DELETE again -> already_deleted
        r2 = requests.delete(f"{API}/integrations/customers/{SYNTH_PHONE}", headers=HDR, timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("already_deleted") is True

        # DELETE unknown phone
        r3 = requests.delete(f"{API}/integrations/customers/9876501234", headers=HDR, timeout=15)
        assert r3.status_code == 404

        # Re-enroll
        rre = requests.post(f"{API}/integrations/enrollments", headers=HDR, json={
            "phone": SYNTH_PHONE, "name": "Ramesh Kumar",
            "shop_name": "Kumar Jewellers", "location": "Delhi",
        }, timeout=15)
        assert rre.status_code == 200
        jr = rre.json()
        assert jr["customer"]["account_status"] == "active"
        # is_new may be top-level or nested under customer
        is_new = jr.get("is_new")
        if is_new is None:
            is_new = jr["customer"].get("is_new")
        assert is_new is True, f"expected is_new=true on re-enroll, got: {jr}"


# ---------------- In-app deletion ----------------
class TestInAppDeletion:
    def test_in_app_deletion_and_admin_log(self):
        token = _login(DEMO_WEB)
        auth = {"Authorization": f"Bearer {token}"}

        # request
        rreq = requests.post(f"{API}/auth/delete-account/request", headers=auth, timeout=15)
        assert rreq.status_code == 200, rreq.text

        # wrong OTP
        rc0 = requests.post(f"{API}/auth/delete-account/confirm", headers=auth, json={"otp": "0000"}, timeout=15)
        assert rc0.status_code == 400, rc0.status_code

        # correct OTP
        rc1 = requests.post(f"{API}/auth/delete-account/confirm", headers=auth, json={"otp": "1234"}, timeout=15)
        assert rc1.status_code == 200, rc1.text
        j = rc1.json()
        assert j["deleted"] is True
        assert "reference" in j

        # /me with same token -> 403
        rme = requests.get(f"{API}/auth/me", headers=auth, timeout=15)
        assert rme.status_code == 403, rme.status_code

        # send-otp on deleted -> 404
        rotp = requests.post(f"{API}/auth/send-otp", json={"phone": DEMO_WEB}, timeout=15)
        assert rotp.status_code == 404

        # Admin deletion-requests
        atok = _login("9999999999")
        rdr = requests.get(f"{API}/admin/deletion-requests",
                           headers={"Authorization": f"Bearer {atok}"}, timeout=15)
        assert rdr.status_code == 200
        data = rdr.json()
        assert data.get("total", 0) >= 1
        items = data.get("items") or data.get("requests") or []
        entry = next((x for x in items if x.get("phone") == DEMO_WEB), None)
        assert entry is not None, f"no entry for {DEMO_WEB} in {items[:3]}"
        assert entry.get("source") == "app"
        assert entry.get("status") == "completed"

        # Staff (executive) request -> 403
        etok = _login("7777777777")
        rex = requests.post(f"{API}/auth/delete-account/request",
                            headers={"Authorization": f"Bearer {etok}"}, timeout=15)
        assert rex.status_code == 403

        # Restore demo customer
        rres = requests.post(f"{API}/integrations/enrollments", headers=HDR, json={
            "phone": DEMO_WEB, "name": "Suresh Verma",
            "shop_name": "Verma Jewellers", "location": "Ludhiana",
            "onboarding_status": "completed",
        }, timeout=15)
        assert rres.status_code == 200, rres.text
        assert rres.json()["customer"]["account_status"] == "active"

        # login works again
        r_send = requests.post(f"{API}/auth/send-otp", json={"phone": DEMO_WEB}, timeout=15)
        assert r_send.status_code == 200
        r_ver = requests.post(f"{API}/auth/verify-otp", json={"phone": DEMO_WEB, "otp": "1234"}, timeout=15)
        assert r_ver.status_code == 200
        assert r_ver.json().get("token") or r_ver.json().get("access_token")


# ---------------- Regression ----------------
class TestRegression:
    def test_profile_update_and_lists(self):
        token = _login("8888888888")
        auth = {"Authorization": f"Bearer {token}"}

        # PUT /api/auth/profile - set shop_name and onboarding_status
        rp = requests.put(f"{API}/auth/profile", headers=auth,
                          json={"shop_name": "Test Shop", "onboarding_status": "completed"}, timeout=15)
        assert rp.status_code == 200, rp.text
        # Verify via /me
        rm = requests.get(f"{API}/auth/me", headers=auth, timeout=15)
        assert rm.status_code == 200
        me = rm.json()
        assert (me.get("shop_name") or me.get("customer", {}).get("shop_name")) == "Test Shop"

        # Reset shop_name to ""
        rp2 = requests.put(f"{API}/auth/profile", headers=auth, json={"shop_name": ""}, timeout=15)
        assert rp2.status_code == 200

        # Telecaller list - no deleted
        atok = _login("9999999999")
        rl = requests.get(f"{API}/telecaller/customers",
                          headers={"Authorization": f"Bearer {atok}"}, timeout=15)
        assert rl.status_code == 200
        items = rl.json()
        if isinstance(items, dict):
            items = items.get("items") or items.get("customers") or []
        deleted_hit = [c for c in items if c.get("account_status") == "deleted"]
        assert not deleted_hit, f"deleted customers leaked into telecaller list: {deleted_hit[:2]}"

        # Products
        rp3 = requests.get(f"{API}/products?limit=3", timeout=15)
        assert rp3.status_code == 200
