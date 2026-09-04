"""Backend tests for iteration 7 — SMS diagnostics build 2026.09.04-sms-v4.

Covers:
- Public GET /api/health (secret-free, provider_check ok, build tag)
- Admin GET /api/admin/sms/diagnostics (auth guards + shape + provider preflight)
- Admin GET /api/admin/sms/diagnostics?force=true
- Admin POST /api/admin/sms/test (auth guards, demo-allowlist + invalid rejects)
- Admin POST /api/admin/sms/logs/{id}/recheck
- Regression: send-otp / verify-otp / auth-me / products / banners with demo phones only
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or open("/app/frontend/.env").read().split("EXPO_PUBLIC_BACKEND_URL=")[1].split("\n")[0].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

DEMO = {"admin": "9999999999", "executive": "7777777777", "customer": "8888888888", "billing": "6666666666"}
OTP = "1234"

# ---------- session helpers ----------

def _login(phone: str) -> str:
    r = requests.post(f"{API}/auth/send-otp", json={"phone": phone}, timeout=15)
    assert r.status_code == 200, f"send-otp {phone} -> {r.status_code} {r.text}"
    r2 = requests.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": OTP}, timeout=15)
    assert r2.status_code == 200, f"verify-otp {phone} -> {r2.status_code} {r2.text}"
    return r2.json()["token"]

@pytest.fixture(scope="module")
def admin_token():
    return _login(DEMO["admin"])

@pytest.fixture(scope="module")
def exec_token():
    return _login(DEMO["executive"])

@pytest.fixture(scope="module")
def cust_token():
    return _login(DEMO["customer"])

def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ---------- 1. Public /health ----------

class TestPublicHealth:
    def test_health_public_and_no_secrets(self):
        r = requests.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["build"] == "2026.09.04-sms-v4"
        assert body["provider_check"] == "ok"
        assert body["provider_message"] and isinstance(body["provider_message"], str)
        assert body["demo_mode"] is False
        # secret-free: NO authkey value / template_id / hint key in the public payload
        # (the message copy contains the word "authkey" — fine; only real secret fields are checked)
        for k in ("authkey", "authkey_hint", "template_id", "template"):
            assert k not in body, f"public /health leaked field: {k}"


# ---------- 2. /admin/sms/diagnostics ----------

class TestSmsDiagnostics:
    def test_diag_requires_auth(self):
        r = requests.get(f"{API}/admin/sms/diagnostics", timeout=15)
        assert r.status_code == 401

    def test_diag_forbids_executive(self, exec_token):
        r = requests.get(f"{API}/admin/sms/diagnostics", headers=_hdr(exec_token), timeout=15)
        assert r.status_code == 403

    def test_diag_forbids_customer(self, cust_token):
        r = requests.get(f"{API}/admin/sms/diagnostics", headers=_hdr(cust_token), timeout=15)
        assert r.status_code == 403

    def test_diag_admin_shape(self, admin_token):
        r = requests.get(f"{API}/admin/sms/diagnostics", headers=_hdr(admin_token), timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["build"] == "2026.09.04-sms-v4"
        assert d["provider_check"] == "ok"
        assert d["authkey_valid"] is True
        # hint == last 4 chars only, prefixed with ellipsis
        assert d["authkey_hint"] and d["authkey_hint"].startswith("…") and len(d["authkey_hint"]) == 5
        assert d["template_id"] == "61baece18e964726da04e8c5"
        tpl = d["template"]
        assert tpl.get("name") == "Login OTP"
        assert tpl.get("sender_id") == "YSILVR"
        assert tpl.get("dlt_id")
        counters = d["counters_24h"]
        for k in ("total", "accepted", "delivered", "failed", "dropped", "pending", "rejected"):
            assert k in counters, f"missing counter {k}"
        assert isinstance(d["recent"], list)
        for row in d["recent"][:5]:
            for k in ("id", "phone", "purpose", "status", "delivery_status", "sent_at"):
                assert k in row, f"recent row missing {k}"

    def test_diag_force_true(self, admin_token):
        r = requests.get(f"{API}/admin/sms/diagnostics?force=true", headers=_hdr(admin_token), timeout=25)
        assert r.status_code == 200
        assert r.json()["provider_check"] == "ok"


# ---------- 3. /admin/sms/test ----------

class TestSmsTest:
    def test_test_requires_auth(self):
        r = requests.post(f"{API}/admin/sms/test", json={"phone": "8888888888"}, timeout=15)
        assert r.status_code == 401

    def test_test_forbids_executive(self, exec_token):
        r = requests.post(f"{API}/admin/sms/test", json={"phone": "8888888888"}, headers=_hdr(exec_token), timeout=15)
        assert r.status_code == 403

    def test_test_demo_allowlist_rejected(self, admin_token):
        r = requests.post(f"{API}/admin/sms/test", json={"phone": "8888888888"}, headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 400
        assert "demo" in r.json()["detail"].lower()

    def test_test_invalid_prefix(self, admin_token):
        r = requests.post(f"{API}/admin/sms/test", json={"phone": "1234567890"}, headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 400

    def test_test_too_short(self, admin_token):
        r = requests.post(f"{API}/admin/sms/test", json={"phone": "12345"}, headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 400


# ---------- 4. /admin/sms/logs/{id}/recheck ----------

class TestSmsRecheck:
    def test_recheck_nonexistent(self, admin_token):
        r = requests.post(f"{API}/admin/sms/logs/nonexistent-id/recheck", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 404

    def test_recheck_existing_accepted(self, admin_token):
        d = requests.get(f"{API}/admin/sms/diagnostics", headers=_hdr(admin_token), timeout=20).json()
        target = next((r for r in d.get("recent", []) if r.get("status") == "accepted"), None)
        if not target:
            pytest.skip("no 'accepted' sms_log entries available to recheck")
        r = requests.post(f"{API}/admin/sms/logs/{target['id']}/recheck", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == target["id"]
        assert body.get("delivery_status") in ("delivered", "failed", "dropped", "pending")


# ---------- 5. Regression — auth / products / banners with DEMO phones only ----------

class TestAuthRegression:
    @pytest.mark.parametrize("phone", list(DEMO.values()))
    def test_send_otp_demo(self, phone):
        r = requests.post(f"{API}/auth/send-otp", json={"phone": phone}, timeout=15)
        assert r.status_code == 200
        assert "otp" in r.json().get("message", "").lower()

    def test_verify_otp_returns_token_and_user(self):
        r = requests.post(f"{API}/auth/verify-otp", json={"phone": DEMO["customer"], "otp": OTP}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("token")
        assert body.get("user", {}).get("phone") == DEMO["customer"]

    def test_send_otp_unknown_404(self):
        r = requests.post(f"{API}/auth/send-otp", json={"phone": "9876501234"}, timeout=15)
        assert r.status_code == 404

    def test_send_otp_inactive_403(self):
        r = requests.post(f"{API}/auth/send-otp", json={"phone": "8888800002"}, timeout=15)
        assert r.status_code == 403

    def test_send_otp_short_400(self):
        r = requests.post(f"{API}/auth/send-otp", json={"phone": "12345"}, timeout=15)
        assert r.status_code == 400

    def test_auth_me(self, cust_token):
        r = requests.get(f"{API}/auth/me", headers=_hdr(cust_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("phone") == DEMO["customer"]


class TestPublicContent:
    def test_products_limit_5(self):
        r = requests.get(f"{API}/products?limit=5", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # paginated shape: {page, pages, total, products: [...]}
        products = data.get("products") if isinstance(data, dict) else data
        assert isinstance(products, list)
        assert len(products) <= 5

    def test_banners(self):
        r = requests.get(f"{API}/banners", timeout=15)
        assert r.status_code == 200
        data = r.json()
        banners = data.get("banners") if isinstance(data, dict) else data
        assert isinstance(banners, list)
