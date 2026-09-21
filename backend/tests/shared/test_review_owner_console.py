"""Owner console for store-review access: server-side owner authorisation, fresh OTP for every key operation,
keys shown once, hashes only, idempotent provisioning, explicit rotation/revocation. Isolated synthetic data,
intercepted SMS transport; no real number is ever messaged."""
import json

import pytest

from shared import core as c

pytestmark = pytest.mark.asyncio
OWNER = "9000000000"


def bearer(session):
    return {"Authorization": f"Bearer {session['token']}"}


async def fresh_otp(api_client, review_env, owner):
    """Owner asks for a fresh challenge; the OTP only ever exists in the intercepted transport and the hashed row."""
    # The 60 s per-phone cooldown protects real users; tests clear the previous challenge row to request again.
    await review_env["primary"].otp_challenges.delete_many({"phone": OWNER})
    res = await api_client.post("/api/admin/review/challenge", headers=bearer(owner))
    assert res.status_code == 200, res.text
    return review_env["sent_otps"][(OWNER, "review_keys")], res.json()["challenge_id"]


async def test_only_the_owner_in_production_scope_may_open_the_console(api_client, review_env, seeded_users, login_helper, monkeypatch):
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    owner = await login_helper(OWNER)
    ok = await api_client.get("/api/admin/review/status", headers=bearer(owner))
    assert ok.status_code == 200 and ok.json()["storage"] == "prefixed_collections" and ok.json()["isolation"] == "application_enforced"
    assert ok.json()["missing_accounts"] == ["store-review-customer", "store-review-admin", "store-review-telecaller", "store-review-telecaller-2", "store-review-billing", "store-review-upload"]
    # A second, non-owner administrator is refused server-side; so are staff and customers.
    await review_env["primary"].users.insert_one({"id": "u_admin2", "phone": "9000000099", "phone_normalized": "9000000099", "name": "Other Admin",
        "role": "admin", "account_status": "active", "status": "active", "session_version": 0, "onboarding_status": "completed", "phone_verified": True})
    other = await login_helper("9000000099")
    denied = await api_client.get("/api/admin/review/status", headers=bearer(other))
    assert denied.status_code == 403 and denied.json()["code"] == "OWNER_ADMIN_REQUIRED"
    assert (await api_client.post("/api/admin/review/challenge", headers=bearer(other))).status_code == 403
    assert (await api_client.get("/api/admin/review/status", headers=bearer(await login_helper("9000000001")))).status_code == 403
    assert (await api_client.get("/api/admin/review/status", headers=bearer(await login_helper("9000000004")))).status_code == 403
    assert (await api_client.get("/api/admin/review/status")).status_code == 401
    # Provision through the console, then prove the REVIEWER administrator cannot reach the console at all.
    otp, cid = await fresh_otp(api_client, review_env, owner)
    issued = await api_client.post("/api/admin/review/keys", json={"action": "provision", "otp": otp, "challenge_id": cid, "environment": "preview"},
                                   headers=bearer(owner))
    assert issued.status_code == 200, issued.text
    keys = {row["reviewer_id"]: row["access_key"] for row in issued.json()["issued"]}
    reviewer_admin = (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-admin", "access_key": keys["store-review-admin"]})).json()
    assert reviewer_admin["user"]["role"] == "admin"
    blocked = await api_client.get("/api/admin/review/status", headers=bearer(reviewer_admin))
    assert blocked.status_code == 403 and blocked.json()["code"] == "REVIEW_SCOPE_FORBIDDEN"
    assert (await api_client.post("/api/admin/review/challenge", headers=bearer(reviewer_admin))).status_code == 403
    assert (await api_client.post("/api/admin/review/keys", json={"action": "rotate", "reviewer_id": "store-review-admin", "otp": "0000"},
                                  headers=bearer(reviewer_admin))).status_code == 403


async def test_keys_need_a_fresh_single_use_otp_are_shown_once_and_never_rotate_implicitly(api_client, review_env, seeded_users, login_helper, monkeypatch):
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    owner = await login_helper(OWNER)
    review, prod = review_env["db"], review_env["primary"]
    # An admin session alone is not enough: no OTP -> validation error; wrong OTP -> refused; nothing provisioned.
    assert (await api_client.post("/api/admin/review/keys", json={"action": "provision"}, headers=bearer(owner))).status_code == 422
    otp, cid = await fresh_otp(api_client, review_env, owner)
    wrong = await api_client.post("/api/admin/review/keys", json={"action": "provision", "otp": f"{(int(otp) + 1) % 10000:04d}", "challenge_id": cid},
                                  headers=bearer(owner))
    assert wrong.status_code == 400 and wrong.json()["code"] == "OTP_INVALID"
    assert await review.review_accounts.count_documents({}) == 0
    # The OTP went through the PRODUCTION transport to the owner's own number only (never a reviewer phone).
    assert set(review_env["sent_otps"]) == {(OWNER, "login"), (OWNER, "review_keys")}  # owner's own number only
    assert await prod.otp_challenges.count_documents({"purpose": "review_keys", "subject": owner["user"]["id"]}) == 1
    assert await review.otp_challenges.count_documents({}) == 0
    # Correct OTP: all six accounts issued, plaintext shown once in the response body only.
    provisioned = await api_client.post("/api/admin/review/keys", json={"action": "provision", "otp": otp, "challenge_id": cid,
                                        "environment": "production", "api_base_url": "https://yash-tryon-test.emergent.host/api"}, headers=bearer(owner))
    assert provisioned.status_code == 200, provisioned.text
    body = provisioned.json()
    keys = {row["reviewer_id"]: row["access_key"] for row in body["issued"]}
    assert set(keys) == {"store-review-customer", "store-review-admin", "store-review-telecaller", "store-review-telecaller-2", "store-review-billing", "store-review-upload"}
    assert body["shown_once"] is True and body["unchanged"] == [] and body["dataset"]["products"] == 12
    assert "PRODUCTION" in body["note_text"] and "https://yash-tryon-test.emergent.host/api" in body["note_text"]
    assert all(k in body["note_text"] for k in keys.values()) and "Play Console" in body["note_text"]
    stored = {row["reviewer_id"]: row async for row in review.review_accounts.find({})}
    assert all(stored[rid]["secret_hash"].startswith("$2b$") and key not in json.dumps(stored[rid], default=str) for rid, key in keys.items())
    logs = json.dumps([row async for row in review.review_access_log.find({}, {"_id": 0})], default=str)
    assert not any(key in logs for key in keys.values()) and "owner_console_provision" in logs
    assert await prod.review_accounts.count_documents({}) == 0 and await prod.review_access_log.count_documents({}) == 0
    # The consumed OTP cannot be replayed.
    replay = await api_client.post("/api/admin/review/keys", json={"action": "provision", "otp": otp, "challenge_id": cid}, headers=bearer(owner))
    assert replay.status_code == 400 and replay.json()["code"] in {"OTP_INVALID", "OTP_USED"}
    # Every issued key signs in with the right role, signs out, is rejected afterwards and signs in AGAIN (reusable).
    for rid, role in (("store-review-customer", "customer"), ("store-review-admin", "admin"),
                      ("store-review-telecaller", "telecaller"), ("store-review-billing", "billing_executive")):
        first = await api_client.post("/api/auth/review/login", json={"reviewer_id": rid, "access_key": keys[rid]})
        assert first.status_code == 200 and first.json()["user"]["role"] == role and first.json()["review_environment"] is True
        assert (await api_client.get("/api/auth/me", headers=bearer(first.json()))).json()["role"] == role
        assert (await api_client.post("/api/auth/logout", headers=bearer(first.json()))).json() == {"logged_out": True}
        assert (await api_client.get("/api/auth/me", headers=bearer(first.json()))).status_code == 401
        again = await api_client.post("/api/auth/review/login", json={"reviewer_id": rid, "access_key": keys[rid]})
        assert again.status_code == 200 and again.json()["user"]["role"] == role
    # Opening the console and provisioning AGAIN never rotates: no key issued, hashes byte-identical, keys still valid.
    status = await api_client.get("/api/admin/review/status", headers=bearer(owner))
    assert status.status_code == 200 and all(a["exists"] and a["enabled"] for a in status.json()["accounts"]) and status.json()["missing_accounts"] == []
    otp2, cid2 = await fresh_otp(api_client, review_env, owner)
    again = await api_client.post("/api/admin/review/keys", json={"action": "provision", "otp": otp2, "challenge_id": cid2}, headers=bearer(owner))
    assert again.status_code == 200 and again.json()["issued"] == [] and again.json()["note_text"] is None
    assert sorted(again.json()["unchanged"]) == sorted(keys)
    assert {row["reviewer_id"]: row["secret_hash"] async for row in review.review_accounts.find({})} == {rid: row["secret_hash"] for rid, row in stored.items()}
    assert (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-admin", "access_key": keys["store-review-admin"]})).status_code == 200
    # Explicit rotation: old key and its live session die, the new key works; only that account changed.
    live = (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-telecaller", "access_key": keys["store-review-telecaller"]})).json()
    otp3, cid3 = await fresh_otp(api_client, review_env, owner)
    rotated = await api_client.post("/api/admin/review/keys", json={"action": "rotate", "reviewer_id": "store-review-telecaller", "otp": otp3, "challenge_id": cid3},
                                    headers=bearer(owner))
    assert rotated.status_code == 200 and [r["reviewer_id"] for r in rotated.json()["issued"]] == ["store-review-telecaller"]
    new_key = rotated.json()["issued"][0]["access_key"]
    assert new_key != keys["store-review-telecaller"] and "store-review-customer" in rotated.json()["unchanged"]
    assert (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-telecaller", "access_key": keys["store-review-telecaller"]})).status_code == 401
    assert (await api_client.get("/api/auth/me", headers=bearer(live))).status_code == 401
    assert (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-telecaller", "access_key": new_key})).status_code == 200
    assert (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-customer", "access_key": keys["store-review-customer"]})).status_code == 200
    # Revocation disables the account and its sessions; unknown reviewer ids are refused before the OTP is consumed.
    otp4, cid4 = await fresh_otp(api_client, review_env, owner)
    unknown = await api_client.post("/api/admin/review/keys", json={"action": "revoke", "reviewer_id": "store-review-owner", "otp": otp4, "challenge_id": cid4},
                                    headers=bearer(owner))
    assert unknown.status_code == 422 and unknown.json()["code"] == "UNKNOWN_REVIEWER"
    revoked = await api_client.post("/api/admin/review/keys", json={"action": "revoke", "reviewer_id": "store-review-telecaller", "otp": otp4, "challenge_id": cid4},
                                    headers=bearer(owner))
    assert revoked.status_code == 200 and revoked.json()["revoked"] == {"reviewer_id": "store-review-telecaller", "revoked": True}
    assert (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-telecaller", "access_key": new_key})).status_code == 401
    row = next(a for a in revoked.json()["accounts"] if a["reviewer_id"] == "store-review-telecaller")
    assert row["enabled"] is False and row["revoked_at"]
    # Health exposes the count only (no ids, no hashes).
    health = (await api_client.get("/api/health")).json()
    assert health["flows"]["review"]["accounts_enabled"] == 5


async def test_reset_sample_data_needs_fresh_otp_keeps_keys_and_signs_reviewers_out(api_client, review_env, seeded_users, login_helper, monkeypatch):
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    owner = await login_helper(OWNER)
    review, prod = review_env["db"], review_env["primary"]
    otp, cid = await fresh_otp(api_client, review_env, owner)
    keys = {row["reviewer_id"]: row["access_key"] for row in (await api_client.post("/api/admin/review/keys",
            json={"action": "provision", "otp": otp, "challenge_id": cid, "environment": "preview"}, headers=bearer(owner))).json()["issued"]}
    hashes = {row["reviewer_id"]: row["secret_hash"] async for row in review.review_accounts.find({})}
    customer = (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-customer", "access_key": keys["store-review-customer"]})).json()
    assert (await api_client.post("/api/ai/consent", json={"granted": True}, headers=bearer(customer))).json()["granted"] is True
    await review.requests.insert_one({"id": "review-request-extra", "user_id": "review-customer-0001", "status": "pending", "created_at": c.stamp()})
    await prod.requests.insert_one({"id": "genuine-request-1", "user_id": "u_cust1", "status": "pending", "created_at": c.stamp()})
    prod_before = {name: await prod[name].count_documents({}) for name in ("users", "requests", "products", "session_families", "refresh_tokens")}
    # No fresh OTP -> refused, nothing reset; reviewer administrators cannot reset either.
    stale = await api_client.post("/api/admin/review/keys", json={"action": "reset_data", "otp": otp, "challenge_id": cid}, headers=bearer(owner))
    assert stale.status_code == 400 and await review.requests.count_documents({"id": "review-request-extra"}) == 1
    reviewer_admin = (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-admin", "access_key": keys["store-review-admin"]})).json()
    assert (await api_client.post("/api/admin/review/keys", json={"action": "reset_data", "otp": "0000"}, headers=bearer(reviewer_admin))).status_code == 403
    otp2, cid2 = await fresh_otp(api_client, review_env, owner)
    reset = await api_client.post("/api/admin/review/keys", json={"action": "reset_data", "otp": otp2, "challenge_id": cid2}, headers=bearer(owner))
    assert reset.status_code == 200, reset.text
    assert reset.json()["issued"] == [] and reset.json()["note_text"] is None and reset.json()["reset"]["products"] == 12
    assert "keys are unchanged" in reset.json()["detail"] and all(a["exists"] and a["enabled"] for a in reset.json()["accounts"])
    # Only the allow-listed review__ collections were rebuilt; credentials identical; reviewer sessions gone; production untouched.
    assert await review.requests.count_documents({"id": "review-request-extra"}) == 0 and await review.requests.count_documents({}) == 8
    assert {row["reviewer_id"]: row["secret_hash"] async for row in review.review_accounts.find({})} == hashes
    assert (await api_client.get("/api/auth/me", headers=bearer(customer))).status_code == 401
    assert (await api_client.get("/api/auth/me", headers=bearer(reviewer_admin))).status_code == 401
    assert await review.session_families.count_documents({}) == 0 and await review.refresh_tokens.count_documents({}) == 0
    assert {name: await prod[name].count_documents({}) for name in prod_before} == prod_before
    assert await prod.requests.count_documents({"id": "genuine-request-1"}) == 1
    again = await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-customer", "access_key": keys["store-review-customer"]})
    assert again.status_code == 200 and again.json()["profile_recreated"] is False
    assert (await api_client.get("/api/ai/consent", headers=bearer(again.json()))).json()["granted"] is False  # consent did not survive the reset
    assert await review.review_access_log.count_documents({"event": "owner_console_reset_data"}) == 1


async def test_console_is_unavailable_when_review_access_is_disabled(api_client, isolated_db, seeded_users, login_helper, monkeypatch):
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    owner = await login_helper(OWNER)
    status = await api_client.get("/api/admin/review/status", headers=bearer(owner))
    assert status.status_code == 200 and status.json()["usable"] is False and status.json()["accounts"] == []
    assert status.json()["review_state"]["reason"] == "REVIEW_ACCESS_DISABLED"
    challenge = await api_client.post("/api/admin/review/challenge", headers=bearer(owner))
    assert challenge.status_code == 503 and challenge.json()["code"] == "REVIEW_UNAVAILABLE"
    assert (OWNER, "review_keys") not in isolated_db["sent_otps"]  # no SMS is sent when nothing can be provisioned
