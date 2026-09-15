"""Iteration 23 live-preview backend verification.

Runs against EXPO_PUBLIC_BACKEND_URL (or EXPO_BACKEND_URL) — the preview backend
at https://app-first-signin.preview.emergentagent.com/api. Never sends SMS,
never prints reviewer access keys.
"""

import os
import re
import pytest
import requests

# Resolve BASE_URL: prefer EXPO_BACKEND_URL, fall back to EXPO_PUBLIC_BACKEND_URL.
BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "https://app-first-signin.preview.emergentagent.com"
).rstrip("/")

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    ses.headers.update({"Content-Type": "application/json"})
    return ses


# --- Health readiness contract ---

class TestHealth:
    def test_health_is_503_not_ready(self, s):
        r = s.get(f"{API}/health", timeout=30)
        assert r.status_code == 503, r.text
        j = r.json()
        assert j["status"] == "not_ready"
        assert j["ready"] is False
        assert j["commit"] == "unrecorded"
        assert j["flows"]["review"]["ready"] is True
        assert j["flows"]["review"]["issues"] == []
        assert j["flows"]["staff"]["ready"] is False
        assert j["flows"]["staff"]["issues"] == ["STAFF_SERVICE_KEY"]
        assert j["flows"]["mobile"]["ready"] is True
        assert j["configuration"]["REVIEW_ACCESS_ENABLED"] is True
        assert j["configuration"]["BUILD_COMMIT"] is False
        assert j["sms_delivery_verified"] is False
        assert j["account_role_verified"] is False

    def test_health_live_is_200(self, s):
        r = s.get(f"{API}/health/live", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "alive"


# --- Review-login unhappy paths (no SMS, no valid keys) ---

class TestReviewLogin:
    def test_unknown_reviewer_401(self, s):
        r = s.post(
            f"{API}/auth/review/login",
            json={"reviewer_id": "store-review-nobody", "access_key": "x" * 40},
            timeout=15,
        )
        assert r.status_code == 401, r.text
        j = r.json()
        # Support both flat {"code": ...} and nested {"detail": {"code": ...}}.
        code = j.get("code")
        if code is None and isinstance(j.get("detail"), dict):
            code = j["detail"].get("code")
        assert code == "REVIEW_CREDENTIALS_INVALID", j

    def test_malformed_body_422(self, s):
        r = s.post(
            f"{API}/auth/review/login",
            json={"reviewer_id": "store-review-customer"},
            timeout=15,
        )
        assert r.status_code == 422, r.text


# --- Font asset headers ---

class TestFonts:
    def test_ionicons_ttf_ok(self, s):
        r = s.get(f"{API}/fonts/ionicons.ttf", timeout=30)
        assert r.status_code == 200
        # Cloudflare may re-encode and strip content-length, but the origin
        # target is 389724 bytes. Check the actual body length matches.
        assert len(r.content) == 389724, len(r.content)
        ct = r.headers.get("content-type", "")
        assert "font/ttf" in ct or "application/font-sfnt" in ct, ct


# --- Website-dependency auth gates ---

class TestAuthGates:
    def test_customers_search_needs_bearer(self, s):
        r = s.get(f"{API}/customers/search", params={"q": "ab"}, timeout=15)
        assert r.status_code == 401, r.text

    def test_requests_needs_bearer(self, s):
        r = s.get(f"{API}/requests", params={"customer_id": "nope"}, timeout=15)
        assert r.status_code == 401, r.text

    def test_integrations_deletions_needs_integration_key(self, s):
        r = s.get(f"{API}/integrations/deletions", timeout=15)
        assert r.status_code == 401, r.text
