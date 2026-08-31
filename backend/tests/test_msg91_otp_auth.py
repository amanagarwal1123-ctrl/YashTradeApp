"""MSG91 OTP auth integration tests — iteration 5.

Backend swapped SMS provider from Twilio to MSG91 (control.msg91.com/api/v5/otp).
Endpoint contracts unchanged.

CRITICAL: Only exercise demo allowlist phones and intentionally-invalid formats.
Any real Indian mobile (10 digits starting 6-9) not on allowlist would trigger
a REAL paid MSG91 SMS. Safe negatives: '1111111111' (starts with 1) and '123'
(too short) — both rejected by local validation before MSG91 is called.
For verify-otp we may safely hit MSG91 verify (no SMS cost) with 6543210987.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://yash-tryon-test.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

DEMO_CUSTOMER = "8888888888"
DEMO_ADMIN = "9999999999"
DEMO_EXECUTIVE = "7777777777"
DEMO_BILLING = "6666666666"
INVALID_PHONE = "1111111111"          # 10-digit but starts with 1 -> local reject
SHORT_PHONE = "123"                   # too short -> local reject
NON_DEMO_VALID_FORMAT = "6543210987"  # valid Indian-mobile format, NOT on demo list
# We only send verify (no send-otp) for NON_DEMO_VALID_FORMAT to avoid paid SMS.


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- Demo phones (allowlist) — no MSG91 dispatch ----------
class TestDemoOTPFlow:
    """Demo phones must accept OTP 1234 and return token + user with correct role."""

    @pytest.mark.parametrize("phone,expected_role", [
        (DEMO_CUSTOMER, "customer"),
        (DEMO_ADMIN, "admin"),
        (DEMO_EXECUTIVE, "executive"),
        (DEMO_BILLING, "billing_executive"),
    ])
    def test_send_and_verify_demo(self, s, phone, expected_role):
        r = s.post(f"{API}/auth/send-otp", json={"phone": phone})
        if r.status_code == 429:
            pytest.skip(f"Rate-limited for {phone} (5/10min window)")
        assert r.status_code == 200, f"send-otp {phone} -> {r.status_code} {r.text}"
        assert "message" in r.json()

        v = s.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": "1234"})
        assert v.status_code == 200, f"verify-otp {phone} -> {v.status_code} {v.text}"
        body = v.json()
        assert body.get("token")
        assert body.get("user", {}).get("phone") == phone
        assert body["user"].get("role") == expected_role

    def test_verify_wrong_otp_returns_400(self, s):
        r = s.post(f"{API}/auth/send-otp", json={"phone": DEMO_CUSTOMER})
        if r.status_code == 429:
            pytest.skip("Rate-limited; can't prime OTP store")
        assert r.status_code == 200
        v = s.post(f"{API}/auth/verify-otp", json={"phone": DEMO_CUSTOMER, "otp": "9998"})
        assert v.status_code == 400, f"expected 400, got {v.status_code} {v.text}"
        detail = v.json().get("detail", "")
        assert "Invalid OTP" in detail or "attempts" in detail.lower(), f"unexpected detail: {detail}"


# ---------- Invalid phone formats — rejected locally before MSG91 ----------
class TestInvalidPhone:

    def test_send_short_phone_returns_400(self, s):
        r = s.post(f"{API}/auth/send-otp", json={"phone": SHORT_PHONE})
        assert r.status_code == 400, f"got {r.status_code} {r.text}"
        assert "Invalid phone" in r.json().get("detail", "")

    def test_send_invalid_indian_mobile_returns_friendly_400(self, s):
        # 1111111111 -> 10 digits but starts with 1 -> local validator rejects
        r = s.post(f"{API}/auth/send-otp", json={"phone": INVALID_PHONE})
        if r.status_code == 429:
            pytest.skip("Rate-limited for 1111111111")
        assert r.status_code == 400, f"got {r.status_code} {r.text}"
        detail = r.json().get("detail", "")
        assert "Invalid phone number" in detail, f"expected friendly msg, got: {detail}"

    def test_no_user_created_for_invalid_number(self, s):
        # Log in as admin, then check customer list does NOT contain 1111111111
        r = s.post(f"{API}/auth/send-otp", json={"phone": DEMO_ADMIN})
        if r.status_code == 429:
            pytest.skip("admin rate-limited")
        v = s.post(f"{API}/auth/verify-otp", json={"phone": DEMO_ADMIN, "otp": "1234"})
        assert v.status_code == 200
        token = v.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        for path in ("/customers", "/admin/customers", "/users"):
            r = s.get(f"{API}{path}", headers=headers, params={"search": INVALID_PHONE})
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else (
                    data.get("customers") or data.get("users") or data.get("items") or [])
                phones = [u.get("phone") for u in items if isinstance(u, dict)]
                assert INVALID_PHONE not in phones, f"user created for invalid number via {path}"
                return
        pytest.skip("No admin customers endpoint discovered")

    def test_verify_non_demo_no_pending_returns_400_not_500(self, s):
        # Real MSG91 verify (GET /otp/verify) — no SMS is sent so no cost.
        # Expected: MSG91 responds with 'mobile not found' / 'otp not found' -> 400 friendly
        r = s.post(f"{API}/auth/verify-otp",
                   json={"phone": NON_DEMO_VALID_FORMAT, "otp": "9999"})
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"
        detail = r.json().get("detail", "")
        assert any(k in detail for k in ("OTP expired", "not found", "Invalid OTP")), \
            f"unexpected detail: {detail}"


# ---------- Rate limiting ----------
class TestRateLimit:
    """5 sends per 10min per phone; 6th must 429. Use billing exec demo to avoid SMS."""

    def test_send_otp_rate_limit(self, s):
        phone = DEMO_BILLING
        codes = []
        for _ in range(6):
            r = s.post(f"{API}/auth/send-otp", json={"phone": phone})
            codes.append(r.status_code)
            time.sleep(0.1)
        assert 429 in codes, f"expected a 429 within 6 sends, got {codes}"


# ---------- Auth regression with token from demo login ----------
class TestAuthRegression:

    @pytest.fixture(scope="class")
    def customer_token(self):
        sess = requests.Session()
        sess.headers.update({"Content-Type": "application/json"})
        r = sess.post(f"{API}/auth/send-otp", json={"phone": DEMO_CUSTOMER})
        if r.status_code == 429:
            pytest.skip("customer rate-limited")
        assert r.status_code == 200
        v = sess.post(f"{API}/auth/verify-otp",
                      json={"phone": DEMO_CUSTOMER, "otp": "1234"})
        assert v.status_code == 200
        return v.json()["token"]

    def test_get_auth_me(self, s, customer_token):
        r = s.get(f"{API}/auth/me",
                  headers={"Authorization": f"Bearer {customer_token}"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("phone") == DEMO_CUSTOMER
        assert body.get("role") == "customer"

    def test_get_cart_count(self, s, customer_token):
        r = s.get(f"{API}/cart/count",
                  headers={"Authorization": f"Bearer {customer_token}"})
        assert r.status_code == 200
        body = r.json()
        assert "count" in body or isinstance(body, int), f"unexpected body: {body}"

    def test_get_products(self, s, customer_token):
        r = s.get(f"{API}/products",
                  headers={"Authorization": f"Bearer {customer_token}"},
                  params={"limit": 5})
        assert r.status_code == 200
        body = r.json()
        products = body if isinstance(body, list) else body.get("products", [])
        assert isinstance(products, list)


# ---------- Provider cleanup ----------
class TestNoTwilioReferences:
    def test_server_py_has_no_twilio(self):
        import re
        with open('/app/backend/server.py', 'r') as f:
            src = f.read()
        matches = re.findall(r'twilio', src, re.IGNORECASE)
        assert not matches, f"Found {len(matches)} 'twilio' references in server.py"
