"""Bootstrap placeholders (e.g. SET_IN_PUBLISH_SECRETS) declared in backend/.env so the platform registers the
key NAME must behave as ABSENT configuration in executable code: they never become a review database handle,
never pass as a staff credential and never appear as a verified deployment commit. Proven against the real
backend process started with placeholder values, plus the operator CLI."""
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest
from pymongo import MongoClient

BACKEND = Path("/app/backend")
TOOL = BACKEND / "tools/provision_review_access.py"
PLACEHOLDER = "SET_IN_PUBLISH_SECRETS"


@pytest.fixture
def placeholder_server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    primary = f"bootstrap_primary_{uuid.uuid4().hex[:8]}"
    env = {**os.environ, "DB_NAME": primary, "REVIEW_DB_NAME": PLACEHOLDER, "STAFF_SERVICE_KEY": PLACEHOLDER,
           "BUILD_COMMIT": PLACEHOLDER}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}/api"
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{base}/health/live", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert proc.poll() is None, "backend exited during startup with placeholder configuration"
            time.sleep(0.5)
        else:
            pytest.fail("backend did not start")
        yield base, primary
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        MongoClient(os.environ["MONGO_URL"]).drop_database(primary)


def test_placeholder_values_are_unconfigured_in_the_running_backend(placeholder_server):
    base, primary = placeholder_server
    health = httpx.get(f"{base}/health", timeout=10)
    body = health.json()
    assert health.status_code == 503 and body["ready"] is False
    assert body["flows"]["review"] == {"ready": False, "issues": ["REVIEW_DB_NAME"], "optional": True}
    assert "STAFF_SERVICE_KEY" in body["flows"]["staff"]["issues"] and body["flows"]["staff"]["ready"] is False
    assert body["configuration"]["REVIEW_DB_NAME"] is False and body["configuration"]["BUILD_COMMIT"] is False
    assert body["commit"] == "unrecorded" and PLACEHOLDER not in json.dumps(body)
    # Readiness never claims what it has not exercised.
    assert body["sms_delivery_verified"] is False and body["account_role_verified"] is False
    # Reviewer sign-in is refused outright (no fallback to production data), with no database access attempted.
    login = httpx.post(f"{base}/auth/review/login", json={"reviewer_id": "store-review-admin", "access_key": "x" * 40}, timeout=10)
    assert login.status_code == 503 and login.json()["code"] == "REVIEW_UNAVAILABLE"
    # The placeholder is not a usable staff credential either.
    staff = httpx.post(f"{base}/auth/send-otp", json={"phone": "9999813334", "channel": "portal", "purpose": "login"},
                       headers={"X-Staff-Service-Key": PLACEHOLDER}, timeout=10)
    assert staff.status_code == 503 and staff.json()["code"] == "CONFIGURATION_REQUIRED"
    names = MongoClient(os.environ["MONGO_URL"]).list_database_names()
    assert PLACEHOLDER not in names and not any(PLACEHOLDER.lower() in n.lower() for n in names)


def test_cli_refuses_placeholder_review_database_before_touching_mongo():
    primary = f"bootstrap_cli_{uuid.uuid4().hex[:8]}"
    env = {**os.environ, "DB_NAME": primary, "REVIEW_DB_NAME": PLACEHOLDER}
    proc = subprocess.run([sys.executable, str(TOOL), "--expected-review-db", PLACEHOLDER, "--provision", "--seed", "--status"],
                          cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 1 and proc.stdout == ""
    blocked = json.loads(proc.stderr.strip().splitlines()[-1])
    assert blocked["outcome"] == "blocked" and "placeholder" in blocked["detail"].lower()
    names = MongoClient(os.environ["MONGO_URL"]).list_database_names()
    assert PLACEHOLDER not in names and primary not in names
