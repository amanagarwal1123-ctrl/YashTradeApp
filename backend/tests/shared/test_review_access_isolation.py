"""Store-review access isolation: reviewer accounts live ONLY in the `review__*` collections (application-enforced).

Every assertion runs against isolated synthetic databases with intercepted transports. The
production double is `isolated_db`/`seeded_users`; the review copy is `review_env`. No real SMS,
storage write or production record is involved.
"""
import io

import jwt
import pytest
from PIL import Image

from shared import core as c
from shared import review_seed

pytestmark = pytest.mark.asyncio
WEBSITE_KEY = {"X-Integration-Key": "integration-key-1234567890-abcdef"}


def bearer(session):
    return {"Authorization": f"Bearer {session['token']}"}


async def provision(review_env):
    with c.scoped(c.REVIEW):
        await review_seed.seed_dataset()
        return await review_seed.provision_accounts()


async def review_login(api_client, reviewer_id, key):
    return await api_client.post("/api/auth/review/login", json={"reviewer_id": reviewer_id, "access_key": key})


async def test_review_login_is_denied_when_review_access_is_disabled(api_client, isolated_db):
    res = await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-admin", "access_key": "x" * 43})
    assert res.status_code == 503 and res.json()["code"] == "REVIEW_UNAVAILABLE"
    health = await api_client.get("/api/health")
    review = health.json()["flows"]["review"]
    assert review["ready"] is False and review["issues"] == ["REVIEW_ACCESS_DISABLED"] and review["optional"] is True
    assert review["enabled"] is False and review["usable"] is False and review["storage"] == "prefixed_collections"
    assert review["isolation"] == "application_enforced" and review["accounts_enabled"] is None
    assert health.json()["configuration"]["REVIEW_ACCESS_ENABLED"] is False and health.json()["configuration"]["REVIEW_STORAGE_USABLE"] is False
    # The optional review flow never blocks production readiness.
    assert "review" not in [n for n, f in health.json()["flows"].items() if not f["ready"] and n != "review"]


async def test_reviewer_roles_come_from_server_side_accounts_only(api_client, review_env, seeded_users):
    keys = await provision(review_env)
    assert set(keys) == {"store-review-customer", "store-review-admin", "store-review-telecaller", "store-review-billing"}
    for reviewer_id, role in (("store-review-customer", "customer"), ("store-review-admin", "admin"),
                              ("store-review-telecaller", "telecaller"), ("store-review-billing", "billing_executive")):
        res = await review_login(api_client, reviewer_id, keys[reviewer_id])
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["user"]["role"] == role and body["user"]["review_environment"] is True and body["review_environment"] is True
        assert "synthetic" in body["notice"]
        me = await api_client.get("/api/auth/me", headers=bearer(body))
        assert me.status_code == 200 and me.json()["role"] == role and me.json()["review_environment"] is True
        assert jwt.decode(body["token"], options={"verify_signature": False})["scope"] == "review"
    # Wrong key, unknown reviewer and a role claim in the body are all rejected identically.
    wrong = await review_login(api_client, "store-review-admin", "not-the-right-key-1234567890abcd")
    assert wrong.status_code == 401 and wrong.json()["code"] == "REVIEW_CREDENTIALS_INVALID"
    unknown = await review_login(api_client, "store-review-owner", "not-the-right-key-1234567890abcd")
    assert unknown.status_code == 401 and unknown.json()["detail"] == wrong.json()["detail"]
    spoof = await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-customer",
                                  "access_key": keys["store-review-customer"], "role": "admin"})
    assert spoof.status_code == 422
    assert (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-admin", "access_key": "short"})).status_code == 422
    # Hashes only; audit rows only in the review database; production has no review artefacts.
    stored = await review_env["db"].review_accounts.find_one({"reviewer_id": "store-review-admin"})
    assert stored["secret_hash"].startswith("$2b$") and keys["store-review-admin"] not in str(stored)
    assert await review_env["db"].review_access_log.count_documents({"success": False}) >= 2
    assert await review_env["primary"].review_accounts.count_documents({}) == 0
    assert await review_env["primary"].review_access_log.count_documents({}) == 0
    assert await review_env["primary"].users.count_documents({"review_environment": True}) == 0


async def test_reviewer_login_rate_limit_is_per_account(api_client, review_env):
    import asyncio
    import time
    keys = await provision(review_env)
    # The limiter uses fixed 60 s windows; eleven bcrypt attempts take ~4 s, so start clear of a window boundary.
    remaining = 60 - (int(time.time()) % 60)
    if remaining < 8:
        await asyncio.sleep(remaining)
    for _ in range(10):
        assert (await review_login(api_client, "store-review-billing", "wrong-key-wrong-key-wrong-key-12")).status_code == 401
    limited = await review_login(api_client, "store-review-billing", keys["store-review-billing"])
    assert limited.status_code == 429 and limited.json()["code"] == "OTP_RATE_LIMIT"
    # Another account is unaffected, and no limiter rows leaked into production.
    assert (await review_login(api_client, "store-review-admin", keys["store-review-admin"])).status_code == 200
    assert await review_env["primary"].otp_limits.count_documents({}) == 0


async def test_review_sessions_cannot_read_or_modify_production_records(api_client, review_env, seeded_users, login_helper):
    keys = await provision(review_env)
    prod = review_env["primary"]
    await prod.products.insert_one({"id": "prod-product-1", "title": "Genuine stock item", "metal_type": "silver", "category": "Chain",
        "visibility": "visible", "is_deleted": False, "version": 0, "created_at": c.stamp(), "updated_at": c.stamp()})
    admin = (await review_login(api_client, "store-review-admin", keys["store-review-admin"])).json()
    customers = await api_client.get("/api/customers?limit=100", headers=bearer(admin))
    assert customers.status_code == 200
    names = {row["name"] for row in customers.json()["customers"]}
    assert "Customer One" not in names and "Customer Two" not in names and all("synthetic" in n for n in names)
    assert (await api_client.get("/api/customers/u_cust1", headers=bearer(admin))).json()["code"] == "CUSTOMER_NOT_FOUND"
    assert (await api_client.patch("/api/customers/u_cust1", json={"name": "Hijacked"}, headers=bearer(admin))).status_code == 404
    assert (await prod.users.find_one({"id": "u_cust1"}))["name"] == "Customer One"
    assert (await api_client.get("/api/customers/search?q=Customer", headers=bearer(admin))).json()["customers"] == [] or all(
        "synthetic" in row["name"] for row in (await api_client.get("/api/customers/search?q=Customer", headers=bearer(admin))).json()["customers"])
    products = await api_client.get("/api/products?limit=100&include_hidden=true", headers=bearer(admin))
    assert all(p["id"].startswith("review-product-") for p in products.json()["products"]) and products.json()["total"] == 12
    assert (await api_client.put("/api/products/prod-product-1", json={"title": "Changed", "version": 0}, headers=bearer(admin))).status_code in (404, 409, 422)
    assert (await prod.products.find_one({"id": "prod-product-1"}))["title"] == "Genuine stock item"
    # Legacy admin read + staff write stay inside the review copy.
    dashboard = await api_client.get("/api/analytics/dashboard", headers=bearer(admin))
    assert dashboard.status_code == 200 and dashboard.json()["total_products"] == 12
    created = await api_client.post("/api/integrations/staff", json={"phone": "9100000199", "name": "Review Tele Two", "role": "telecaller"}, headers=bearer(admin))
    assert created.status_code == 200
    assert await prod.users.count_documents({"phone": "9100000199"}) == 0
    assert await review_env["db"].users.count_documents({"phone": "9100000199"}) == 1
    # Production staff still see only genuine records.
    real_admin = await login_helper("9999813334")
    real_list = await api_client.get("/api/customers?limit=100", headers=bearer(real_admin))
    assert all("synthetic" not in row["name"] for row in real_list.json()["customers"])
    assert (await api_client.get("/api/customers/review-customer-0001", headers=bearer(real_admin))).status_code == 404
    real_products = await api_client.get("/api/products?limit=100&include_hidden=true", headers=bearer(real_admin))
    assert {p["id"] for p in real_products.json()["products"]} == {"prod-product-1"}


async def test_review_actions_persist_in_review_database_and_simulate_external_effects(api_client, review_env, seeded_users):
    keys = await provision(review_env)
    prod, review, sent = review_env["primary"], review_env["db"], review_env["sent_otps"]
    customer = (await review_login(api_client, "store-review-customer", keys["store-review-customer"])).json()
    created = await api_client.post("/api/requests", json={"request_type": "ask_price", "product_ids": ["review-product-0001"]},
                                    headers={**bearer(customer), "Idempotency-Key": "review-ask-1"})
    assert created.status_code == 200, created.text
    assert await review.requests.count_documents({"id": created.json()["id"]}) == 1
    assert await prod.requests.count_documents({"id": created.json()["id"]}) == 0
    mine = await api_client.get("/api/requests/my", headers=bearer(customer))
    assert created.json()["id"] in {r["id"] for r in mine.json()["requests"]}
    # SMS-triggering flows are simulated: the intercepted production sender is never invoked.
    before = dict(sent)
    change = await api_client.post("/api/auth/phone-change/request", json={"new_phone": "9100000777"}, headers=bearer(customer))
    assert change.status_code == 200, change.text
    assert dict(sent) == before
    assert await review.sms_log.count_documents({"status": "simulated", "phone": "9100000777"}) == 1
    assert await prod.sms_log.count_documents({}) == 0 and await prod.otp_challenges.count_documents({"phone": "9100000777"}) == 0
    admin = (await review_login(api_client, "store-review-admin", keys["store-review-admin"])).json()
    test_sms = await api_client.post("/api/admin/sms/test", json={"phone": "9100000778"}, headers=bearer(admin))
    assert test_sms.status_code == 200 and test_sms.json()["log"]["simulated"] is True
    assert dict(sent) == before
    # Review media lives in the review database; production object storage is never written or read.
    image = io.BytesIO(); Image.new("RGB", (64, 64), (200, 170, 90)).save(image, "JPEG")
    uploaded = await api_client.post("/api/products/upload-image", files={"file": ("sample.jpg", image.getvalue(), "image/jpeg")}, headers=bearer(admin))
    assert uploaded.status_code == 200, uploaded.text
    path = uploaded.json()["storage_path"]
    assert path not in review_env["object_store"]
    assert await review.review_blobs.count_documents({"_id": path}) == 1
    served = await api_client.get(f"/api/files/{path}", headers=bearer(admin))
    assert served.status_code == 200 and served.headers["content-type"] == "image/jpeg"
    public_sample = await api_client.get("/api/files/yash-trade/review/products/review-product-0001.png", headers=bearer(customer))
    assert public_sample.status_code == 200 and public_sample.headers["content-type"] == "image/png"
    # The same paths are invisible to production sessions and anonymous callers (private → auth, then 404).
    assert (await api_client.get("/api/files/yash-trade/review/products/review-product-0001.png")).status_code in (401, 404)
    real_admin_token = None
    for phone in ("9999813334",):
        sent = await api_client.post("/api/auth/send-otp", json={"phone": phone, "channel": "mobile"})
        otp = review_env["sent_otps"][(phone, "login")]
        real_admin_token = (await api_client.post("/api/auth/verify-otp", json={"phone": phone, "channel": "mobile", "otp": otp,
                                                   "challenge_id": sent.json()["challenge_id"]})).json()
    assert (await api_client.get(f"/api/files/{path}", headers=bearer(real_admin_token))).status_code == 404
    assert (await api_client.get("/api/files/yash-trade/review/products/review-product-0001.png", headers=bearer(real_admin_token))).status_code == 404


async def test_review_refresh_logout_rotation_and_revocation(api_client, review_env, seeded_users, login_helper):
    keys = await provision(review_env)
    session = (await review_login(api_client, "store-review-telecaller", keys["store-review-telecaller"])).json()
    assert session["refresh_token"].startswith("review.")
    refreshed = await api_client.post("/api/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    assert jwt.decode(refreshed.json()["token"], options={"verify_signature": False})["scope"] == "review"
    assert (await api_client.get("/api/auth/me", headers=bearer(refreshed.json()))).json()["role"] == "telecaller"
    assert await review_env["primary"].refresh_tokens.count_documents({}) == 0
    # A production refresh token never routes into review data and vice versa.
    real = await login_helper("9000000001")
    assert (await api_client.post("/api/auth/refresh", json={"refresh_token": "review." + real["refresh_token"]})).status_code == 401
    assert (await api_client.post("/api/auth/refresh", json={"refresh_token": session["refresh_token"].removeprefix("review.")})).status_code == 401
    assert (await api_client.post("/api/auth/logout", headers=bearer(refreshed.json()))).json() == {"logged_out": True}
    assert (await api_client.get("/api/auth/me", headers=bearer(refreshed.json()))).status_code == 401
    # Rotation invalidates the old key and existing sessions; revocation disables the account.
    live = (await review_login(api_client, "store-review-telecaller", keys["store-review-telecaller"])).json()
    with c.scoped(c.REVIEW):
        new_key = await review_seed.rotate("store-review-telecaller")
    assert (await review_login(api_client, "store-review-telecaller", keys["store-review-telecaller"])).status_code == 401
    assert (await api_client.get("/api/auth/me", headers=bearer(live))).status_code == 401
    rotated = await review_login(api_client, "store-review-telecaller", new_key)
    assert rotated.status_code == 200
    with c.scoped(c.REVIEW):
        await review_seed.revoke("store-review-telecaller")
    assert (await review_login(api_client, "store-review-telecaller", new_key)).status_code == 401
    assert (await api_client.get("/api/auth/me", headers=bearer(rotated.json()))).status_code == 401


async def test_forged_scope_claims_and_review_phones_cannot_cross_environments(api_client, review_env, seeded_users, login_helper):
    keys = await provision(review_env)
    real = await login_helper("9000000004")
    claims = jwt.decode(real["token"], options={"verify_signature": False})
    forged = jwt.encode({**claims, "scope": "review"}, c.secret("JWT_SECRET"), algorithm="HS256")
    res = await api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 401  # production identity does not exist in the review database
    review = (await review_login(api_client, "store-review-customer", keys["store-review-customer"])).json()
    stripped = jwt.encode({k: v for k, v in jwt.decode(review["token"], options={"verify_signature": False}).items() if k != "scope"},
                          c.secret("JWT_SECRET"), algorithm="HS256")
    assert (await api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {stripped}"})).status_code == 401
    # Review phones are not identities in production: the website lookup is 404 and a production OTP for that number
    # is an ordinary (unknown-number) sign-up challenge, never a reviewer login.
    started = await api_client.post("/api/auth/send-otp", json={"phone": "9100000101", "channel": "mobile"})
    assert started.status_code == 200 and started.json()["account_exists"] is False
    lookup = await api_client.get("/api/integrations/customers/9100000101", headers=WEBSITE_KEY)
    assert lookup.status_code == 404
    # Genuine OTP login is unchanged.
    assert (await login_helper("9000000005"))["user"]["role"] == "customer"


async def test_simulated_review_otp_is_disclosed_only_to_its_own_authenticated_review_session(api_client, review_env, seeded_users, login_helper):
    keys = await provision(review_env)
    prod, review = review_env["primary"], review_env["db"]
    customer = (await review_login(api_client, "store-review-customer", keys["store-review-customer"])).json()
    # Authorised: the reviewer's OWN deletion challenge (subject == authenticated caller) carries the simulated code, and
    # only the hashed row + a digit-free simulated sms_log entry are stored.
    started = await api_client.post("/api/auth/delete-account/request", headers=bearer(customer))
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["review_environment"] is True and body["simulated_otp"].isdigit() and len(body["simulated_otp"]) == 4
    challenge = await review.otp_challenges.find_one({"purpose": "account_deletion", "subject": "review-customer-0001"})
    assert challenge and body["simulated_otp"] not in str({k: v for k, v in challenge.items() if k != "hash"})
    simulated = await review.sms_log.find_one({"status": "simulated", "purpose": "account_deletion"}, {"_id": 0})
    assert simulated and body["simulated_otp"] not in str(simulated) and await prod.otp_challenges.count_documents({}) == 0
    # Not authorised: a login OTP for ANOTHER synthetic account requested with the same review bearer (subject != caller),
    # an unauthenticated request, a production customer's own deletion challenge, and a signed-out review session.
    other = await api_client.post("/api/auth/send-otp", json={"phone": "9100000102", "channel": "mobile"}, headers=bearer(customer))
    assert other.status_code == 200 and "simulated_otp" not in other.json()
    unauth = await api_client.post("/api/auth/send-otp", json={"phone": "9100000101", "channel": "mobile"})  # production scope: plain sign-up challenge
    assert unauth.status_code == 200 and "simulated_otp" not in unauth.json() and unauth.json()["account_exists"] is False
    real = await login_helper("9000000005")
    await prod.otp_challenges.delete_many({"phone": "9000000005"})  # 60 s cooldown row from the login challenge (test only)
    real_delete = await api_client.post("/api/auth/delete-account/request", headers=bearer(real))
    assert real_delete.status_code == 200 and "simulated_otp" not in real_delete.json() and ("9000000005", "account_deletion") in review_env["sent_otps"]
    signed_out = (await review_login(api_client, "store-review-customer", keys["store-review-customer"])).json()
    assert (await api_client.post("/api/auth/logout", headers=bearer(signed_out))).status_code == 200
    assert (await api_client.post("/api/auth/delete-account/request", headers=bearer(signed_out))).status_code == 401
    # Wrong digits fail and count as an attempt; the disclosed code is single use.
    wrong = await api_client.post("/api/auth/delete-account/confirm", json={"otp": f"{(int(body['simulated_otp']) + 1) % 10000:04d}",
                                  "challenge_id": body["challenge_id"]}, headers=bearer(customer))
    assert wrong.status_code == 400 and wrong.json()["code"] == "OTP_INVALID"


async def test_reviewer_deletion_then_repeat_login_starts_a_fresh_sample_profile_without_restoring_anything(api_client, review_env, seeded_users, login_helper):
    keys = await provision(review_env)
    prod, review = review_env["primary"], review_env["db"]
    prod_users_before = [u async for u in prod.users.find({}, {"_id": 0}).sort("id", 1)]
    customer = (await review_login(api_client, "store-review-customer", keys["store-review-customer"])).json()
    assert customer["profile_recreated"] is False
    # The sample profile accumulates personal state: AI consent, chat history, a reward balance and an enquiry.
    assert (await api_client.post("/api/ai/consent", json={"granted": True}, headers=bearer(customer))).json()["granted"] is True
    await review.ai_chat_history.insert_one({"id": "h1", "user_id": "review-customer-0001", "session_id": "jeweller-review-customer-0001",
                                             "role": "user", "content": "sample question", "created_at": c.stamp()})
    assert (await review.users.find_one({"id": "review-customer-0001"}))["reward_points"] == 120
    started = (await api_client.post("/api/auth/delete-account/request", headers=bearer(customer))).json()
    done = await api_client.post("/api/auth/delete-account/confirm", json={"otp": started["simulated_otp"], "challenge_id": started["challenge_id"]},
                                 headers=bearer(customer))
    assert done.status_code == 200 and done.json()["deleted"] is True, done.text
    replay = await api_client.post("/api/auth/delete-account/confirm", json={"otp": started["simulated_otp"], "challenge_id": started["challenge_id"]},
                                   headers=bearer(customer))
    assert replay.status_code == 401  # session revoked by the deletion; the consumed code cannot be replayed either
    tomb = await review.users.find_one({"id": "review-customer-0001"}, {"_id": 0})
    assert tomb["account_status"] == "deleted" and "ai_consent" not in tomb and tomb["phone"].startswith("deleted:")
    assert await review.ai_chat_history.count_documents({"user_id": "review-customer-0001"}) == 0
    assert await review.deleted_identities.count_documents({"user_id": "review-customer-0001"}) == 1
    assert await review.deletion_requests.count_documents({"user_id": "review-customer-0001"}) == 1
    # Everything stayed in the review copy: production users, tombstones, deletion ledger and website outbox untouched.
    assert [u async for u in prod.users.find({}, {"_id": 0}).sort("id", 1)] == prod_users_before
    assert await prod.deleted_identities.count_documents({}) == 0 and await prod.deletion_requests.count_documents({}) == 0
    assert (await api_client.get("/api/integrations/deletions", headers=WEBSITE_KEY)).json()["events"] == []
    # Repeat sign-in with the SAME enabled credential: fresh profile, nothing restored, old session still dead.
    again = await review_login(api_client, "store-review-customer", keys["store-review-customer"])
    assert again.status_code == 200 and again.json()["profile_recreated"] is True and "fresh sample profile" in again.json()["notice"]
    assert (await api_client.get("/api/auth/me", headers=bearer(customer))).status_code == 401
    fresh = await review.users.find_one({"id": "review-customer-0001"}, {"_id": 0})
    assert fresh["account_status"] == "active" and fresh["review_environment"] is True and fresh["profile_generation"] == 1
    assert fresh["session_version"] >= 1 and fresh["phone"] == "9100000101" and fresh["reward_points"] == 0
    assert "ai_consent" not in fresh and (await api_client.get("/api/ai/consent", headers=bearer(again.json()))).json()["granted"] is False
    assert await review.ai_chat_history.count_documents({"user_id": "review-customer-0001"}) == 0
    assert await review.deleted_identities.count_documents({"user_id": "review-customer-0001"}) == 0
    assert await review.review_access_log.count_documents({"event": "review_profile_recreated"}) == 1
    me = await api_client.get("/api/auth/me", headers=bearer(again.json()))
    assert me.status_code == 200 and me.json()["role"] == "customer" and me.json()["review_environment"] is True
    # A REVOKED credential never regains access, and never recreates a profile: delete again, revoke, sign in -> 401.
    started = (await api_client.post("/api/auth/delete-account/request", headers=bearer(again.json()))).json()
    assert (await api_client.post("/api/auth/delete-account/confirm", json={"otp": started["simulated_otp"], "challenge_id": started["challenge_id"]},
                                  headers=bearer(again.json()))).status_code == 200
    with c.scoped(c.REVIEW):
        await review_seed.revoke("store-review-customer")
    denied = await review_login(api_client, "store-review-customer", keys["store-review-customer"])
    assert denied.status_code == 401
    assert (await review.users.find_one({"id": "review-customer-0001"}))["account_status"] == "deleted"
    assert await review.review_access_log.count_documents({"event": "review_profile_recreated"}) == 1
    # Ordinary customers never auto-recreate: a genuine deletion stays deleted for the normal OTP flow.
    real = await login_helper("9000000005")
    await prod.otp_challenges.delete_many({"phone": "9000000005"})  # 60 s cooldown row from the login challenge (test only)
    started = (await api_client.post("/api/auth/delete-account/request", headers=bearer(real))).json()
    otp = review_env["sent_otps"][("9000000005", "account_deletion")]
    assert (await api_client.post("/api/auth/delete-account/confirm", json={"otp": otp, "challenge_id": started["challenge_id"]}, headers=bearer(real))).status_code == 200
    await prod.otp_challenges.delete_many({"phone": "9000000005"})
    afresh = await api_client.post("/api/auth/send-otp", json={"phone": "9000000005", "channel": "mobile"})
    assert afresh.status_code == 200 and afresh.json()["account_exists"] is False  # the erased identity is not a registered number any more; a fresh sign-up may start
    assert (await prod.users.find_one({"id": "u_cust2"}))["account_status"] == "deleted"
    # Reset keeps the credentials but rebuilds the synthetic dataset (also clears the tombstone above).
    with c.scoped(c.REVIEW):
        summary = await review_seed.seed_dataset(reset=True)
        status = await review_seed.status()
    assert summary["products"] == 12 and len(status["accounts"]) == 4 and all("secret_hash" not in a for a in status["accounts"])
    assert await review.otp_challenges.count_documents({}) == 0 and (await review.users.find_one({"id": "review-customer-0001"}))["account_status"] == "active"
