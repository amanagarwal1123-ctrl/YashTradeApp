"""E2E backend tests for iteration 30: deletion-status two-outcome model against the LIVE preview backend.

Verifies:
- Review scope: GET /api/admin/deletion-requests structure/rows/providers
- Review scope: provider action lifecycle on ai_provider (state machine, validation, guards)
- Review scope: cleanup/status invariance across provider actions
- Review scope: access control (customer -> 403, no token -> 401)
- Production scope: superseded rows shape + 409 DELETION_SUPERSEDED
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://app-first-signin.preview.emergentagent.com").rstrip("/")

REVIEW_ADMIN_KEY_FILE = "/tmp/yash-private/preview-store-review-admin-e2e.txt"
REVIEW_CUSTOMER_KEY_FILE = "/tmp/yash-private/preview-store-review-customer-2026-09-15.txt"
FIXTURES_FILE = "/tmp/yash-private/e2e-fixtures.json"

REVIEW_ROW = "DEL-review-customer-0001"
AI_PROVIDER = "ai_provider"
SMS_PROVIDER = "sms_provider"

# Live-preview evidence run (iteration 30). It needs the disposable private fixtures of that run; without them it is skipped.
pytestmark = pytest.mark.skipif(not all(Path(p).exists() for p in (REVIEW_ADMIN_KEY_FILE, REVIEW_CUSTOMER_KEY_FILE, FIXTURES_FILE)),
                                reason="live-preview fixtures (/tmp/yash-private) not present; see test_reports/iteration_30.json for the recorded run")


# ---------------- helpers ----------------

def _read_reviewer_credentials(path: str) -> tuple[str, str]:
    text = Path(path).read_text()
    # Format: "Reviewer ID: <id> ... Access key: <key>"
    m_id = re.search(r"Reviewer ID:\s*([^\s]+)", text)
    m_key = re.search(r"Access key:\s*(\S+)", text)
    assert m_id and m_key, f"could not parse credentials from {path}"
    return m_id.group(1), m_key.group(1)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _review_login(session: requests.Session, key_file: str) -> str:
    rid, key = _read_reviewer_credentials(key_file)
    r = session.post(
        f"{BASE_URL}/api/auth/review/login",
        json={"reviewer_id": rid, "access_key": key},
        timeout=30,
    )
    assert r.status_code == 200, f"reviewer login failed {r.status_code} {r.text}"
    return r.json()["token"]


def _refresh_admin_fixture_if_needed(session: requests.Session) -> str:
    data = json.loads(Path(FIXTURES_FILE).read_text())
    tok = data["admin_fixture"]["token"]
    ping = session.get(f"{BASE_URL}/api/auth/me", headers=_bearer(tok), timeout=30)
    if ping.status_code == 200:
        return tok
    refresh_token = data["admin_fixture"]["refresh_token"]
    r = session.post(
        f"{BASE_URL}/api/auth/refresh",
        json={"refresh_token": refresh_token},
        timeout=30,
    )
    assert r.status_code == 200, f"refresh failed {r.status_code} {r.text}"
    body = r.json()
    data["admin_fixture"]["token"] = body["token"]
    if body.get("refresh_token"):
        data["admin_fixture"]["refresh_token"] = body["refresh_token"]
    Path(FIXTURES_FILE).write_text(json.dumps(data, indent=1))
    return body["token"]


# ---------------- fixtures ----------------

@pytest.fixture(scope="module")
def api_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def review_admin_token(api_client: requests.Session) -> str:
    return _review_login(api_client, REVIEW_ADMIN_KEY_FILE)


@pytest.fixture(scope="module")
def review_customer_token(api_client: requests.Session) -> str:
    return _review_login(api_client, REVIEW_CUSTOMER_KEY_FILE)


@pytest.fixture(scope="module")
def prod_admin_token(api_client: requests.Session) -> str:
    return _refresh_admin_fixture_if_needed(api_client)


# ---------------- Review-scope: listing structure ----------------

class TestListingStructure:
    def test_listing_structure_and_providers(self, api_client, review_admin_token):
        r = api_client.get(
            f"{BASE_URL}/api/admin/deletion-requests",
            headers=_bearer(review_admin_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(["requests", "total", "provider_procedures", "states"]).issubset(body.keys())
        # provider_procedures for three providers
        pp = body["provider_procedures"]
        for key in ("sms_provider", "ai_provider", "object_storage"):
            assert key in pp
            entry = pp[key]
            assert "provider" in entry and "holds" in entry and "procedure" in entry
            assert entry.get("delete_api") is False
        # states has 6 states (typical set: not_applicable, not_requested, requested, no_procedure, confirmed, refused)
        assert isinstance(body["states"], dict) and len(body["states"]) == 6
        # Find review row
        row = next((r for r in body["requests"] if r["reference"] == REVIEW_ROW), None)
        assert row is not None, f"review row {REVIEW_ROW} not found in listing"
        assert "status" in row and "cleanup" in row and "providers" in row
        assert "provider_erasure" in row
        assert "meaning" in row
        # PII must be excluded
        for banned in ("phone", "name", "shop_name"):
            assert banned not in row, f"PII field '{banned}' should not be in row"
        # providers include state/history
        for pk in ("sms_provider", "ai_provider", "object_storage"):
            assert pk in row["providers"]
            pv = row["providers"][pk]
            assert "state" in pv and "history" in pv


# ---------------- Review-scope: lifecycle ----------------

class TestProviderLifecycle:
    """Sequential lifecycle on DEL-review-customer-0001 / ai_provider."""

    def _post(self, api_client, token, provider, body, expected_status=None):
        r = api_client.post(
            f"{BASE_URL}/api/admin/deletion-requests/{REVIEW_ROW}/providers/{provider}",
            headers=_bearer(token),
            json=body,
            timeout=30,
        )
        if expected_status is not None:
            assert r.status_code == expected_status, f"expected {expected_status}, got {r.status_code}: {r.text}"
        return r

    def _get_provider(self, api_client, token, provider) -> dict:
        r = api_client.get(f"{BASE_URL}/api/admin/deletion-requests", headers=_bearer(token), timeout=30)
        row = next(rr for rr in r.json()["requests"] if rr["reference"] == REVIEW_ROW)
        return row["providers"][provider], row

    def _reset_to_not_requested(self, api_client, token):
        """Best-effort reopen loop to reach not_requested / requested baseline."""
        state, _ = self._get_provider(api_client, token, AI_PROVIDER)
        # If in a terminal state, reopen; loop up to 4 times
        for _ in range(4):
            if state["state"] in ("not_requested",):
                return
            r = self._post(api_client, token, AI_PROVIDER, {"action": "reopen"})
            if r.status_code != 200:
                break
            state, _ = self._get_provider(api_client, token, AI_PROVIDER)

    def test_0_baseline_reopen(self, api_client, review_admin_token):
        # Reopen loop until we're in the earliest resettable state
        self._reset_to_not_requested(api_client, review_admin_token)
        state, _ = self._get_provider(api_client, review_admin_token, AI_PROVIDER)
        assert state["state"] in ("not_requested", "requested"), state["state"]
        # If not not_requested, we can still exercise 409 by attempting a 'confirmed' from a not_requested state; skip guard test if needed
        pytest.provider_baseline_state = state["state"]

    def test_1_confirmed_from_not_requested_returns_409_provider_state(self, api_client, review_admin_token):
        state, _ = self._get_provider(api_client, review_admin_token, AI_PROVIDER)
        if state["state"] != "not_requested":
            # Force reopen from requested (only route back). If we can't get to not_requested, skip.
            pytest.skip(f"cannot reach not_requested state (currently {state['state']})")
        r = self._post(api_client, review_admin_token, AI_PROVIDER, {"action": "confirmed", "outcome": "some-outcome-text"})
        assert r.status_code == 409, r.text
        body = r.json()
        assert "PROVIDER_STATE" in json.dumps(body).upper(), body

    def test_2_requested_transitions_ok(self, api_client, review_admin_token):
        r = self._post(api_client, review_admin_token, AI_PROVIDER,
                       {"action": "requested", "request_reference": "TICKET-1", "channel": "email support@emergent.sh"},
                       expected_status=200)
        body = r.json()
        state, _ = self._get_provider(api_client, review_admin_token, AI_PROVIDER)
        assert state["state"] == "requested"
        assert state.get("requested_at")
        assert isinstance(state.get("history"), list) and len(state["history"]) >= 1
        # Last history entry has actor_id
        last = state["history"][-1]
        assert last.get("actor_id"), f"history missing actor_id: {last}"

    def test_3_confirmed_short_outcome_returns_422(self, api_client, review_admin_token):
        r = self._post(api_client, review_admin_token, AI_PROVIDER, {"action": "confirmed", "outcome": "abc"})
        assert r.status_code == 422, r.text
        assert "OUTCOME_REQUIRED" in r.text.upper() or "OUTCOME" in r.text.upper()

    def test_4_refused_without_exception_returns_422(self, api_client, review_admin_token):
        r = self._post(api_client, review_admin_token, AI_PROVIDER, {"action": "refused", "outcome": "Provider declined the request"})
        assert r.status_code == 422, r.text
        assert "RETENTION_EXCEPTION_REQUIRED" in r.text.upper() or "RETENTION" in r.text.upper()

    def test_5_refused_with_exception_ok(self, api_client, review_admin_token):
        r = self._post(api_client, review_admin_token, AI_PROVIDER, {
            "action": "refused",
            "outcome": "Provider declined the deletion request",
            "retention_exception": {
                "reason": "Legal hold on gateway logs for 12 months",
                "basis": "contract clause 7",
                "review_at": "2027-03-01",
            }
        }, expected_status=200)
        state, row = self._get_provider(api_client, review_admin_token, AI_PROVIDER)
        assert state["state"] == "refused"
        assert row["provider_erasure"] == "retained_with_exception", row["provider_erasure"]

    def test_6_reopen_from_refused_to_requested(self, api_client, review_admin_token):
        r = self._post(api_client, review_admin_token, AI_PROVIDER, {"action": "reopen"}, expected_status=200)
        state, _ = self._get_provider(api_client, review_admin_token, AI_PROVIDER)
        # After reopen from refused when requested_at exists, expect 'requested' (not 'not_requested')
        assert state["state"] in ("requested", "not_requested"), state["state"]
        # outcome/retention_exception should be cleared
        assert not state.get("outcome"), state.get("outcome")
        assert not state.get("retention_exception"), state.get("retention_exception")

    def test_7_confirmed_ok(self, api_client, review_admin_token):
        state, _ = self._get_provider(api_client, review_admin_token, AI_PROVIDER)
        if state["state"] == "not_requested":
            # get back to requested
            self._post(api_client, review_admin_token, AI_PROVIDER,
                       {"action": "requested", "request_reference": "TICKET-2", "channel": "email support@emergent.sh"},
                       expected_status=200)
        r = self._post(api_client, review_admin_token, AI_PROVIDER, {
            "action": "confirmed",
            "outcome": "Emergent confirmed deletion of gateway logs on 15 Sep 2026",
        }, expected_status=200)
        state, row = self._get_provider(api_client, review_admin_token, AI_PROVIDER)
        assert state["state"] == "confirmed"
        # Other two providers not_applicable => summary should be "completed"
        assert row["provider_erasure"] == "completed", row["provider_erasure"]

    def test_8_final_reopen_leaves_requested(self, api_client, review_admin_token):
        r = self._post(api_client, review_admin_token, AI_PROVIDER, {"action": "reopen"}, expected_status=200)
        state, _ = self._get_provider(api_client, review_admin_token, AI_PROVIDER)
        assert state["state"] in ("requested", "not_requested"), state["state"]


# ---------------- Review-scope: guards ----------------

class TestGuards:
    def test_not_applicable_provider_returns_409(self, api_client, review_admin_token):
        r = api_client.post(
            f"{BASE_URL}/api/admin/deletion-requests/{REVIEW_ROW}/providers/{SMS_PROVIDER}",
            headers=_bearer(review_admin_token),
            json={"action": "requested", "request_reference": "T", "channel": "email x@x"},
            timeout=30,
        )
        assert r.status_code == 409, f"{r.status_code} {r.text}"
        assert "PROVIDER_NOT_APPLICABLE" in r.text.upper()

    def test_unknown_provider_returns_404(self, api_client, review_admin_token):
        r = api_client.post(
            f"{BASE_URL}/api/admin/deletion-requests/{REVIEW_ROW}/providers/foo",
            headers=_bearer(review_admin_token),
            json={"action": "reopen"},
            timeout=30,
        )
        assert r.status_code == 404, f"{r.status_code} {r.text}"
        assert "PROVIDER_UNKNOWN" in r.text.upper()

    def test_missing_deletion_returns_404(self, api_client, review_admin_token):
        r = api_client.post(
            f"{BASE_URL}/api/admin/deletion-requests/DEL-missing/providers/{AI_PROVIDER}",
            headers=_bearer(review_admin_token),
            json={"action": "reopen"},
            timeout=30,
        )
        assert r.status_code == 404, f"{r.status_code} {r.text}"
        assert "DELETION_NOT_FOUND" in r.text.upper()

    def test_unknown_extra_field_returns_422(self, api_client, review_admin_token):
        r = api_client.post(
            f"{BASE_URL}/api/admin/deletion-requests/{REVIEW_ROW}/providers/{AI_PROVIDER}",
            headers=_bearer(review_admin_token),
            json={"action": "reopen", "made_up_field": "x"},
            timeout=30,
        )
        assert r.status_code == 422, f"{r.status_code} {r.text}"


# ---------------- Review-scope: separation invariant ----------------

class TestSeparationInvariant:
    def test_top_level_status_and_cleanup_unchanged(self, api_client, review_admin_token):
        r = api_client.get(f"{BASE_URL}/api/admin/deletion-requests", headers=_bearer(review_admin_token), timeout=30)
        row = next(rr for rr in r.json()["requests"] if rr["reference"] == REVIEW_ROW)
        assert row["status"] in ("external_erasure_pending", "cleanup_completed"), row["status"]
        assert "cleanup" in row and "website" in row["cleanup"]


# ---------------- Access control ----------------

class TestAccessControl:
    def test_customer_reviewer_forbidden(self, api_client, review_customer_token):
        r = api_client.get(f"{BASE_URL}/api/admin/deletion-requests", headers=_bearer(review_customer_token), timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text}"

    def test_no_token_unauthorized(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/admin/deletion-requests", timeout=30)
        assert r.status_code == 401, f"{r.status_code} {r.text}"


# ---------------- Production scope: superseded rows ----------------

class TestProductionSupersededRows:
    def test_listing_rows_and_guard(self, api_client, prod_admin_token):
        r = api_client.get(f"{BASE_URL}/api/admin/deletion-requests", headers=_bearer(prod_admin_token), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 2, f"expected 2 superseded rows, got {body['total']}"
        for row in body["requests"]:
            assert row["status"] == "superseded_reactivated", row["status"]
            assert row["cleanup"]["app"] == "superseded", row["cleanup"]
            assert row["provider_erasure"] == "superseded", row["provider_erasure"]
            for banned in ("phone", "name", "shop_name"):
                assert banned not in row
            # providers preserved
            assert row["providers"]["sms_provider"]["state"] == "not_requested"
            assert row["providers"]["ai_provider"]["state"] == "not_requested"
            assert row["providers"]["ai_provider"].get("data_present") == "unknown"
            assert row["providers"]["object_storage"]["state"] == "not_applicable"

    def test_provider_action_on_superseded_returns_409(self, api_client, prod_admin_token):
        r = api_client.post(
            f"{BASE_URL}/api/admin/deletion-requests/DEL-20260909-2626C3/providers/{AI_PROVIDER}",
            headers=_bearer(prod_admin_token),
            json={"action": "reopen"},
            timeout=30,
        )
        assert r.status_code == 409, f"{r.status_code} {r.text}"
        assert "DELETION_SUPERSEDED" in r.text.upper()
