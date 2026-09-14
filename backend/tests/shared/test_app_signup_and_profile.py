"""App-first identity: phone + OTP creates the customer account when none exists (login-or-register), the website
registration updates that same account (never a duplicate), differing website values wait for the customer's choice,
a deleted number can start afresh with a fresh OTP, and requests to the team need a complete profile."""
from shared import core as c

INTEGRATION = {"X-Integration-Key": "integration-key-1234567890-abcdef"}


def bearer(session):
    return {"Authorization": "Bearer " + session["token"]}


async def enroll_on_website(api_client, isolated_db, phone, **profile):
    sent = await api_client.post("/api/auth/send-otp", json={"phone": phone, "purpose": "enrollment", "channel": "mobile"}, headers=INTEGRATION)
    assert sent.status_code == 200, sent.text
    otp = isolated_db["sent_otps"][(phone, "enrollment")]
    grant = await api_client.post("/api/auth/verify-otp", json={"phone": phone, "purpose": "enrollment", "channel": "mobile", "otp": otp,
                                                               "challenge_id": sent.json()["challenge_id"]}, headers=INTEGRATION)
    assert grant.status_code == 200, grant.text
    body = {"phone": phone, "name": "Web Name", "shop_name": "Web Shop", "location": "Ludhiana", "verification_grant": grant.json()["verification_grant"],
            "idempotency_key": "idem-" + phone, "consent_version": "v1", "consent_terms": True, "consent_privacy": True, **profile}
    return await api_client.post("/api/integrations/enrollments", headers=INTEGRATION, json=body)


async def test_unknown_number_signs_up_from_the_app_with_recorded_consent(api_client, isolated_db, seeded_users):
    db = isolated_db["db"]
    sent = await api_client.post("/api/auth/send-otp", json={"phone": "9300000001", "channel": "mobile"})
    assert sent.status_code == 200 and sent.json()["account_exists"] is False
    otp = isolated_db["sent_otps"][("9300000001", "login")]
    payload = {"phone": "9300000001", "channel": "mobile", "otp": otp, "challenge_id": sent.json()["challenge_id"]}
    # Consent is mandatory for account creation and nothing is created before it (the challenge stays usable).
    refused = await api_client.post("/api/auth/verify-otp", json=payload)
    assert refused.status_code == 422 and refused.json()["code"] == "CONSENT_REQUIRED"
    assert await db.users.count_documents({"phone_normalized": "9300000001"}) == 0
    created = await api_client.post("/api/auth/verify-otp", json={**payload, "accept_terms": True})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["is_new_account"] is True and body["user"]["role"] == "customer" and body["user"]["profile_complete"] is False
    assert body["user"]["registration_source"] == "app" and body["user"]["onboarding_status"] == "pending" and body["user"]["step1_complete"] is False
    stored = await db.users.find_one({"phone_normalized": "9300000001"}, {"_id": 0})
    assert stored["consent_history"] == [{**stored["consent_history"][0], "version": "terms-privacy-2026-09", "terms": True, "privacy": True, "source": "app"}]
    assert "phone" not in stored["consent_history"][0] and stored["has_logged_in"] is True
    # The account is usable straight away; a later login is a plain login (no second consent entry, not "new").
    me = await api_client.get("/api/auth/me", headers=bearer(body))
    assert me.status_code == 200 and me.json()["phone"] == "9300000001"
    await db.otp_challenges.delete_many({"phone": "9300000001"})  # 60 s cooldown row (test only)
    again_sent = await api_client.post("/api/auth/send-otp", json={"phone": "9300000001", "channel": "mobile"})
    assert again_sent.json()["account_exists"] is True
    again = await api_client.post("/api/auth/verify-otp", json={"phone": "9300000001", "channel": "mobile", "challenge_id": again_sent.json()["challenge_id"],
                                                               "otp": isolated_db["sent_otps"][("9300000001", "login")]})
    assert again.status_code == 200 and again.json()["is_new_account"] is False
    assert len((await db.users.find_one({"phone_normalized": "9300000001"}))["consent_history"]) == 1
    assert await db.users.count_documents({"phone_normalized": "9300000001"}) == 1


async def test_portal_and_staff_paths_never_create_accounts(api_client, isolated_db, seeded_users):
    portal = await api_client.post("/api/auth/send-otp", json={"phone": "9300000002", "channel": "portal"},
                                   headers={"X-Staff-Service-Key": "staff-service-key-1234567890-abcdef"})
    assert portal.status_code == 404 and portal.json()["code"] == "USER_NOT_FOUND"
    assert ("9300000002", "login") not in isolated_db["sent_otps"]
    deletion = await api_client.post("/api/auth/send-otp", json={"phone": "9300000002", "purpose": "deletion"}, headers=INTEGRATION)
    assert deletion.status_code == 404
    # Sign-up SMS budget: at most 10 new-number challenges per IP per hour on top of the per-number limits.
    for i in range(10):
        ok = await api_client.post("/api/auth/send-otp", json={"phone": f"93000001{i:02d}", "channel": "mobile"})
        assert ok.status_code == 200, ok.text
    capped = await api_client.post("/api/auth/send-otp", json={"phone": "9300000199", "channel": "mobile"})
    assert capped.status_code == 429 and capped.json()["code"] == "OTP_RATE_LIMIT"
    assert ("9300000199", "login") not in isolated_db["sent_otps"]


async def test_website_registration_updates_the_app_account_and_parks_conflicting_values(api_client, isolated_db, seeded_users, login_helper):
    db = isolated_db["db"]
    phone = "9300000003"
    sent = await api_client.post("/api/auth/send-otp", json={"phone": phone, "channel": "mobile"})
    session = (await api_client.post("/api/auth/verify-otp", json={"phone": phone, "channel": "mobile", "accept_terms": True,
                                                                  "otp": isolated_db["sent_otps"][(phone, "login")], "challenge_id": sent.json()["challenge_id"]})).json()
    # The customer completes the profile in the app.
    saved = await api_client.put("/api/auth/profile", json={"name": "App Name", "shop_name": "App Shop", "location": "Amritsar"}, headers=bearer(session))
    assert saved.status_code == 200 and saved.json()["profile_complete"] is True and saved.json()["onboarding_status"] == "completed"
    await db.otp_challenges.delete_many({"phone": phone})
    # Website registration with the same number: same account, website values overwrite, app values parked for a choice.
    enrolled = await enroll_on_website(api_client, isolated_db, phone, shop_name="App Shop")
    assert enrolled.status_code == 200, enrolled.text
    assert enrolled.json()["created"] is False and enrolled.json()["customer"]["id"] == session["user"]["id"]
    assert await db.users.count_documents({"phone_normalized": phone}) == 1
    me = (await api_client.get("/api/auth/me", headers=bearer(session))).json()
    assert me["name"] == "Web Name" and me["shop_name"] == "App Shop" and me["location"] == "Ludhiana"
    assert set(me["profile_conflicts"]) == {"name", "location"}  # shop_name was identical -> no conflict
    assert me["profile_conflicts"]["name"] == {**me["profile_conflicts"]["name"], "previous": "App Name", "kept": "Web Name", "source": "website"}
    # Every conflicting field needs a choice; then the rejected values are dropped field by field.
    partial = await api_client.post("/api/auth/profile/conflicts/resolve", json={"choices": {"name": "previous"}}, headers=bearer(session))
    assert partial.status_code == 422 and partial.json()["code"] == "CHOICE_REQUIRED"
    resolved = await api_client.post("/api/auth/profile/conflicts/resolve", json={"choices": {"name": "previous", "location": "kept"}}, headers=bearer(session))
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["name"] == "App Name" and resolved.json()["location"] == "Ludhiana" and resolved.json()["profile_conflicts"] == {}
    assert (await db.users.find_one({"id": session["user"]["id"]}, {"_id": 0}))["city"] == "Ludhiana"
    nothing = await api_client.post("/api/auth/profile/conflicts/resolve", json={"choices": {"name": "kept"}}, headers=bearer(session))
    assert nothing.status_code == 409 and nothing.json()["code"] == "NO_PROFILE_CONFLICTS"
    # Saving the profile form explicitly also settles pending conflicts.
    await db.users.update_one({"id": session["user"]["id"]}, {"$set": {"profile_conflicts": {"name": {"previous": "X", "kept": "Y"}}}})
    saved = await api_client.put("/api/auth/profile", json={"name": "Final", "shop_name": "App Shop", "location": "Ludhiana"}, headers=bearer(session))
    assert saved.json()["profile_conflicts"] == {} and saved.json()["name"] == "Final"


async def test_deleted_number_starts_afresh_but_stale_grants_cannot_resurrect(api_client, isolated_db, seeded_users, login_helper):
    db = isolated_db["db"]
    real = await login_helper("9000000005")
    old_id = real["user"]["id"]
    await db.otp_challenges.delete_many({"phone": "9000000005"})
    started = (await api_client.post("/api/auth/delete-account/request", headers=bearer(real))).json()
    otp = isolated_db["sent_otps"][("9000000005", "account_deletion")]
    assert (await api_client.post("/api/auth/delete-account/confirm", json={"otp": otp, "challenge_id": started["challenge_id"]}, headers=bearer(real))).status_code == 200
    await db.otp_challenges.delete_many({"phone": "9000000005"})
    # A grant issued BEFORE the deletion (queued website retry) is refused ...
    stale_hash = c.digest("stale-grant")
    await db.auth_grants.insert_one({"hash": stale_hash, "phone": "9000000005", "purpose": "enrollment", "subject": "", "used": False,
                                     "issued_at": c.now() - c.timedelta(minutes=3), "expires_at": c.now() + c.timedelta(minutes=2)})
    retry = await api_client.post("/api/integrations/enrollments", headers=INTEGRATION, json={
        "phone": "9000000005", "name": "Ghost", "shop_name": "Ghost", "location": "Ghost", "verification_grant": "stale-grant",
        "idempotency_key": "idem-stale-1", "consent_version": "v1", "consent_terms": True, "consent_privacy": True})
    assert retry.status_code == 409 and retry.json()["code"] == "DELETED_IDENTITY"
    # ... but the person can sign up again in the app with a fresh OTP: a NEW account, history stays erased.
    sent = await api_client.post("/api/auth/send-otp", json={"phone": "9000000005", "channel": "mobile"})
    assert sent.status_code == 200 and sent.json()["account_exists"] is False
    fresh = await api_client.post("/api/auth/verify-otp", json={"phone": "9000000005", "channel": "mobile", "accept_terms": True,
                                                               "otp": isolated_db["sent_otps"][("9000000005", "login")], "challenge_id": sent.json()["challenge_id"]})
    assert fresh.status_code == 200 and fresh.json()["is_new_account"] is True and fresh.json()["user"]["id"] != old_id
    assert fresh.json()["user"]["name"] == "" and fresh.json()["user"]["profile_complete"] is False
    assert (await db.users.find_one({"id": old_id}))["account_status"] == "deleted"  # tombstone untouched
    await db.otp_challenges.delete_many({"phone": "9000000005"})
    # ... and register on the website again too (fresh verification) - it updates the new account, no duplicate.
    enrolled = await enroll_on_website(api_client, isolated_db, "9000000005")
    assert enrolled.status_code == 200, enrolled.text
    assert enrolled.json()["created"] is False and enrolled.json()["customer"]["id"] == fresh.json()["user"]["id"]
    assert await db.users.count_documents({"phone_normalized": "9000000005"}) == 1


async def test_requests_require_a_complete_profile_and_go_through_after_completion(api_client, isolated_db, seeded_users, login_helper):
    db = isolated_db["db"]
    sent = await api_client.post("/api/auth/send-otp", json={"phone": "9300000004", "channel": "mobile"})
    session = (await api_client.post("/api/auth/verify-otp", json={"phone": "9300000004", "channel": "mobile", "accept_terms": True,
                                                                  "otp": isolated_db["sent_otps"][("9300000004", "login")], "challenge_id": sent.json()["challenge_id"]})).json()
    call = {"request_type": "callback", "category": "silver", "preferred_time": "morning", "notes": "", "product_id": "", "product_ids": []}
    blocked = await api_client.post("/api/requests", json=call, headers=bearer(session))
    assert blocked.status_code == 428 and blocked.json()["code"] == "PROFILE_INCOMPLETE"
    assert await db.requests.count_documents({"user_id": session["user"]["id"]}) == 0
    await db.cart.insert_one({"id": "cart-1", "user_id": session["user"]["id"], "product_id": "p-1", "quantity": 1, "status": "active"})
    cart_blocked = await api_client.post("/api/cart/submit", json={"notes": ""}, headers=bearer(session))
    assert cart_blocked.status_code == 428 and cart_blocked.json()["code"] == "PROFILE_INCOMPLETE"
    assert (await db.cart.find_one({"id": "cart-1"}))["status"] == "active"
    # Complete the profile (the app opens the form and re-sends the original request) -> both go through.
    assert (await api_client.put("/api/auth/profile", json={"name": "Done", "shop_name": "Done Shop", "location": "Jalandhar"}, headers=bearer(session))).status_code == 200
    sent_ok = await api_client.post("/api/requests", json=call, headers=bearer(session))
    assert sent_ok.status_code == 200, sent_ok.text
    assert (await api_client.post("/api/cart/submit", json={"notes": ""}, headers=bearer(session))).status_code == 200
    # Website-registered customers (profile always complete) are unaffected.
    web = await login_helper("9000000004")
    assert (await api_client.post("/api/requests", json=call, headers=bearer(web))).status_code == 200
