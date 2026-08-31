"""Iteration 6 – Unified role-based login + Telecaller CRM + profile edit + role guards.

CRITICAL SAFETY:
- Only exercise demo allowlist phones (8888888888, 8888800001, 8888800002,
  7777777777, 9999999999, 6666666666) and intentionally-invalid formats
  (9876501234 unregistered, 1234567890 invalid).
- Do NOT complete a real phone change (would trigger paid MSG91 SMS to a real number).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL',
                          'https://yash-tryon-test.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

CUSTOMER = "8888800001"        # website-registered customer
CUSTOMER_ALT = "8888888888"    # base demo customer
INACTIVE = "8888800002"
EXEC = "7777777777"
ADMIN = "9999999999"
BILLING = "6666666666"
UNREGISTERED = "9876501234"    # valid format but NOT a user
INVALID_PHONE = "1234567890"   # 10-digit but starts with 1 -> local reject


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(sess, phone, otp="1234"):
    r = sess.post(f"{API}/auth/send-otp", json={"phone": phone})
    if r.status_code == 429:
        pytest.skip(f"Rate-limited on {phone}")
    assert r.status_code == 200, f"send-otp {phone} -> {r.status_code} {r.text}"
    v = sess.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": otp})
    assert v.status_code == 200, f"verify-otp {phone} -> {v.status_code} {v.text}"
    return v.json()


@pytest.fixture(scope="module")
def admin_token(sess):
    return _login(sess, ADMIN)["token"]


@pytest.fixture(scope="module")
def exec_token(sess):
    return _login(sess, EXEC)["token"]


@pytest.fixture(scope="module")
def customer_token(sess):
    return _login(sess, CUSTOMER)["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============================================================================
# 1. Registered-numbers-only enforcement
# ============================================================================
class TestUnregisteredAndInactive:

    def test_unregistered_send_otp_returns_404(self, sess):
        r = sess.post(f"{API}/auth/send-otp", json={"phone": UNREGISTERED})
        if r.status_code == 429:
            pytest.skip("Rate-limited")
        assert r.status_code == 404, f"got {r.status_code} {r.text}"
        detail = r.json().get("detail", "")
        assert "not registered" in detail.lower()

    def test_unregistered_second_send_still_404_no_user_created(self, sess, admin_token):
        # send once
        r1 = sess.post(f"{API}/auth/send-otp", json={"phone": UNREGISTERED})
        # send again immediately: must still be 404, never 200/429-user-created
        r2 = sess.post(f"{API}/auth/send-otp", json={"phone": UNREGISTERED})
        assert r1.status_code in (404, 429)
        assert r2.status_code in (404, 429), f"user was auto-created? {r2.status_code} {r2.text}"
        # Verify no user record exists for that phone
        q = sess.get(f"{API}/customers", headers=H(admin_token),
                     params={"search": UNREGISTERED})
        assert q.status_code == 200
        phones = [c.get("phone") for c in q.json().get("customers", [])]
        assert UNREGISTERED not in phones

    def test_inactive_send_otp_returns_403(self, sess):
        r = sess.post(f"{API}/auth/send-otp", json={"phone": INACTIVE})
        if r.status_code == 429:
            pytest.skip("Rate-limited")
        assert r.status_code == 403, f"got {r.status_code} {r.text}"
        assert "inactive" in r.json().get("detail", "").lower()

    def test_inactive_verify_otp_returns_403(self, sess):
        # Even if someone tries to jump to verify, must be blocked
        r = sess.post(f"{API}/auth/verify-otp", json={"phone": INACTIVE, "otp": "1234"})
        assert r.status_code == 403, f"got {r.status_code} {r.text}"
        assert "inactive" in r.json().get("detail", "").lower()


# ============================================================================
# 2. Website customer login populates website-parity fields
# ============================================================================
class TestWebsiteCustomerLogin:

    def test_login_returns_website_fields(self, sess):
        body = _login(sess, CUSTOMER)
        user = body["user"]
        assert user["role"] == "customer"
        assert user.get("name", "").startswith("Suresh Verma")
        assert user.get("shop_name")
        assert user.get("location")
        assert user.get("has_logged_in") is True
        assert user.get("first_login_at")
        assert user.get("last_login_at")
        assert user.get("account_status") == "active"
        assert user.get("registration_source") == "website"

    def test_auth_me_returns_all_website_fields(self, sess, customer_token):
        r = sess.get(f"{API}/auth/me", headers=H(customer_token))
        assert r.status_code == 200
        me = r.json()
        for field in ("shop_name", "location", "phone_verified", "onboarding_status",
                      "has_logged_in", "account_status", "registration_source",
                      "registered_at", "first_login_at", "last_login_at"):
            assert field in me, f"missing field: {field}. Got keys: {list(me.keys())}"


# ============================================================================
# 3. Profile editing
# ============================================================================
class TestProfileEditing:

    def test_put_profile_updates_and_syncs_city(self, sess, customer_token):
        # Snapshot current
        me0 = sess.get(f"{API}/auth/me", headers=H(customer_token)).json()
        new_shop = f"TEST_Shop_{int(time.time())}"
        new_loc = "TestCity_Ludhiana"
        r = sess.put(f"{API}/auth/profile", headers=H(customer_token),
                     json={"name": me0.get("name", "Suresh Verma"),
                           "shop_name": new_shop, "location": new_loc})
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        updated = r.json()
        assert updated["shop_name"] == new_shop
        assert updated["location"] == new_loc
        assert updated.get("city") == new_loc, "city should be synced to location"
        # Restore to leave demo data intact-ish
        sess.put(f"{API}/auth/profile", headers=H(customer_token),
                 json={"name": me0.get("name", "Suresh Verma"),
                       "shop_name": me0.get("shop_name", ""),
                       "location": me0.get("location", "")})

    def test_put_profile_ignores_role_and_phone(self, sess, customer_token):
        r = sess.put(f"{API}/auth/profile", headers=H(customer_token),
                     json={"role": "admin", "phone": "1234567890"})
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "customer", "role must not be settable via profile"
        assert body["phone"] == CUSTOMER, "phone must not be settable via profile"


# ============================================================================
# 4. Phone-change flow (DO NOT complete)
# ============================================================================
class TestPhoneChange:

    def test_phone_change_request_duplicate_returns_409(self, sess, customer_token):
        # 8888888888 is another demo customer
        r = sess.post(f"{API}/auth/phone-change/request", headers=H(customer_token),
                      json={"new_phone": CUSTOMER_ALT})
        if r.status_code == 429:
            pytest.skip("rate-limited")
        assert r.status_code == 409, f"expected 409 duplicate, got {r.status_code} {r.text}"

    def test_phone_change_request_invalid_returns_400(self, sess, customer_token):
        r = sess.post(f"{API}/auth/phone-change/request", headers=H(customer_token),
                      json={"new_phone": INVALID_PHONE})
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"


# ============================================================================
# 5. Telecaller CRM
# ============================================================================
class TestTelecallerCRM:

    def test_executive_role_returned_on_login(self, sess):
        body = _login(sess, EXEC)
        assert body["user"]["role"] == "executive"

    def test_get_telecaller_customers_assigned_scope(self, sess, exec_token):
        r = sess.get(f"{API}/telecaller/customers", headers=H(exec_token))
        assert r.status_code == 200
        customers = r.json().get("customers", [])
        phones = {c.get("phone") for c in customers}
        # Should include assigned demo phones
        assert CUSTOMER in phones, f"expected {CUSTOMER} in exec's list, got {phones}"

    def test_telecaller_summary_shape(self, sess, exec_token):
        r = sess.get(f"{API}/telecaller/summary", headers=H(exec_token))
        assert r.status_code == 200
        body = r.json()
        for k in ("total_customers", "by_status", "follow_ups_due", "actions_today"):
            assert k in body, f"missing {k} in {body}"
        assert isinstance(body["by_status"], dict)
        assert "interested" in body["by_status"]

    def test_status_change_action_records_activity(self, sess, exec_token):
        # Find the assigned customer id for 8888800001
        r = sess.get(f"{API}/telecaller/customers", headers=H(exec_token),
                     params={"search": CUSTOMER})
        customers = r.json()["customers"]
        target = next((c for c in customers if c["phone"] == CUSTOMER), None)
        assert target, "assigned customer not found"
        cid = target["id"]
        prev = target.get("lead_status", "new")

        act = sess.post(f"{API}/telecaller/customers/{cid}/action",
                        headers=H(exec_token),
                        json={"action": "status_change",
                              "new_status": "interested",
                              "notes": "TEST_iter6 note"})
        assert act.status_code == 200, f"{act.status_code} {act.text}"
        body = act.json()
        assert body["customer"]["lead_status"] == "interested"
        activity = body["activity"]
        assert activity["previous_status"] == prev
        assert activity["new_status"] == "interested"
        assert activity["telecaller_id"]
        assert activity["customer_id"] == cid

        # History
        hist = sess.get(f"{API}/telecaller/customers/{cid}/activity",
                        headers=H(exec_token))
        assert hist.status_code == 200
        acts = hist.json()["activities"]
        assert len(acts) >= 1
        assert acts[0]["notes"] == "TEST_iter6 note"

    def test_invalid_status_returns_422(self, sess, exec_token):
        r = sess.get(f"{API}/telecaller/customers", headers=H(exec_token),
                     params={"search": CUSTOMER})
        cid = next(c["id"] for c in r.json()["customers"] if c["phone"] == CUSTOMER)
        act = sess.post(f"{API}/telecaller/customers/{cid}/action",
                        headers=H(exec_token),
                        json={"action": "status_change", "new_status": "foo"})
        assert act.status_code == 422, f"got {act.status_code} {act.text}"


# ============================================================================
# 6. Role enforcement
# ============================================================================
class TestRoleGuards:

    def test_customer_cannot_access_telecaller_customers(self, sess, customer_token):
        r = sess.get(f"{API}/telecaller/customers", headers=H(customer_token))
        assert r.status_code == 403

    def test_customer_cannot_access_admin_customers(self, sess, customer_token):
        r = sess.get(f"{API}/customers", headers=H(customer_token))
        assert r.status_code == 403

    def test_executive_cannot_access_admin_customers(self, sess, exec_token):
        r = sess.get(f"{API}/customers", headers=H(exec_token))
        assert r.status_code == 403

    def test_executive_cannot_action_unassigned_customer(self, sess, admin_token, exec_token):
        # Find any customer with assigned_salesperson != exec_id (or unassigned)
        exec_me = sess.get(f"{API}/auth/me", headers=H(exec_token)).json()
        exec_id = exec_me["id"]
        all_cust = sess.get(f"{API}/customers", headers=H(admin_token),
                            params={"limit": 100}).json().get("customers", [])
        target = next((c for c in all_cust
                       if c.get("assigned_salesperson") not in (exec_id,)
                       and c.get("phone") not in (CUSTOMER, CUSTOMER_ALT)), None)
        if not target:
            # Force one: unassign 8888888888 via admin
            alt = next((c for c in all_cust if c["phone"] == CUSTOMER_ALT), None)
            if not alt:
                pytest.skip("No unassigned customer available")
            sess.patch(f"{API}/customers/{alt['id']}", headers=H(admin_token),
                       json={"assigned_salesperson": ""})
            target = alt
        r = sess.post(f"{API}/telecaller/customers/{target['id']}/action",
                      headers=H(exec_token),
                      json={"action": "note", "notes": "TEST_should_403"})
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"


# ============================================================================
# 7. Admin customer management
# ============================================================================
class TestAdminCustomerFields:

    def test_customers_list_has_new_fields(self, sess, admin_token):
        r = sess.get(f"{API}/customers", headers=H(admin_token), params={"limit": 50})
        assert r.status_code == 200
        customers = r.json()["customers"]
        assert customers, "expected at least some customers"
        # Find one that has has_logged_in true (8888800001)
        c = next((x for x in customers if x.get("phone") == CUSTOMER), None)
        assert c, f"{CUSTOMER} missing from admin list"
        assert "account_status" in c
        assert "has_logged_in" in c
        assert "shop_name" in c

    def test_patch_assign_salesperson_then_deactivate_reactivate(self, sess, admin_token, exec_token):
        exec_me = sess.get(f"{API}/auth/me", headers=H(exec_token)).json()
        exec_id = exec_me["id"]
        # Use 8888800001 (already assigned to exec) — reassign to same is idempotent
        cust = sess.get(f"{API}/customers", headers=H(admin_token),
                        params={"search": CUSTOMER}).json()["customers"][0]
        cid = cust["id"]
        # Re-assign (idempotent)
        r = sess.patch(f"{API}/customers/{cid}", headers=H(admin_token),
                       json={"assigned_salesperson": exec_id})
        assert r.status_code == 200
        assert r.json().get("assigned_salesperson") == exec_id

        # Deactivate
        r = sess.patch(f"{API}/customers/{cid}", headers=H(admin_token),
                       json={"account_status": "inactive"})
        assert r.status_code == 200
        assert r.json().get("account_status") == "inactive"

        # Verify customer's existing token can't call protected APIs
        # We don't have a fresh customer token bound to this cid at this
        # moment, but we can simulate by trying /auth/me with a stale token.
        # Since customer_token was minted before deactivation, it should now 403.
        try:
            customer_body = _login(sess, CUSTOMER)
            # This login attempt should itself fail with 403 (inactive)
            pytest.fail(f"login should have failed after deactivate, got {customer_body}")
        except AssertionError:
            # send-otp for inactive customer will return 403 -> _login asserts fail
            pass
        finally:
            # ALWAYS reactivate
            r = sess.patch(f"{API}/customers/{cid}", headers=H(admin_token),
                           json={"account_status": "active"})
            assert r.status_code == 200
            assert r.json().get("account_status") == "active"

        # Re-login should now work again
        body = _login(sess, CUSTOMER)
        assert body["user"]["account_status"] == "active"
