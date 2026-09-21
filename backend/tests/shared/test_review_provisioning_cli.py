"""End-to-end owner provisioning command for store-review access, run as a real subprocess against
disposable databases (the isolated production double + a separate review copy).

Ephemeral keys are parsed in memory from the operator channel (stderr or the private note) and used
to sign in through the API; they are never printed or asserted by value. Also covers the bounded
review-scope AI assistant (provider mocked) and background-job scope isolation.
"""
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from shared import core as c
from shared import review_seed

pytestmark = pytest.mark.asyncio
BACKEND = Path("/app/backend")
TOOL = BACKEND / "tools/provision_review_access.py"
KEY_LINE = re.compile(r"^ONE-TIME ACCESS KEY\s+(\S+): (\S+)$", re.M)
ROLES = {"store-review-customer": "customer", "store-review-admin": "admin", "store-review-telecaller": "telecaller",
         "store-review-telecaller-2": "telecaller", "store-review-billing": "billing_executive", "store-review-upload": "upload_executive"}


def bearer(session):
    return {"Authorization": f"Bearer {session['token']}"}


def cli(review_env, *flags, env_overrides=None, expect_ok=True, expect_code=None):
    """Run the operator tool as a real subprocess. expect_code: 0 (stdout JSON), 1 (blocked, stderr JSON) or
    2 (verification failed/incomplete, stdout JSON). expect_ok is shorthand for 0 / 1."""
    code = expect_code if expect_code is not None else (0 if expect_ok else 1)
    env = {**os.environ, "DB_NAME": review_env["primary"].name, "REVIEW_ACCESS_ENABLED": "true"}
    env.pop("REVIEW_DB_NAME", None)
    env.update(env_overrides or {})
    proc = subprocess.run([sys.executable, str(TOOL), "--expected-db", env["DB_NAME"] or review_env["name"], *flags],
                          cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == code, (proc.returncode, proc.stderr[-400:].replace(review_env["name"], "<review-db>"))
    if code == 1:
        return json.loads(proc.stderr.strip().splitlines()[-1]), proc.stderr
    out = json.loads(proc.stdout)
    assert out["outcome"] == "ok" if code == 0 else out["outcome"] in {"verification_failed", "verification_incomplete"}
    assert "status" not in out or isinstance(out["status"], dict)  # the account-status table is never overwritten by the run result
    return out, proc.stderr


def keys_from(stderr):
    return dict(KEY_LINE.findall(stderr))


async def login(api_client, reviewer_id, key):
    return await api_client.post("/api/auth/review/login", json={"reviewer_id": reviewer_id, "access_key": key})


async def test_cli_provisions_seeds_reports_status_and_is_idempotent_on_repeat(api_client, review_env, seeded_users):
    out, err = cli(review_env, "--provision", "--seed", "--status")
    assert out["database"] == review_env["name"] and out["unprefixed_collections_untouched"] is True
    assert out["storage"] == "prefixed_collections" and out["isolation"] == "application_enforced"
    assert sorted(out["new_accounts"]) == sorted(ROLES)
    assert out["dataset"] == {"users": 12, "products": 12, "requests": 8, "rate_slabs": 6}
    keys = keys_from(err)
    assert set(keys) == set(ROLES) and all(len(k) >= 40 for k in keys.values())
    assert "secret_hash" not in json.dumps(out) and not any(k in out.__repr__() for k in keys.values())
    # Repeat run: no new accounts, no new keys, dataset unchanged, existing hashes untouched.
    before = {row["reviewer_id"]: row["secret_hash"] async for row in review_env["db"].review_accounts.find({})}
    again, err_again = cli(review_env, "--provision", "--seed")
    assert again["new_accounts"] == [] and keys_from(err_again) == {} and again["dataset"] == out["dataset"]
    after = {row["reviewer_id"]: row["secret_hash"] async for row in review_env["db"].review_accounts.find({})}
    assert after == before
    status, _ = cli(review_env, "--status")
    assert len(status["status"]["accounts"]) == 6 and all("secret_hash" not in a and a["enabled"] for a in status["status"]["accounts"])
    # Every role signs in through the API with the parsed key, refreshes, and is bound to the review scope.
    sessions = {}
    for reviewer_id, role in ROLES.items():
        res = await login(api_client, reviewer_id, keys[reviewer_id])
        assert res.status_code == 200, res.status_code
        assert res.json()["user"]["role"] == role and res.json()["review_environment"] is True
        refreshed = await api_client.post("/api/auth/refresh", json={"refresh_token": res.json()["refresh_token"]})
        assert refreshed.status_code == 200
        me = await api_client.get("/api/auth/me", headers=bearer(refreshed.json()))
        assert me.json()["role"] == role and me.json()["review_environment"] is True
        sessions[role] = refreshed.json()
    # Role permissions inside the review copy behave like production roles.
    assert (await api_client.get("/api/analytics/dashboard", headers=bearer(sessions["customer"]))).status_code == 403
    assert (await api_client.get("/api/customers?limit=5", headers=bearer(sessions["customer"]))).status_code == 403
    assert (await api_client.get("/api/analytics/dashboard", headers=bearer(sessions["admin"]))).status_code == 200
    assert (await api_client.post("/api/pdf-upload/init", json={"batch_id": "review-batch-1", "filename": "sample.pdf", "file_size": 2048,
                                  "sha256": "a" * 64, "total_chunks": 1}, headers=bearer(sessions["telecaller"]))).status_code == 403
    assert (await api_client.get("/api/customers/search?q=Sample", headers=bearer(sessions["billing_executive"]))).status_code == 200
    assert (await api_client.get("/api/rewards/history", headers=bearer(sessions["customer"]))).status_code == 200
    # The production double received nothing from any of this.
    prod = review_env["primary"]
    assert await prod.review_accounts.count_documents({}) == 0 and await prod.review_access_log.count_documents({}) == 0
    assert await prod.users.count_documents({"review_environment": True}) == 0 and await prod.products.count_documents({}) == 0
    assert await prod.users.count_documents({}) == len(seeded_users)


async def test_cli_fails_closed_on_missing_or_unsafe_review_configuration(review_env):
    for overrides, flags in (({"DB_NAME": ""}, ("--provision",)),
                             ({"DB_NAME": "SET_IN_PUBLISH_SECRETS"}, ("--provision",)),
                             ({"MONGO_URL": ""}, ("--status",))):
        blocked, _ = cli(review_env, *flags, env_overrides=overrides, expect_ok=False)
        assert blocked["outcome"] == "blocked" and blocked["error_type"] == "ValueError"
    mismatch = subprocess.run([sys.executable, str(TOOL), "--expected-db", "some_other_db", "--provision"], cwd=BACKEND,
                              env={**os.environ, "DB_NAME": review_env["primary"].name},
                              capture_output=True, text=True, timeout=120)
    assert mismatch.returncode == 1 and "does not match" in mismatch.stderr
    note_needs_env, _ = cli(review_env, "--provision", "--write-note", "/tmp/never-written.txt", expect_ok=False)
    assert "--environment" in note_needs_env["detail"]
    verify_needs_url, _ = cli(review_env, "--provision", "--verify", "--environment", "preview", expect_ok=False)
    assert "--api-base-url" in verify_needs_url["detail"]
    assert await review_env["db"].review_accounts.count_documents({}) == 0
    assert await review_env["primary"].review_accounts.count_documents({}) == 0
    assert not Path("/tmp/never-written.txt").exists()


async def test_cli_private_note_rotate_revoke_and_reset(api_client, review_env, tmp_path):
    private_dir = Path("/tmp") / f"yash-review-note-{uuid.uuid4().hex[:8]}"
    note = private_dir / "review-access.txt"
    out, err = cli(review_env, "--provision", "--seed", "--environment", "preview", "--api-base-url", "http://testserver/api",
                   "--write-note", str(note))
    try:
        assert keys_from(err) == {} and out["note_written"] == str(note)  # keys went ONLY to the private file
        text = note.read_text()
        assert stat.S_IMODE(note.stat().st_mode) == 0o600
        assert "PREVIEW" in text and "http://testserver/api" in text and review_env["name"] in text
        assert "Help" in text and "App review access" in text and "Store reviewer access" not in text and "App Store Connect" in text and "Play Console" in text
        keys = {m.group(1): m.group(2) for m in re.finditer(r"Reviewer ID: (\S+)\s+Role: .+?Access key: (\S+)$", text, re.M)}
        assert set(keys) == set(ROLES)
        for reviewer_id in ROLES:
            assert (await login(api_client, reviewer_id, keys[reviewer_id])).status_code == 200
        # A note is never written inside the repository or over an existing file — and the refusal happens
        # BEFORE any key is rotated, so the current admin key keeps working.
        inside, _ = cli(review_env, "--rotate", "store-review-admin", "--environment", "preview", "--write-note", "/app/leak.txt", expect_ok=False)
        assert "inside the repository" in inside["detail"] and not Path("/app/leak.txt").exists()
        overwrite, _ = cli(review_env, "--rotate", "store-review-admin", "--environment", "preview", "--write-note", str(note), expect_ok=False)
        assert overwrite["error_type"] == "FileExistsError"
        assert (await login(api_client, "store-review-admin", keys["store-review-admin"])).status_code == 200
        # Rotation to a fresh private note: old telecaller sessions and key die, only that key is in the new note.
        live = (await login(api_client, "store-review-telecaller", keys["store-review-telecaller"])).json()
        note2 = private_dir / "rotated.txt"
        rotated, err2 = cli(review_env, "--rotate", "store-review-telecaller", "--environment", "preview", "--write-note", str(note2))
        assert rotated["rotated"] == "store-review-telecaller" and keys_from(err2) == {}
        text2 = note2.read_text()
        new_keys = {m.group(1): m.group(2) for m in re.finditer(r"Reviewer ID: (\S+)\s+Role: .+?Access key: (\S+)$", text2, re.M)}
        assert set(new_keys) == {"store-review-telecaller"} and "store-review-customer" in text2 and "NOT changed" in text2
        assert (await login(api_client, "store-review-telecaller", keys["store-review-telecaller"])).status_code == 401
        assert (await api_client.get("/api/auth/me", headers=bearer(live))).status_code == 401
        fresh = await login(api_client, "store-review-telecaller", new_keys["store-review-telecaller"])
        assert fresh.status_code == 200
        # Revoke disables the account and its sessions; status reflects it; the hash stays private.
        revoked, _ = cli(review_env, "--revoke", "store-review-telecaller")
        assert revoked["revoked"] == {"reviewer_id": "store-review-telecaller", "revoked": True}
        assert (await login(api_client, "store-review-telecaller", new_keys["store-review-telecaller"])).status_code == 401
        assert (await api_client.get("/api/auth/me", headers=bearer(fresh.json()))).status_code == 401
        row = next(a for a in revoked["status"]["accounts"] if a["reviewer_id"] == "store-review-telecaller")
        assert row["enabled"] is False and row["revoked_at"] and "secret_hash" not in row
        # Reviewer-created data is wiped by --reset-data while accounts (and the customer's working key) survive.
        customer = (await login(api_client, "store-review-customer", keys["store-review-customer"])).json()
        created = await api_client.post("/api/requests", json={"request_type": "callback", "product_ids": ["review-product-0002"]},
                                        headers={**bearer(customer), "Idempotency-Key": "cli-reset-1"})
        assert created.status_code == 200
        reset, _ = cli(review_env, "--reset-data")
        assert reset["dataset"] == {"users": 12, "products": 12, "requests": 8, "rate_slabs": 6}
        assert await review_env["db"].requests.count_documents({"id": created.json()["id"]}) == 0
        assert (await login(api_client, "store-review-customer", keys["store-review-customer"])).status_code == 200
        assert (await api_client.get("/api/auth/me", headers=bearer(customer))).status_code == 401  # reset wiped sessions too
        # A rerun with --write-note when nothing new is issued writes no file (no stale key leaks).
        none, _ = cli(review_env, "--provision", "--environment", "preview", "--write-note", str(private_dir / "unused.txt"))
        assert none["note_written"] is None and not (private_dir / "unused.txt").exists()
    finally:
        for f in private_dir.glob("*"):
            f.unlink()
        private_dir.rmdir()


def test_verify_step_checks_role_scope_logout_and_session_reuse(monkeypatch):
    sys.path.insert(0, str(BACKEND / "tools"))
    import provision_review_access as tool
    import httpx

    calls, closed = [], set()

    class Response:
        def __init__(self, status, body):
            self.status_code, self._body = status, body
            self.headers = {"content-type": "application/json"}

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs.get("follow_redirects") is False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, json=None, headers=None):
            calls.append(("POST", url))
            if url.endswith("/auth/review/login"):
                tokens = {"store-review-admin": "t1", "store-review-billing": "t2", "store-review-telecaller": "t4"}
                roles = {"store-review-admin": "admin", "store-review-billing": "billing_executive", "store-review-telecaller": "telecaller"}
                if json["reviewer_id"] in tokens:
                    closed.discard(tokens[json["reviewer_id"]])  # a repeat sign-in opens a fresh session for the same token id
                    return Response(200, {"token": tokens[json["reviewer_id"]], "review_environment": True, "user": {"role": roles[json["reviewer_id"]]}})
                return Response(401, {"code": "REVIEW_CREDENTIALS_INVALID"})
            token = headers["Authorization"].split()[1]
            if token == "t4":
                return Response(503, {"code": "SERVICE_UNAVAILABLE"})  # logout intercepted/failing
            closed.add(token)
            return Response(200, {"logged_out": True})

        def get(self, url, headers=None):
            token = headers["Authorization"].split()[1]
            if token in closed:
                return Response(401, {"code": "SESSION_REVOKED"})
            roles = {"t1": "admin", "t2": "customer", "t4": "telecaller"}  # t2 = wrong role for billing
            return Response(200, {"role": roles[token], "review_environment": True})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    results = tool._verify_issued("https://backend.example/api/", {"store-review-admin": "k1", "store-review-billing": "k2",
                                                                    "store-review-customer": "k3", "store-review-telecaller": "k4"})
    assert results["store-review-admin"] == {"ok": True, "role": "admin", "review_environment": True, "session_closed": True, "repeat_login": True}
    assert results["store-review-billing"]["ok"] is False and results["store-review-billing"]["step"] == "role"
    assert results["store-review-customer"] == {"ok": False, "step": "login", "http_status": 401, "code": "REVIEW_CREDENTIALS_INVALID"}
    # A failed logout is never reported as a closed session or a PASS.
    assert results["store-review-telecaller"]["ok"] is False and results["store-review-telecaller"]["session_closed"] is False
    assert results["store-review-telecaller"]["step"] == "logout" and results["store-review-telecaller"]["http_status"] == 503
    assert all(url.startswith("https://backend.example/api/") for _, url in calls)
    dumped = json.dumps(results)
    assert "k1" not in dumped and "k2" not in dumped and "k4" not in dumped
    # Only an explicit https /api origin (or a loopback test server) may receive keys.
    for bad in ("http://backend.example/api", "https://backend.example/", "https://backend.example/api?x=1",
                "https://user:pw@backend.example/api", "ftp://backend.example/api", "https://backend.example/api#f"):
        with pytest.raises(ValueError):
            tool._validate_target(bad)
    assert tool._validate_target("https://backend.example/api/") == "https://backend.example/api"
    assert tool._validate_target("http://127.0.0.1:8001/api") == "http://127.0.0.1:8001/api"


def test_verify_note_recovery_appends_results_without_mutation(monkeypatch, tmp_path):
    sys.path.insert(0, str(BACKEND / "tools"))
    import provision_review_access as tool
    import httpx

    class Response:
        def __init__(self, status, body):
            self.status_code, self._body, self.headers = status, body, {"content-type": "application/json"}

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, **_): self.closed = set()
        def __enter__(self): return self
        def __exit__(self, *_): return False

        def post(self, url, json=None, headers=None):
            if url.endswith("/auth/review/login"):
                self.closed.discard("Bearer tok-" + json["reviewer_id"])
                return Response(200, {"token": "tok-" + json["reviewer_id"], "review_environment": True,
                                      "user": {"role": "customer" if "customer" in json["reviewer_id"] else "admin"}})
            self.closed.add(headers["Authorization"])
            return Response(200, {"logged_out": True})

        def get(self, url, headers=None):
            if headers["Authorization"] in self.closed:
                return Response(401, {})
            return Response(200, {"role": "customer" if "customer" in headers["Authorization"] else "admin", "review_environment": True})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    note = tmp_path / "note.txt"
    note.write_text("\n".join(tool._note_lines("production", "https://backend.example/api", "rev_db",
                                               {"store-review-customer": "key-c-000000000000000000000000000",
                                                "store-review-admin": "key-a-000000000000000000000000000"}, [], None,
                                               verification_error="ConnectError while contacting https://backend.example/api")))
    assert "NOT COMPLETED" in note.read_text() and "--verify-note" in note.read_text()
    # The note's own header pins environment + review database + BACKEND: mismatches are refused before any request.
    with pytest.raises(ValueError, match="issued for PRODUCTION"):
        tool._verify_note(str(note), "https://backend.example/api", "preview", "rev_db")
    with pytest.raises(ValueError, match="database differs"):
        tool._verify_note(str(note), "https://backend.example/api", "production", "other_db")
    for other in ("https://other.example/api", "https://backend.example:8443/api", "http://backend.example/api", "https://backend.example/api/v2"):
        with pytest.raises(ValueError, match="pins backend"):
            tool._verify_note(str(note), other, "production", "rev_db")
    assert "VERIFICATION RE-RUN" not in note.read_text()  # a refused pre-flight leaves the note untouched
    # Equivalent spellings of the same target are accepted: explicit default port, trailing slash, host case.
    assert tool._target_identity("https://Backend.Example:443/api/") == tool._target_identity("https://backend.example/api")
    checked = tool._verify_note(str(note), "https://backend.example/api", "production", "rev_db")
    assert checked["error"] is None and checked["accounts"] == ["store-review-admin", "store-review-customer"]
    assert checked["results"] == {"store-review-customer": {"ok": True, "role": "customer", "review_environment": True, "session_closed": True, "repeat_login": True},
                                  "store-review-admin": {"ok": True, "role": "admin", "review_environment": True, "session_closed": True, "repeat_login": True}}
    text = note.read_text()
    assert "VERIFICATION RE-RUN" in text and text.count("PASS") == 2 and "key-c-000000000000000000000000000" in text
    # A note that never recorded its backend cannot be verified against any target (strict, exit 1 in the CLI).
    unpinned = tmp_path / "unpinned.txt"
    unpinned.write_text("\n".join(tool._note_lines("production", "", "rev_db", {"store-review-admin": "key-a-000000000000000000000000000"}, [], None)))
    assert "Backend: (not recorded)" in unpinned.read_text()
    with pytest.raises(ValueError, match="does not record the backend"):
        tool._verify_note(str(unpinned), "https://backend.example/api", "production", "rev_db")
    # Transport failure AFTER a valid pre-flight: sanitized NOT COMPLETED entry, no results, error type only.
    class DeadClient(FakeClient):
        def post(self, url, json=None, headers=None):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "Client", DeadClient)
    dead = tool._verify_note(str(note), "https://backend.example/api", "production", "rev_db")
    assert dead["results"] is None and dead["error"] == "ConnectError"
    tail = note.read_text().splitlines()[-2:]
    assert "NOT COMPLETED - ConnectError while contacting https://backend.example/api" in tail[0] and "re-run the same --verify-note" in tail[1]
    assert "connection refused" not in note.read_text()


@pytest.fixture
def live_server(review_env):
    """The real backend as a separate HTTP process bound to the disposable production double + review copy,
    so the CLI's --verify/--verify-note exercise genuine network sign-in, /auth/me, sign-out and reuse checks."""
    import socket
    import time
    import httpx

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "DB_NAME": review_env["primary"].name, "REVIEW_ACCESS_ENABLED": "true"}
    env.pop("REVIEW_DB_NAME", None)
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
            assert proc.poll() is None, "backend process exited during startup"
            time.sleep(0.5)
        else:
            pytest.fail("live backend did not start")
        assert httpx.get(f"{base}/health", timeout=5).json()["flows"]["review"]["ready"] is True
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


async def test_cli_verify_against_live_backend_returns_strict_exit_codes(review_env, live_server, api_client):
    """Exit 0 only when EVERY issued key is proven end-to-end; 2 when verification fails or cannot complete;
    keys are never lost on a failed verification and production issuance never prints them."""
    private_dir = Path("/tmp") / f"yash-review-live-{uuid.uuid4().hex[:8]}"
    note1, note2, note3 = (private_dir / n for n in ("issued.txt", "rotated-offline.txt", "nothing-issued.txt"))
    dead_port_url = "http://127.0.0.1:9/api"  # discard port: connection refused, never a redirect or a server
    try:
        # Production issuance without a private note is refused before any account exists.
        refused, _ = cli(review_env, "--provision", "--environment", "production", expect_ok=False)
        assert "requires --write-note" in refused["detail"]
        assert await review_env["db"].review_accounts.count_documents({}) == 0
        # Full path: provision + seed + verify against the live HTTP backend -> exit 0, every reviewer account proven.
        out, err = cli(review_env, "--provision", "--seed", "--status", "--environment", "production", "--api-base-url", live_server,
                       "--verify", "--write-note", str(note1))
        assert out["outcome"] == "ok" and out["verified_all"] is True and out["all_accounts_verified"] is True
        assert sorted(out["verified_accounts"]) == sorted(ROLES) and out["issued_accounts"] == sorted(ROLES)
        assert all(r == {"ok": True, "role": ROLES[rid], "review_environment": True, "session_closed": True, "repeat_login": True} for rid, r in out["verification"].items())
        assert len(out["status"]["accounts"]) == 6  # account table survives beside the run outcome
        assert keys_from(err) == {} and "ONE-TIME" not in err
        text1 = note1.read_text()
        keys = {m.group(1): m.group(2) for m in re.finditer(r"Reviewer ID: (\S+)\s+Role: .+?Access key: (\S+)$", text1, re.M)}
        assert set(keys) == set(ROLES) and "PRODUCTION" in text1 and text1.count("PASS") == 6 and "FAIL" not in text1
        assert not any(k in json.dumps(out) for k in keys.values())
        # Every verification session was closed on the server: the audit shows logins and logouts, no live sessions leak.
        assert await review_env["db"].review_access_log.count_documents({"event": "review_login_succeeded", "success": True}) == 12  # sign-in + repeat sign-in per reviewer account (6 accounts)
        # Recovery re-verification of the stored note against the live backend: exit 0, results appended, nothing mutated.
        before = {row["reviewer_id"]: row["secret_hash"] async for row in review_env["db"].review_accounts.find({})}
        again, _ = cli(review_env, "--verify-note", str(note1), "--environment", "production", "--api-base-url", live_server)
        assert again["verified_all"] is True and again["note_updated"] == str(note1) and "VERIFICATION RE-RUN" in note1.read_text()
        assert {row["reviewer_id"]: row["secret_hash"] async for row in review_env["db"].review_accounts.find({})} == before
        wrong_env, _ = cli(review_env, "--verify-note", str(note1), "--environment", "preview", "--api-base-url", live_server, expect_ok=False)
        assert "issued for PRODUCTION" in wrong_env["detail"]
        mixed, _ = cli(review_env, "--verify-note", str(note1), "--provision", "--environment", "production", "--api-base-url", live_server, expect_ok=False)
        assert "read-only" in mixed["detail"]
        # A revoked account makes the recorded verification FAIL -> exit 2, never a silent PASS.
        cli(review_env, "--revoke", "store-review-telecaller")
        # Test convenience only: three verification runs (6 accounts x 2 sign-ins each) within one minute would trip the
        # per-IP brute-force limit of the reviewer login (30/min); the limit itself is asserted in test_review_access_isolation.
        await review_env["db"].otp_limits.delete_many({})
        failed, _ = cli(review_env, "--verify-note", str(note1), "--environment", "production", "--api-base-url", live_server, expect_code=2)
        assert failed["outcome"] == "verification_failed" and failed["verified_all"] is False
        assert failed["verification"]["store-review-telecaller"] == {"ok": False, "step": "login", "http_status": 401, "code": "REVIEW_CREDENTIALS_INVALID"}
        assert sorted(failed["verified_accounts"]) == sorted(set(ROLES) - {"store-review-telecaller"})
        assert re.search(r"store-review-telecaller\s+FAIL\s+\{.*\"step\": \"login\"", note1.read_text())
        # Transport failure during --verify: the rotated key is already in the note (marked NOT COMPLETED), exit 2,
        # and the key itself works - proving nothing was lost.
        incomplete, err2 = cli(review_env, "--rotate", "store-review-admin", "--environment", "production", "--api-base-url", dead_port_url,
                               "--verify", "--write-note", str(note2), expect_code=2)
        assert incomplete["outcome"] == "verification_incomplete" and incomplete["verification_error"] == "ConnectError"
        assert incomplete["rotated"] == "store-review-admin" and incomplete["verified_accounts"] == [] and keys_from(err2) == {}
        text2 = note2.read_text()
        assert "NOT COMPLETED" in text2 and "ConnectError" in text2 and "--verify-note" in text2 and stat.S_IMODE(note2.stat().st_mode) == 0o600
        new_admin = re.search(r"Reviewer ID: store-review-admin\s+Role: .+?Access key: (\S+)$", text2, re.M).group(1)
        assert new_admin != keys["store-review-admin"]
        assert (await login(api_client, "store-review-admin", new_admin)).status_code == 200
        assert (await login(api_client, "store-review-admin", keys["store-review-admin"])).status_code == 401
        # STRICT PRE-FLIGHT: note2 pins the dead backend. Asking --verify-note to use the live server (same host, other
        # port) is a different target -> exit 1 BEFORE any request: no sign-in reaches the server, the note is untouched.
        attempts_before = await review_env["db"].review_access_log.count_documents({"reviewer_id": "store-review-admin"})
        elsewhere, _ = cli(review_env, "--verify-note", str(note2), "--environment", "production", "--api-base-url", live_server, expect_ok=False)
        assert elsewhere["outcome"] == "blocked" and "pins backend" in elsewhere["detail"] and new_admin not in json.dumps(elsewhere)
        assert await review_env["db"].review_access_log.count_documents({"reviewer_id": "store-review-admin"}) == attempts_before
        assert "VERIFICATION RE-RUN" not in note2.read_text()
        # Same pinned target, still unreachable: valid pre-flight, transport failure -> exit 2 (INCOMPLETE, not blocked)
        # and a sanitized NOT COMPLETED entry appended to the note (error type only, no key, no payload).
        still_down, _ = cli(review_env, "--verify-note", str(note2), "--environment", "production", "--api-base-url", dead_port_url, expect_code=2)
        assert still_down["outcome"] == "verification_incomplete" and still_down["verification_error"] == "ConnectError"
        assert "verification" not in still_down and still_down["issued_accounts"] == ["store-review-admin"] and still_down["verified_accounts"] == []
        text2b = note2.read_text()
        assert f"VERIFICATION RE-RUN" in text2b and f"NOT COMPLETED - ConnectError while contacting {dead_port_url}" in text2b
        assert text2b.count(new_admin) == 1  # the key line is never repeated into the verification log
        # --verify with nothing issued cannot prove anything: exit 2 (incomplete) and no note file is left behind.
        nothing, _ = cli(review_env, "--provision", "--environment", "production", "--api-base-url", live_server, "--verify",
                         "--write-note", str(note3), expect_code=2)
        assert nothing["outcome"] == "verification_incomplete" and "verification_skipped" in nothing and not note3.exists()
    finally:
        for f in private_dir.glob("*"):
            f.unlink()
        if private_dir.exists():
            private_dir.rmdir()


async def test_review_ai_assistant_is_genuine_but_bounded_and_isolated(api_client, review_env, seeded_users, login_helper, monkeypatch):
    import emergentintegrations.llm.chat as chat_module

    sent = []

    class FakeChat:
        def __init__(self, api_key, session_id, system_message):
            self._messages, self.session_id = [], session_id

        def with_model(self, provider, model):
            sent.append(("model", provider, model))
            return self

        async def send_message(self, message):
            sent.append(("message", self.session_id, message.text))
            return "Synthetic assistant reply: pitch silver payal by weight and purity."

    monkeypatch.setattr(chat_module, "LlmChat", FakeChat)
    with c.scoped(c.REVIEW):
        await review_seed.seed_dataset()
        keys = await review_seed.provision_accounts()
    customer = (await login(api_client, "store-review-customer", keys["store-review-customer"])).json()
    # Consent gate applies to reviewers too (they grant it on synthetic data); nothing reaches the provider before it.
    gated = await api_client.post("/api/ai/chat", json={"message": "How do I pitch silver payal?"}, headers=bearer(customer))
    assert gated.status_code == 403 and gated.json()["code"] == "AI_CONSENT_REQUIRED" and sent == []
    assert (await api_client.post("/api/ai/consent", json={"granted": True}, headers=bearer(customer))).json()["granted"] is True
    assert await review_env["primary"].users.count_documents({"ai_consent.granted": True}) == 0  # consent recorded in review scope only
    reply = await api_client.post("/api/ai/chat", json={"message": "How do I pitch silver payal?"}, headers=bearer(customer))
    assert reply.status_code == 200 and reply.json()["response"].startswith("Synthetic assistant reply") and not reply.json().get("error")
    assert sent[-1][0] == "message" and sent[-1][2] == "How do I pitch silver payal?"
    assert "review-customer-0001" not in sent[-1][1] and sent[-1][1].startswith("yt-")  # provider sees a keyed pseudonym only
    assert await review_env["db"].ai_chat_history.count_documents({"user_id": "review-customer-0001"}) == 2
    assert await review_env["primary"].ai_chat_history.count_documents({}) == 0
    # Bounded: over-long prompts and the daily budget stop before the provider is called.
    calls_before = len(sent)
    long = await api_client.post("/api/ai/chat", json={"message": "x" * 601}, headers=bearer(customer))
    assert long.json()["error"] is True and long.json()["review_limit"] == "message_length" and len(sent) == calls_before
    today = c.now().strftime("%Y-%m-%dT00:00:01")
    await review_env["db"].ai_chat_history.insert_many([{"id": f"cap-{n}", "user_id": "review-customer-0001", "session_id": "jeweller-review-customer-0001",
                                                          "role": "user", "content": "cap", "created_at": today} for n in range(39)])
    capped = await api_client.post("/api/ai/chat", json={"message": "one more"}, headers=bearer(customer))
    assert capped.json()["error"] is True and capped.json()["review_limit"] == "daily_messages" and len(sent) == calls_before
    # Production sessions are not subject to the review budget and keep their own history.
    real = await login_helper("9000000005")
    await api_client.post("/api/ai/consent", json={"granted": True}, headers=bearer(real))
    real_reply = await api_client.post("/api/ai/chat", json={"message": "y" * 700}, headers=bearer(real))
    assert real_reply.status_code == 200 and not real_reply.json().get("error") and len(sent) == calls_before + 2
    assert await review_env["primary"].ai_chat_history.count_documents({"user_id": real["user"]["id"]}) == 2
    assert await review_env["db"].ai_chat_history.count_documents({"user_id": real["user"]["id"]}) == 0


async def test_review_background_jobs_and_workers_stay_in_review_scope(api_client, review_env, seeded_users, login_helper):
    with c.scoped(c.REVIEW):
        await review_seed.seed_dataset()
        keys = await review_seed.provision_accounts()
    assert c.scopes() == [None, c.REVIEW]  # workers serve production first, then the review copy, each inside its own scope
    admin = (await login(api_client, "store-review-admin", keys["store-review-admin"])).json()
    init = await api_client.post("/api/pdf-upload/init", json={"batch_id": "review-batch-1", "filename": "review-sample.pdf", "file_size": 4096,
                                 "sha256": "b" * 64, "total_chunks": 1}, headers=bearer(admin))
    assert init.status_code == 200, init.text
    jid = init.json()["upload_id"]
    assert await review_env["db"].import_jobs.count_documents({"id": jid}) == 1
    assert await review_env["primary"].import_jobs.count_documents({}) == 0
    real_admin = await login_helper("9000000000")
    assert (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=bearer(real_admin))).status_code == 404
    assert (await api_client.get(f"/api/pdf-upload/{jid}/status", headers=bearer(admin))).status_code == 200
    # Media accounting for a review admin reads only review-scope assets and reports the provider's real capability.
    usage = await api_client.get("/api/admin/media/usage", headers=bearer(admin))
    assert usage.status_code == 200 and usage.json()["provider_delete_supported"] is False
    audit = await api_client.post("/api/admin/media/lifecycle-audit", headers=bearer(admin))
    assert audit.status_code == 200 and audit.json()["remote_deletions"] == 0
    assert await review_env["primary"].media_assets.count_documents({"deletion_checked_at": {"$exists": True}}) == 0
    with c.scoped(c.REVIEW):
        await review_seed.seed_dataset(reset=True)
    assert await review_env["db"].import_jobs.count_documents({}) == 0
