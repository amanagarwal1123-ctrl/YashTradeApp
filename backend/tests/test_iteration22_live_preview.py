"""Iteration 22 – live preview verification against deployed EXPO_PUBLIC_BACKEND_URL.

Focus areas (per review_request):
  * icon-font endpoints (GET/HEAD /api/fonts/*)
  * store-review auth (/api/auth/review/login, /me, /refresh, /logout)
  * review-scoped admin endpoints (analytics/customers/products)
  * review-scoped AI bound (message length limit)
  * health/live gate + review-only banner metadata
  * website D2/D3/D4 dependencies (customer search/detail/requests/deletions auth)
  * regression: public /api/products, unauthenticated /api/auth/me → 401

Credentials come from /tmp/yash-private/preview-review-access.txt (never printed).
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://yash-review-deploy.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PRIVATE_FILE = Path("/tmp/yash-private/preview-review-access.txt")


def _load_reviewers() -> dict[str, str]:
    """Return {reviewer_id: access_key} from the private preview file (never logged)."""
    if not PRIVATE_FILE.exists():
        pytest.skip("preview reviewer credentials file missing")
    creds: dict[str, str] = {}
    pat = re.compile(r"Reviewer ID:\s*(\S+).*?Access key:\s*(\S+)")
    for line in PRIVATE_FILE.read_text().splitlines():
        m = pat.search(line)
        if m:
            creds[m.group(1)] = m.group(2)
    if "store-review-customer" not in creds or "store-review-admin" not in creds:
        pytest.skip("required reviewer entries not found in preview file")
    return creds


@pytest.fixture(scope="session")
def reviewers() -> dict[str, str]:
    return _load_reviewers()


@pytest.fixture(scope="session")
def customer_token(reviewers) -> str:
    r = requests.post(
        f"{API}/auth/review/login",
        json={"reviewer_id": "store-review-customer", "access_key": reviewers["store-review-customer"]},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_token(reviewers) -> str:
    r = requests.post(
        f"{API}/auth/review/login",
        json={"reviewer_id": "store-review-admin", "access_key": reviewers["store-review-admin"]},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ------------------------------------------------------------------ fonts
class TestFonts:
    def test_get_ionicons(self):
        r = requests.get(f"{API}/fonts/ionicons.ttf", timeout=20)
        assert r.status_code == 200
        assert r.headers.get("content-type") == "font/ttf"
        # Cloudflare strips upstream content-length when applying chunked/gzip; verify body length instead
        assert len(r.content) == 389724
        body_sha = hashlib.sha256(r.content).hexdigest()
        assert r.headers.get("x-font-sha256") == body_sha

    def test_manifest_matches_body(self):
        r = requests.get(f"{API}/fonts/ionicons.manifest.json", timeout=20)
        assert r.status_code == 200
        manifest_sha = r.json().get("sha256")
        r2 = requests.get(f"{API}/fonts/ionicons.ttf", timeout=20)
        assert manifest_sha == hashlib.sha256(r2.content).hexdigest()

    def test_head_ionicons(self):
        r = requests.head(f"{API}/fonts/ionicons.ttf", timeout=20)
        assert r.status_code == 200
        # Origin advertises content-length: 389724; the CDN may strip it when chunked-encoding,
        # so only assert when the header is preserved end-to-end.
        cl = r.headers.get("content-length")
        if cl is not None:
            assert cl == "389724"

    def test_material_icons_missing(self):
        r = requests.get(f"{API}/fonts/MaterialIcons.ttf", timeout=20)
        assert r.status_code == 404


# ------------------------------------------------------------------ review auth
class TestReviewAuth:
    def test_unknown_reviewer_invalid(self):
        r = requests.post(
            f"{API}/auth/review/login",
            json={"reviewer_id": "store-review-owner", "access_key": "x" * 40},
            timeout=20,
        )
        assert r.status_code == 401
        assert r.json().get("code") == "REVIEW_CREDENTIALS_INVALID"

    def test_extra_field_rejected(self, reviewers):
        r = requests.post(
            f"{API}/auth/review/login",
            json={"reviewer_id": "store-review-customer", "access_key": reviewers["store-review-customer"], "role": "admin"},
            timeout=20,
        )
        assert r.status_code == 422

    def test_short_key_rejected(self):
        r = requests.post(
            f"{API}/auth/review/login",
            json={"reviewer_id": "store-review-customer", "access_key": "short"},
            timeout=20,
        )
        assert r.status_code == 422

    def test_customer_login_and_me(self, reviewers):
        r = requests.post(
            f"{API}/auth/review/login",
            json={"reviewer_id": "store-review-customer", "access_key": reviewers["store-review-customer"]},
            timeout=20,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["role"] == "customer"
        assert data.get("review_environment") is True
        assert data.get("token")
        assert data.get("refresh_token", "").startswith("review.")

        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {data['token']}"}, timeout=20)
        assert me.status_code == 200
        mj = me.json()
        assert mj.get("role") == "customer"
        assert mj.get("review_environment") is True

        rr = requests.post(f"{API}/auth/refresh", json={"refresh_token": data["refresh_token"]}, timeout=20)
        assert rr.status_code == 200, rr.text

        lo = requests.post(f"{API}/auth/logout", headers={"Authorization": f"Bearer {data['token']}"}, timeout=20)
        assert lo.status_code == 200
        assert lo.json().get("logged_out") is True

    def test_admin_analytics_and_scoped_data(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/analytics/dashboard", headers=h, timeout=20)
        assert r.status_code == 200, r.text

        r = requests.get(f"{API}/customers?limit=100", headers=h, timeout=20)
        assert r.status_code == 200
        payload = r.json()
        items = payload.get("customers") if isinstance(payload, dict) else payload
        assert items, "expected synthetic customer list"
        for c in items:
            name = (c.get("name") or c.get("full_name") or "").lower()
            assert "synthetic" in name, f"non-synthetic customer surfaced: {name!r}"

        r = requests.get(f"{API}/products?limit=100", headers=h, timeout=20)
        assert r.status_code == 200
        payload = r.json()
        products = payload.get("products") if isinstance(payload, dict) else payload
        assert products, "expected synthetic products"
        for p in products:
            pid = p.get("id") or p.get("product_id") or ""
            assert pid.startswith("review-product-"), f"unexpected product id: {pid!r}"


class TestReviewRateLimit:
    def test_rate_limit_locks_reviewer(self, reviewers):
        rid = "store-review-billing"
        for _ in range(5):
            r = requests.post(
                f"{API}/auth/review/login",
                json={"reviewer_id": rid, "access_key": "z" * 45},
                timeout=20,
            )
            assert r.status_code in (401, 429)
        # correct key next should be blocked with 429
        r = requests.post(
            f"{API}/auth/review/login",
            json={"reviewer_id": rid, "access_key": reviewers[rid]},
            timeout=20,
        )
        assert r.status_code == 429, f"expected 429 after 5 wrong keys, got {r.status_code}"


# ------------------------------------------------------------------ review AI bound
class TestReviewAIBound:
    def test_long_message_review_blocked(self, customer_token):
        h = {"Authorization": f"Bearer {customer_token}"}
        r = requests.post(f"{API}/ai/chat", headers=h, json={"message": "x" * 601}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("error") is True
        assert body.get("review_limit") == "message_length"


# ------------------------------------------------------------------ health
class TestHealth:
    def test_health_metadata(self):
        r = requests.get(f"{API}/health", timeout=20)
        # /health returns 503 when overall status=not_ready (STAFF placeholder). That is expected
        # in preview per review_request; the body fields still describe review readiness truthfully.
        assert r.status_code in (200, 503)
        j = r.json()
        assert j.get("build") == "shared-v1-store-submission-2026-09-13"
        assert j.get("configuration", {}).get("REVIEW_ACCESS_ENABLED") is True
        assert j.get("flows", {}).get("review", {}).get("ready") is True
        staff = j.get("flows", {}).get("staff", {})
        assert staff.get("ready") is False
        assert "STAFF_SERVICE_KEY" in (staff.get("issues") or [])

    def test_health_live(self):
        r = requests.get(f"{API}/health/live", timeout=20)
        assert r.status_code == 200


# ------------------------------------------------------------------ D2/D3/D4
class TestWebsiteD2D3D4:
    def test_d2_customer_search_alpha(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/customers/search?q=Sample", headers=h, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "customers" in body
        assert body.get("query") == "Sample"
        assert body.get("limit") == 20
        assert body.get("minimum_length") == 2

    def test_d2_customer_search_min_length(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/customers/search?q=9", headers=h, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body.get("customers") == []
        assert body.get("minimum_length") == 2

    def test_d3_customer_detail(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/customers/review-customer-0001", headers=h, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("detail_limit") == 100
        ch = j.get("complete_history") or ""
        assert ch.startswith("/api/requests?customer_id=review-customer-0001")

    def test_d3_requests_filter(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(
            f"{API}/requests?customer_id=review-customer-0001&status=all&limit=100",
            headers=h,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("customer_id") == "review-customer-0001"
        rows = j.get("requests") or j.get("results") or []
        for row in rows:
            assert row.get("customer_id") == "review-customer-0001"

    def test_d3_requests_invalid_filter(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/requests?customer_id=$where:1", headers=h, timeout=20)
        assert r.status_code == 422
        assert r.json().get("code") == "INVALID_FILTER"

    def test_d3_requests_unknown_customer(self, admin_token):
        # customer_scope() on /api/requests returns 404 for unknown but canonical-format IDs
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/requests?customer_id=review-customer-9999", headers=h, timeout=20)
        assert r.status_code == 404
        assert r.json().get("code") == "CUSTOMER_NOT_FOUND"

    def test_d4_deletions_requires_key(self):
        r = requests.get(f"{API}/integrations/deletions", timeout=20)
        assert r.status_code == 401
        r2 = requests.get(
            f"{API}/integrations/deletions",
            headers={"X-Integration-Key": "wrong-key"},
            timeout=20,
        )
        assert r2.status_code == 401


# ------------------------------------------------------------------ regression
class TestRegression:
    def test_public_products(self):
        r = requests.get(f"{API}/products", timeout=20)
        assert r.status_code == 200

    def test_unauthenticated_me(self):
        r = requests.get(f"{API}/auth/me", timeout=20)
        assert r.status_code == 401
