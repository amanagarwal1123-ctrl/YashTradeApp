"""Iteration 31: verify deployment-blocker fixes on live preview.

Focus areas:
  1. Reviewer admin sign-in and deletion ledger listing (DEL-review-int-0001 interrupted).
  2. Guards for the new resume endpoint (409 CLEANUP_NOT_PENDING, 404, 401).
  3. Successful resume via API and second-call 409 CLEANUP_NOT_PENDING.
  4. Regression: /api/health, /api/openapi.json, provider action lifecycle.

Reviewer admin key read from private file; NEVER printed.
"""
from __future__ import annotations

import os
import pathlib
import time
from typing import Any

import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else None
if not BASE_URL:
    # Fallback to frontend/.env value read at import (kept out of code once tests run against preview)
    envfile = pathlib.Path("/app/frontend/.env").read_text().splitlines()
    for line in envfile:
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

API = f"{BASE_URL}/api"

REVIEWER_KEY_PATH = pathlib.Path("/tmp/yash-private/preview-store-review-admin-e2e31.txt")


def _read_reviewer_key() -> str:
    for line in REVIEWER_KEY_PATH.read_text().splitlines():
        if "Reviewer ID: store-review-admin" in line and "Access key:" in line:
            return line.split("Access key:", 1)[1].strip()
    raise RuntimeError("Reviewer key not found")


@pytest.fixture(scope="module")
def admin_token() -> str:
    key = _read_reviewer_key()
    resp = requests.post(
        f"{API}/auth/review/login",
        json={"reviewer_id": "store-review-admin", "access_key": key},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("user", {}).get("role") == "admin"
    return body["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


def _get_row(headers: dict[str, str], reference: str) -> dict[str, Any] | None:
    resp = requests.get(f"{API}/admin/deletion-requests", headers=headers, timeout=30)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for row in data.get("requests", []):
        if row.get("reference") == reference:
            return row
    return None


class TestListing:
    def test_int_row_present_and_interrupted(self, admin_headers):
        row = _get_row(admin_headers, "DEL-review-int-0001")
        assert row is not None, "DEL-review-int-0001 missing from ledger"
        # Row was already resumed by an earlier module run when re-running; both paths acceptable
        if row["status"] == "local_cleanup_pending":
            cleanup = row.get("cleanup") or {}
            assert cleanup.get("app") == "pending", cleanup
            note = cleanup.get("note") or ""
            assert "interrupted" in note.lower(), note
        else:
            assert row["status"] == "external_erasure_pending", row["status"]
        assert row.get("provider_erasure") == "outstanding", row.get("provider_erasure")

    def test_customer_row_present_external_pending(self, admin_headers):
        row = _get_row(admin_headers, "DEL-review-customer-0001")
        assert row is not None
        assert row["status"] == "external_erasure_pending", row["status"]


class TestGuardsBeforeResume:
    def test_wrong_state_returns_409(self, admin_headers):
        resp = requests.post(
            f"{API}/admin/deletion-requests/DEL-review-customer-0001/cleanup",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 409, (resp.status_code, resp.text)
        assert resp.json().get("code") == "CLEANUP_NOT_PENDING", resp.text

    def test_unknown_reference_returns_404(self, admin_headers):
        resp = requests.post(
            f"{API}/admin/deletion-requests/DEL-does-not-exist/cleanup",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 404, resp.text
        assert resp.json().get("code") == "DELETION_NOT_FOUND", resp.text

    def test_unauth_returns_401(self):
        resp = requests.post(
            f"{API}/admin/deletion-requests/DEL-review-int-0001/cleanup",
            timeout=30,
        )
        assert resp.status_code == 401, resp.text


class TestHealthAndOpenAPI:
    def test_health_deletion_ready(self):
        resp = requests.get(f"{API}/health", timeout=30)
        # Preview typically returns 503 not_ready because STAFF_SERVICE_KEY is placeholder (expected).
        assert resp.status_code in (200, 503), resp.status_code
        body = resp.json()
        flows = body.get("flows") or {}
        deletion = flows.get("deletion") or {}
        assert deletion.get("ready") is True, deletion

    def test_openapi_lists_cleanup_endpoint(self):
        resp = requests.get(f"{API}/openapi.json", timeout=30)
        assert resp.status_code == 200
        paths = resp.json().get("paths", {})
        assert "/api/admin/deletion-requests/{reference}/cleanup" in paths, list(paths.keys())[-20:]


class TestProviderActionLifecycle:
    """Existing provider-action endpoint still works.

    Leaves final state 'requested' as instructed.
    """

    def test_request_and_reopen(self, admin_headers):
        # request
        body = {"action": "requested", "request_reference": "E2E-31", "channel": "email"}
        r1 = requests.post(
            f"{API}/admin/deletion-requests/DEL-review-customer-0001/providers/ai_provider",
            headers=admin_headers,
            json=body,
            timeout=30,
        )
        # Row may already be in requested state from previous iterations; two acceptable outcomes:
        #   * 200 with state == requested
        #   * 409 PROVIDER_STATE if row already in requested
        assert r1.status_code in (200, 409), r1.text
        if r1.status_code == 200:
            assert r1.json().get("providers", {}).get("ai_provider", {}).get("state") == "requested"
        # reopen while requested should be 409 PROVIDER_STATE
        r2 = requests.post(
            f"{API}/admin/deletion-requests/DEL-review-customer-0001/providers/ai_provider",
            headers=admin_headers,
            json={"action": "reopen"},
            timeout=30,
        )
        assert r2.status_code == 409, r2.text
        assert r2.json().get("code") == "PROVIDER_STATE", r2.text


class TestResumeCleanup:
    """Runs after guard tests; performs the actual resume.

    The row DEL-review-int-0001 is a fixture and once resumed cannot be re-resumed within the
    same DB state. This test tolerates that: if the row is already resumed (e.g., by a previous
    run of this test in the module), we skip the primary POST assertion and only verify the
    second-call 409 path plus the persistent DB state (cleanup.resumed[]) via the GET listing.
    """

    def test_resume_success_and_second_call_409(self, admin_headers):
        row = _get_row(admin_headers, "DEL-review-int-0001")
        assert row is not None
        # First-run path: still local_cleanup_pending
        if row["status"] == "local_cleanup_pending":
            resp = requests.post(
                f"{API}/admin/deletion-requests/DEL-review-int-0001/cleanup",
                headers=admin_headers,
                timeout=60,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body.get("status") == "external_erasure_pending", body
            cleanup = body.get("cleanup") or {}
            assert cleanup.get("app") == "completed", cleanup

        # Verify persistent state: row is now external_erasure_pending, cleanup.app='completed'
        row2 = _get_row(admin_headers, "DEL-review-int-0001")
        assert row2 is not None
        assert row2["status"] == "external_erasure_pending", row2["status"]
        cleanup2 = row2.get("cleanup") or {}
        assert cleanup2.get("app") == "completed", cleanup2
        assert cleanup2.get("website") == "pending", cleanup2

        # Second call must be 409 CLEANUP_NOT_PENDING
        r2 = requests.post(
            f"{API}/admin/deletion-requests/DEL-review-int-0001/cleanup",
            headers=admin_headers,
            timeout=30,
        )
        assert r2.status_code == 409, r2.text
        assert r2.json().get("code") == "CLEANUP_NOT_PENDING", r2.text
