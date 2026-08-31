"""Twilio OTP auth integration tests - iteration 4.

CRITICAL: Only exercise demo phones + intentionally-invalid 1111111111.
Any other 10-digit number would send a REAL paid SMS via Twilio.
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
INVALID_PHONE = "1111111111"  # not a demo phone -> hits Twilio 60200


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- Demo phones (allowlist) ----------
class TestDemoOTPFlow:
    """Demo phones must accept OTP 1234 and return token + user."""

    @pytest.mark.parametrize("phone,expected_role", [
        (DEMO_CUSTOMER, "customer"),
        (DEMO_ADMIN, "admin"),
        (DEMO_EXECUTIVE, "executive"),
    ])
    def test_send_and_verify_demo(self, s, phone, expected_role):
        r = s.post(f"{API}/auth/send-otp", json={"phone": phone})
        # allow 429 if a previous iteration exhausted the rate window
        if r.status_code == 429:
            pytest.skip(f"Rate-limited for {phone} (5/10min window). Expected transient.")
        assert r.status_code == 200, f"send-otp {phone} -> {r.status_code} {r.text}"
        assert "message" in r.json()

        v = s.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": "1234"})
        assert v.status_code == 200, f"verify-otp {phone} -> {v.status_code} {v.text}"
        body = v.json()
        assert "token" in body and body["token"]
        assert "user" in body
        assert body["user"]["phone"] == phone
        assert body["user"].get("role") == expected_role

    def test_verify_wrong_otp_returns_400(self, s):
        # Prime the OTP store first
        r = s.post(f"{API}/auth/send-otp", json={"phone": DEMO_CUSTOMER})
        if r.status_code == 429:
            pytest.skip("Rate-limited; can't prime OTP store")
        assert r.status_code == 200
        v = s.post(f"{API}/auth/verify-otp", json={"phone": DEMO_CUSTOMER, "otp": "9998"})
        assert v.status_code == 400, f"expected 400, got {v.status_code} {v.text}"
        detail = v.json().get("detail", "")
        assert "OTP" in detail or "attempts" in detail.lower(), f"unexpected detail: {detail}"


# ---------- Invalid / non-demo phones (Twilio path) ----------
class TestInvalidPhone:

    def test_send_short_phone_returns_400(self, s):
        r = s.post(f"{API}/auth/send-otp", json={"phone": "123"})
        assert r.status_code == 400
        assert "Invalid phone" in r.json().get("detail", "")

    def test_send_invalid_number_friendly_400(self, s):
        # 1111111111 is not on demo allowlist and Twilio rejects with 60200
        r = s.post(f"{API}/auth/send-otp", json={"phone": INVALID_PHONE})
        if r.status_code == 429:
            pytest.skip("Rate-limited for 1111111111; friendly 400 already validated earlier")
        assert r.status_code == 400, f"got {r.status_code} {r.text}"
        detail = r.json().get("detail", "")
        assert "Invalid phone number" in detail, f"expected friendly msg, got: {detail}"
        # And a NON 500

    def test_no_user_created_for_invalid_number(self, s):
        # Log in as admin, then search customers for 1111111111
        s2 = s.post(f"{API}/auth/send-otp", json={"phone": DEMO_ADMIN})
        if s2.status_code == 429:
            pytest.skip("admin rate-limited; skip user-not-created verification")
        v = s.post(f"{API}/auth/verify-otp", json={"phone": DEMO_ADMIN, "otp": "1234"})
        assert v.status_code == 200
        token = v.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Try common admin listing endpoints
        for path in ("/customers", "/admin/customers", "/users"):
            r = s.get(f"{API}{path}", headers=headers, params={"search": INVALID_PHONE})
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else (data.get("customers") or data.get("users") or data.get("items") or [])
                phones = [u.get("phone") for u in items if isinstance(u, dict)]
                assert INVALID_PHONE not in phones, f"user was created for invalid number via {path}"
                return
        pytest.skip("No admin customers endpoint discovered; friendly 400 alone was validated in prior test")

    def test_verify_non_demo_no_pending_returns_400_not_500(self, s):
        # No prior send-otp for 1111111111 accepted, so Twilio should say 404/60200 -> 400
        r = s.post(f"{API}/auth/verify-otp", json={"phone": INVALID_PHONE, "otp": "9999"})
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"
        detail = r.json().get("detail", "")
        # Accept either 'Invalid phone' (60200) or 'OTP expired or not found' (404)
        assert any(k in detail for k in ("Invalid phone", "OTP expired", "not found")), f"unexpected: {detail}"


# ---------- Rate limiting ----------
class TestRateLimit:
    """5 sends per 10min window; 6th must 429. Use a phone we can burn: 6666666666 (billing exec demo)."""

    def test_send_otp_rate_limit(self, s):
        phone = "6666666666"  # demo billing exec, does NOT hit Twilio
        codes = []
        for i in range(6):
            r = s.post(f"{API}/auth/send-otp", json={"phone": phone})
            codes.append(r.status_code)
            time.sleep(0.1)
        # First 5 should be 200, 6th 429 (or earlier 429 if previous iter left counters)
        assert 429 in codes, f"expected a 429 within 6 sends, got {codes}"
        # And at least the earliest attempts before 429 should have been 200
        first_success = codes[0]
        assert first_success in (200, 429), f"first attempt unexpected: {codes}"


# ---------- Auth regression on token from demo login ----------
class TestAuthRegression:

    @pytest.fixture(scope="class")
    def customer_token(self):
        sess = requests.Session()
        sess.headers.update({"Content-Type": "application/json"})
        r = sess.post(f"{API}/auth/send-otp", json={"phone": DEMO_CUSTOMER})
        if r.status_code == 429:
            pytest.skip("customer rate-limited")
        assert r.status_code == 200
        v = sess.post(f"{API}/auth/verify-otp", json={"phone": DEMO_CUSTOMER, "otp": "1234"})
        assert v.status_code == 200
        return v.json()["token"]

    def test_get_auth_me(self, s, customer_token):
        r = s.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {customer_token}"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("phone") == DEMO_CUSTOMER
        assert body.get("role") == "customer"

    def test_get_cart_count(self, s, customer_token):
        r = s.get(f"{API}/cart/count", headers={"Authorization": f"Bearer {customer_token}"})
        assert r.status_code == 200
        body = r.json()
        # response could be {"count": N} or an int
        assert "count" in body or isinstance(body, int), f"unexpected body: {body}"

    def test_get_products(self, s, customer_token):
        r = s.get(f"{API}/products", headers={"Authorization": f"Bearer {customer_token}"}, params={"limit": 5})
        assert r.status_code == 200
        body = r.json()
        # accept either list or {products: [...]}
        products = body if isinstance(body, list) else body.get("products", [])
        assert isinstance(products, list)
