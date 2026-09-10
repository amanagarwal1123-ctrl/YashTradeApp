"""Iteration 10 backend tests — build 2026.09.09-integration-v7.

Covers:
- /api/health: build tag, demo_mode=false, integration key_source='env',
  OTP_DEMO_MODE not surfaced, no warnings, no secret values.
- Subprocess simulation of a deploy WITHOUT ENROLLMENT_INTEGRATION_KEY and with
  OTP_DEMO_MODE=true → default key kicks in, OTP_DEMO_MODE is ignored, only
  allow-list phones get the demo OTP.
- Light regression for the integration upsert/delete endpoints, demo logins,
  admin SMS diagnostics, and product listing.
"""
import json
import os
import subprocess
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://yash-tryon-test.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
INTEGRATION_KEY = "CVO6i5qVspaaYOtn9Esh-KPOHmrgtI9Z4-KYFFtSJGUxeKmR"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def admin_token(s):
    # login admin (demo phone)
    r = s.post(f"{API}/auth/send-otp", json={"phone": "9999999999"}, timeout=15)
    assert r.status_code == 200, r.text
    r = s.post(f"{API}/auth/verify-otp", json={"phone": "9999999999", "otp": "1234"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ---------------- /api/health ---------------- #
class TestHealth:
    def test_health_build_and_flags(self, s):
        r = s.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j.get("build") == "2026.09.09-integration-v7", j
        assert j.get("demo_mode") is False, j
        integ = j.get("integration")
        assert isinstance(integ, dict), j
        assert integ.get("enabled") is True
        assert integ.get("key_source") == "env"
        assert integ.get("header") == "X-Integration-Key"
        assert integ.get("enrollments_path") == "/api/integrations/enrollments"
        assert integ.get("delete_path") == "/api/integrations/customers/{phone}"
        # OTP_DEMO_MODE must NOT appear anywhere in env_keys_present/missing
        assert "OTP_DEMO_MODE" not in j.get("env_keys_present", []), j
        assert "OTP_DEMO_MODE" not in j.get("env_keys_missing", []), j
        assert j.get("warnings") == [], j
        # no secret VALUES in body
        body_text = json.dumps(j)
        assert INTEGRATION_KEY not in body_text, "integration key leaked in /api/health"


# ---------------- Subprocess simulation ---------------- #
class TestSubprocessSimulation:
    def test_default_key_and_ignored_otp_demo_mode(self):
        script = (
            "import os; from dotenv import dotenv_values; "
            "v=dotenv_values('.env'); "
            "[os.environ.__setitem__(k, v[k]) for k in ("
            "'MONGO_URL','DB_NAME','MSG91_AUTHKEY','MSG91_TEMPLATE_ID','JWT_SECRET','OTP_DEMO_PHONES')]; "
            "import dotenv; dotenv.load_dotenv=lambda *a,**k: False; "
            "import server, json; r=server._server_env_report(); "
            "print(json.dumps({"
            "'default_key': server.ENROLLMENT_INTEGRATION_KEY==server.ENROLLMENT_INTEGRATION_DEFAULT_KEY,"
            "'from_env': server.ENROLLMENT_KEY_FROM_ENV,"
            "'demo_9999999999': server._is_demo_phone('9999999999'),"
            "'demo_real': server._is_demo_phone('9711881372'),"
            "'key_source': r['integration']['key_source'],"
            "'warnings': r['warnings']}))"
        )
        env = os.environ.copy()
        env.pop("ENROLLMENT_INTEGRATION_KEY", None)
        env["OTP_DEMO_MODE"] = "true"
        proc = subprocess.run(
            ["env", "-u", "ENROLLMENT_INTEGRATION_KEY", "OTP_DEMO_MODE=true", "python3", "-c", script],
            cwd="/app/backend",
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
        # last non-empty line is the json (server may print startup logs)
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        payload = None
        for ln in reversed(lines):
            try:
                payload = json.loads(ln)
                break
            except Exception:
                continue
        assert payload is not None, f"no json output: {proc.stdout}"
        assert payload["default_key"] is True, payload
        assert payload["from_env"] is False, payload
        assert payload["demo_9999999999"] is True, payload
        assert payload["demo_real"] is False, payload  # a real number is NOT demo even with OTP_DEMO_MODE=true
        assert payload["key_source"] == "built-in default", payload
        warnings = payload["warnings"]
        assert any("OTP_DEMO_MODE" in w and "IGNORED" in w for w in warnings), warnings
        assert any("built-in default" in w for w in warnings), warnings


# ---------------- Regression: integration endpoints ---------------- #
class TestIntegrationRegression:
    def test_upsert_with_valid_key_returns_200(self, s):
        headers = {"X-Integration-Key": INTEGRATION_KEY, "Content-Type": "application/json"}
        body = {"phone": "8888800077", "name": "Ramesh Kumar", "shop_name": "Kumar Jewellers", "location": "Delhi"}
        r = requests.post(f"{API}/integrations/enrollments", headers=headers, json=body, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        cust = j.get("customer") or j
        assert cust.get("shop_name") == "Kumar Jewellers", j

    def test_upsert_without_header_returns_401(self, s):
        body = {"phone": "8888800077", "name": "Ramesh Kumar"}
        r = requests.post(f"{API}/integrations/enrollments", json=body, timeout=15)
        assert r.status_code == 401, r.text


# ---------------- Regression: demo logins & unknown ---------------- #
class TestDemoLogins:
    def test_admin_demo_send_and_verify(self, s):
        r = s.post(f"{API}/auth/send-otp", json={"phone": "9999999999"}, timeout=15)
        assert r.status_code == 200, r.text
        r = s.post(f"{API}/auth/verify-otp", json={"phone": "9999999999", "otp": "1234"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("token")

    def test_customer_demo_send(self, s):
        r = s.post(f"{API}/auth/send-otp", json={"phone": "8888888888"}, timeout=15)
        assert r.status_code == 200, r.text

    def test_unknown_phone_returns_404(self, s):
        r = s.post(f"{API}/auth/send-otp", json={"phone": "9876501234"}, timeout=15)
        assert r.status_code == 404, r.text


# ---------------- Regression: admin diagnostics & products ---------------- #
class TestAdminAndProducts:
    def test_admin_sms_diagnostics(self, s, admin_token):
        r = requests.get(
            f"{API}/admin/sms/diagnostics",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("demo_mode") is False, j
        se = j.get("server_env", {})
        assert se.get("integration", {}).get("key_source") == "env", j

    def test_products_limit_3(self, s):
        r = s.get(f"{API}/products?limit=3", timeout=15)
        assert r.status_code == 200, r.text
