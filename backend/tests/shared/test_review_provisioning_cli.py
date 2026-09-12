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
ROLES = {"store-review-customer": "customer", "store-review-admin": "admin",
         "store-review-telecaller": "telecaller", "store-review-billing": "billing_executive"}


def bearer(session):
    return {"Authorization": f"Bearer {session['token']}"}


def cli(review_env, *flags, env_overrides=None, expect_ok=True):
    env = {**os.environ, "DB_NAME": review_env["primary"].name, "REVIEW_DB_NAME": review_env["name"]}
    env.update(env_overrides or {})
    proc = subprocess.run([sys.executable, str(TOOL), "--expected-review-db", env["REVIEW_DB_NAME"] or review_env["name"], *flags],
                          cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    if expect_ok:
        assert proc.returncode == 0, proc.stderr[-400:].replace(review_env["name"], "<review-db>")
        return json.loads(proc.stdout), proc.stderr
    assert proc.returncode == 1
    return json.loads(proc.stderr.strip().splitlines()[-1]), proc.stderr


def keys_from(stderr):
    return dict(KEY_LINE.findall(stderr))


async def login(api_client, reviewer_id, key):
    return await api_client.post("/api/auth/review/login", json={"reviewer_id": reviewer_id, "access_key": key})


async def test_cli_provisions_seeds_reports_status_and_is_idempotent_on_repeat(api_client, review_env, seeded_users):
    out, err = cli(review_env, "--provision", "--seed", "--status")
    assert out["review_db"] == review_env["name"] and out["primary_db_untouched"] is True
    assert sorted(out["new_accounts"]) == sorted(ROLES)
    assert out["dataset"] == {"users": 10, "products": 12, "requests": 8, "rate_slabs": 6}
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
    assert len(status["status"]["accounts"]) == 4 and all("secret_hash" not in a and a["enabled"] for a in status["status"]["accounts"])
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
    for overrides, flags in (({"REVIEW_DB_NAME": ""}, ("--provision",)),
                             ({"REVIEW_DB_NAME": review_env["primary"].name}, ("--provision",)),
                             ({"MONGO_URL": ""}, ("--status",))):
        blocked, _ = cli(review_env, *flags, env_overrides=overrides, expect_ok=False)
        assert blocked["status"] == "blocked" and blocked["error_type"] == "ValueError"
    mismatch = subprocess.run([sys.executable, str(TOOL), "--expected-review-db", "some_other_db", "--provision"], cwd=BACKEND,
                              env={**os.environ, "DB_NAME": review_env["primary"].name, "REVIEW_DB_NAME": review_env["name"]},
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
        assert "Store reviewer access" in text and "App Store Connect" in text and "Play Console" in text
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
        assert reset["dataset"] == {"users": 10, "products": 12, "requests": 8, "rate_slabs": 6}
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


def test_verify_step_checks_role_scope_and_closes_the_session(monkeypatch):
    sys.path.insert(0, str(BACKEND / "tools"))
    import provision_review_access as tool
    import httpx

    calls = []

    class Response:
        def __init__(self, status, body):
            self.status_code, self._body = status, body
            self.headers = {"content-type": "application/json"}

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, json=None, headers=None):
            calls.append(("POST", url.rsplit("/", 2)[-2:], bool(headers)))
            if url.endswith("/auth/review/login"):
                if json["reviewer_id"] == "store-review-admin":
                    return Response(200, {"token": "t1", "review_environment": True})
                if json["reviewer_id"] == "store-review-billing":
                    return Response(200, {"token": "t2", "review_environment": True})
                return Response(401, {"code": "REVIEW_CREDENTIALS_INVALID"})
            return Response(200, {"logged_out": True})

        def get(self, url, headers=None):
            if headers["Authorization"] == "Bearer t1":
                return Response(200, {"role": "admin", "review_environment": True})
            return Response(200, {"role": "customer", "review_environment": True})  # wrong role for billing

    monkeypatch.setattr(httpx, "Client", FakeClient)
    results = tool._verify_issued("https://backend.example/api/", {"store-review-admin": "k1", "store-review-billing": "k2", "store-review-customer": "k3"})
    assert results["store-review-admin"] == {"ok": True, "role": "admin", "review_environment": True, "session_closed": True}
    assert results["store-review-billing"]["ok"] is False and results["store-review-billing"]["role"] == "customer"
    assert results["store-review-customer"] == {"ok": False, "step": "login", "http_status": 401, "code": "REVIEW_CREDENTIALS_INVALID"}
    assert ("POST", ["auth", "logout"], True) in calls and calls.count(("POST", ["auth", "logout"], True)) == 2
    assert "k1" not in json.dumps(results) and "k2" not in json.dumps(results)


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
    reply = await api_client.post("/api/ai/chat", json={"message": "How do I pitch silver payal?"}, headers=bearer(customer))
    assert reply.status_code == 200 and reply.json()["response"].startswith("Synthetic assistant reply") and not reply.json().get("error")
    assert sent[-1] == ("message", "jeweller-review-customer-0001", "How do I pitch silver payal?")
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
    real_admin = await login_helper("9999813334")
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
