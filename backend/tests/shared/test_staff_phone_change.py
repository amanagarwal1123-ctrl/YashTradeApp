"""Administrator-controlled staff login-number change, customer promotion boundary, international canonical numbers."""

import asyncio
import uuid

import pytest
from fastapi import HTTPException

from shared import core as c

TELE, TELE2, BILL, CUST, OWNER = "u_tele1", "u_tele2", "u_bill", "u_cust1", "u_admin"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _body(new_phone, expected="9000000001", uid=TELE, key=None, reason="Handset lost; new company SIM issued to the telecaller", token="no-preview"):
    return {"new_phone": new_phone, "reason": reason, "confirm_user_id": uid, "expected_phone": expected,
            "idempotency_key": key or uuid.uuid4().hex, "preview_token": token}


async def _previewed(api_client, admin, body, ref=None):
    """The confirmation an administrator sees is bound to (target, current number, new number): fetch it like the panel does."""
    res = await api_client.post(f"/api/integrations/staff/{ref or body['confirm_user_id']}/phone/preview", headers=_auth(admin), json={"new_phone": body["new_phone"]})
    assert res.status_code == 200, res.text
    return {**body, "preview_token": res.json().get("preview_token", "no-preview")}


async def _admin(login_helper):
    return (await login_helper("9000000000"))["token"]


async def _signup(api_client, isolated_db, phone):
    payload = {"phone": phone, "purpose": "login", "channel": "mobile"}
    send = await api_client.post("/api/auth/send-otp", json=payload)
    assert send.status_code == 200, send.text
    canonical = c.phone(phone)
    otp = isolated_db["sent_otps"].get((canonical, "login"))
    assert otp, f"OTP was not dispatched to the full canonical number {canonical}"
    verify = await api_client.post("/api/auth/verify-otp", json={**payload, "otp": otp, "challenge_id": send.json()["challenge_id"], "accept_terms": True})
    assert verify.status_code == 200, verify.text
    return verify.json()


# ---------------------------------------------------------------- canonical phone parsing -----------------------------
def test_canonical_phone_keeps_indian_ten_digits_and_e164_for_supported_countries():
    assert c.phone("9876543210") == "9876543210"
    assert c.phone("+91 98765 43210") == "9876543210"
    assert c.phone("919876543210") == "9876543210"
    assert c.phone("+1 (415) 555-2671") == "+14155552671"
    assert c.phone("+1 416 555 0134") == "+14165550134"          # Canada shares +1
    assert c.phone("+61 412 345 678") == "+61412345678"
    assert c.phone("0061412345678") == "+61412345678"
    for bad, code in (("+44 7911 123456", "UNSUPPORTED_COUNTRY"), ("+1 415 555 26", "INVALID_PHONE"), ("12345", "INVALID_PHONE"),
                      ("+91 12345 67890", "INVALID_PHONE"), ("4155552671", "INVALID_PHONE")):
        with pytest.raises(HTTPException) as err:
            c.phone(bad)
        assert err.value.detail["code"] == code, bad
    # never truncated to the last ten digits
    assert c.sms_destination("+14155552671") == "14155552671" and c.sms_destination("9876543210") == "919876543210"
    assert c.phone_display("+14155552671") == "+1 415-555-2671" and c.phone_display("9876543210") == "+91 98765 43210"


@pytest.mark.asyncio
async def test_international_login_creates_one_e164_account_without_duplicates(api_client, isolated_db, login_helper):
    first = await _signup(api_client, isolated_db, "+61412345678")
    # a differently formatted spelling is the SAME identity: it even shares the per-number OTP cooldown
    blocked = await api_client.post("/api/auth/send-otp", json={"phone": "+61 412 345 678", "purpose": "login", "channel": "mobile"})
    assert blocked.status_code == 429 and blocked.json()["code"] == "OTP_COOLDOWN"
    await isolated_db["db"].otp_challenges.delete_many({"phone": "+61412345678"})
    again = await _signup(api_client, isolated_db, "+61 412 345 678")
    assert first["user"]["id"] == again["user"]["id"] and first["user"]["phone"] == "+61412345678"
    assert await isolated_db["db"].users.count_documents({"phone_normalized": "+61412345678"}) == 1
    us = await _signup(api_client, isolated_db, "+1 (415) 555-2671")
    assert us["user"]["phone"] == "+14155552671"
    assert await isolated_db["db"].users.count_documents({"phone_normalized": {"$in": ["4155552671", "+14155552671"]}}) == 1


# ---------------------------------------------------------------- admin phone change ----------------------------------
@pytest.mark.asyncio
async def test_preview_classifies_available_customer_staff_and_unchanged_numbers(api_client, isolated_db, login_helper):
    token = await _admin(login_helper)
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone/preview", headers=_auth(token), json={"new_phone": "9111111111"})
    assert res.status_code == 200 and res.json()["status"] == "available" and res.json()["new_phone"] == "9111111111"
    assert res.json()["staff"]["id"] == TELE and "keeps the same account" in res.json()["outcome"]
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone/preview", headers=_auth(token), json={"new_phone": "9000000004"})
    body = res.json()
    assert res.status_code == 200 and body["status"] == "customer"
    assert body["customer"]["id"] == CUST and body["customer"]["role"] == "customer" and body["customer"]["masked_phone"].endswith("0004")
    assert "9000000004" not in body["customer"]["masked_phone"] and "same person" in body["outcome"]
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone/preview", headers=_auth(token), json={"new_phone": "9000000003"})
    assert res.status_code == 200 and res.json()["status"] == "staff" and res.json()["owner"]["id"] == BILL
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone/preview", headers=_auth(token), json={"new_phone": "9000000001"})
    assert res.json()["status"] == "unchanged"
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone/preview", headers=_auth(token), json={"new_phone": "12345"})
    assert res.status_code == 422 and res.json()["code"] == "INVALID_PHONE"
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone/preview", headers=_auth(token), json={"new_phone": "+44 7911 123456"})
    assert res.status_code == 422 and res.json()["code"] == "UNSUPPORTED_COUNTRY"


@pytest.mark.asyncio
async def test_unused_number_change_preserves_identity_revokes_sessions_and_requires_verification(api_client, isolated_db, login_helper):
    db = isolated_db["db"]
    admin = await _admin(login_helper)
    tele_session = await login_helper("9000000001")
    tele_token = tele_session["token"]
    assert (await api_client.get("/api/auth/me", headers=_auth(tele_token))).status_code == 200
    before = await db.users.find_one({"id": TELE}, {"_id": 0})
    await db.users.update_one({"id": TELE}, {"$set": {"assigned_customers": ["u_cust2"], "code": "T1"}})

    key = uuid.uuid4().hex
    body_in = await _previewed(api_client, admin, _body("+61 412 345 678", key=key))
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=body_in)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "recovered" not in body and "replayed" not in body
    assert body["user"]["id"] == TELE and body["user"]["phone"] == "+61412345678" and body["verification_required"] is True
    assert body["old_phone_masked"].endswith("0001") and "9000000001" not in body["old_phone_masked"]
    after = await db.users.find_one({"id": TELE}, {"_id": 0})
    assert after["role"] == before["role"] and after["created_at"] == before["created_at"] and after["assigned_customers"] == ["u_cust2"]
    assert after["phone_verified"] is False and "verified_at" not in after and after["phone_normalized"] == "+61412345678"
    assert await db.users.count_documents({"role": {"$ne": "customer"}}) == await isolated_db["db"].users.count_documents({"role": {"$ne": "customer"}})
    audit = await db.identity_audit.find_one({"target_id": TELE}, {"_id": 0})
    assert audit["actor_id"] == OWNER and audit["old_phone"] == "9000000001" and audit["new_phone"] == "+61412345678" and audit["reason"]
    assert after["identity_events"][-1]["type"] == "staff_phone_changed"
    # sessions of the affected account are gone (app + website share these families); refresh tokens are burnt
    assert (await api_client.get("/api/auth/me", headers=_auth(tele_token))).status_code == 401
    refreshed = await api_client.post("/api/auth/refresh", json={"refresh_token": tele_session["refresh_token"]})
    assert refreshed.status_code == 401
    # the old number no longer reaches the staff account: a mobile login there is a fresh sign-up, not the telecaller
    await db.otp_challenges.delete_many({"phone": "9000000001"})
    send = await api_client.post("/api/auth/send-otp", json={"phone": "9000000001", "purpose": "login", "channel": "mobile"})
    assert send.status_code == 200 and send.json()["account_exists"] is False
    # the new number signs in ONLY after OTP verification, which then marks it verified
    relogin = await login_helper("+61412345678")
    assert relogin["user"]["id"] == TELE and relogin["user"]["role"] == "telecaller"
    assert (await db.users.find_one({"id": TELE}, {"_id": 0}))["phone_verified"] is True
    # retry with the same idempotency key replays the stored result without a second update
    again = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=body_in)
    assert again.status_code == 200 and again.json()["replayed"] is True and again.json()["new_phone"] == "+61412345678"
    assert await db.identity_audit.count_documents({"target_id": TELE}) == 1
    # same key with a different payload is refused
    mismatch = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json={**body_in, "new_phone": "9111111111", "expected_phone": "+61412345678"})
    assert mismatch.status_code == 409 and mismatch.json()["code"] == "IDEMPOTENCY_MISMATCH"


@pytest.mark.asyncio
async def test_conflicts_confirmation_permissions_and_protections(api_client, isolated_db, login_helper):
    admin = await _admin(login_helper)
    # customer-owned number: never silently changes the staff record - explicit promotion boundary
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9000000004"))
    assert res.status_code == 409 and res.json()["code"] == "CUSTOMER_PROMOTION_REQUIRED"
    assert (await isolated_db["db"].users.find_one({"id": TELE}, {"_id": 0}))["phone"] == "9000000001"
    # number owned by another staff account
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9000000003"))
    assert res.status_code == 409 and res.json()["code"] == "PHONE_OWNED_BY_STAFF"
    # wrong confirmation id, stale before-value, unchanged number, short reason, invalid number
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9111111111", uid=TELE2))).json()["code"] == "CONFIRMATION_REQUIRED"
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9111111111", expected="9000000009"))).json()["code"] == "VERSION_CONFLICT"
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9000000001"))).json()["code"] == "PHONE_UNCHANGED"
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9111111111", reason="short"))).status_code == 422
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("12345"))).json()["code"] == "INVALID_PHONE"
    # owner and other administrators are never renumbered by this operation; customers need promotion, not renumbering
    assert (await api_client.post(f"/api/integrations/staff/{OWNER}/phone", headers=_auth(admin), json=_body("9111111111", expected="9000000000", uid=OWNER))).json()["code"] == "OWNER_ADMIN_PROTECTED"
    await isolated_db["db"].users.insert_one({"id": "u_admin2", "phone": "9000000016", "phone_normalized": "9000000016", "name": "Second Admin",
        "role": "admin", "account_status": "active", "status": "active", "session_version": 0, "created_at": c.stamp(), "updated_at": c.stamp()})
    assert (await api_client.post("/api/integrations/staff/u_admin2/phone", headers=_auth(admin), json=_body("9111111111", expected="9000000016", uid="u_admin2"))).json()["code"] == "ADMIN_SELF_SERVICE_REQUIRED"
    assert (await api_client.post(f"/api/integrations/staff/{CUST}/phone", headers=_auth(admin), json=_body("9111111111", expected="9000000004", uid=CUST))).json()["code"] == "EXPLICIT_CONVERSION_REQUIRED"
    # permissions: staff and customers cannot use either endpoint
    tele = (await login_helper("9000000002"))["token"]
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone/preview", headers=_auth(tele), json={"new_phone": "9111111111"})).status_code == 403
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(tele), json=_body("9111111111"))).status_code == 403
    cust = (await login_helper("9000000004"))["token"]
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(cust), json=_body("9111111111"))).status_code == 403
    # the owner record itself is untouched by all of the above
    owner = await isolated_db["db"].users.find_one({"id": OWNER}, {"_id": 0})
    assert owner["phone"] == "9000000000" and owner["role"] == "admin" and c.account_status(owner) == "active"
    # legacy PATCH with a phone points to the new operation instead of changing anything
    res = await api_client.patch(f"/api/integrations/staff/{TELE}", headers=_auth(admin), json={"phone": "9111111111"})
    assert res.status_code == 409 and res.json()["code"] == "PHONE_CHANGE_OPERATION_REQUIRED"


@pytest.mark.asyncio
async def test_recent_authentication_is_required(api_client, isolated_db, login_helper):
    session = await login_helper("9000000000")
    admin = session["token"]
    # age the sign-in beyond the step-up window: the change is refused, preview (read-only) still works
    await isolated_db["db"].session_families.update_many({"user_id": OWNER}, {"$set": {"authenticated_at": "2026-01-01T00:00:00+00:00"}})
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9111111111"))
    assert res.status_code == 403 and res.json()["code"] == "RECENT_AUTH_REQUIRED"
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone/preview", headers=_auth(admin), json={"new_phone": "9111111111"})).status_code == 200
    assert (await isolated_db["db"].users.find_one({"id": TELE}, {"_id": 0}))["phone"] == "9000000001"
    # a family without any sign-in stamp (older build) never qualifies either
    await isolated_db["db"].session_families.update_many({"user_id": OWNER}, {"$unset": {"authenticated_at": ""}})
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9111111111"))).json()["code"] == "RECENT_AUTH_REQUIRED"
    # a fresh OTP sign-in satisfies the step-up
    await isolated_db["db"].otp_challenges.delete_many({"phone": "9000000000"})
    fresh = (await login_helper("9000000000"))["token"]
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(fresh), json=await _previewed(api_client, fresh, _body("9111111111")))).status_code == 200


@pytest.mark.asyncio
async def test_confirmation_is_bound_to_the_exact_account_and_number(api_client, isolated_db, login_helper):
    admin = await _admin(login_helper)
    good = await _previewed(api_client, admin, _body("9111111111"))
    # the preview described 9111111111 for TELE: submitting another number, or another staff member, with that confirmation is refused
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json={**good, "new_phone": "9222222222"})
    assert res.status_code == 409 and res.json()["code"] == "PREVIEW_MISMATCH"
    other = {**good, "confirm_user_id": TELE2, "expected_phone": "9000000002"}
    res = await api_client.post(f"/api/integrations/staff/{TELE2}/phone", headers=_auth(admin), json=other)
    assert res.status_code == 409 and res.json()["code"] == "PREVIEW_MISMATCH"
    # a confirmation for the same number issued for a DIFFERENT staff member does not transfer either
    transferred = {**(await _previewed(api_client, admin, other)), "confirm_user_id": TELE, "expected_phone": "9000000001"}
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=transferred)
    assert res.status_code == 409 and res.json()["code"] == "PREVIEW_MISMATCH"
    # a missing / stale confirmation is refused; an expired one names the reason
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9111111111"))).json()["code"] == "PREVIEW_MISMATCH"
    from shared import people
    expired = {**good, "preview_token": people.preview_token(TELE, "9000000001", "9111111111", int(c.now().timestamp()) - 1)}
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=expired)).json()["code"] == "PREVIEW_EXPIRED"
    for uid in (TELE, TELE2):
        assert (await isolated_db["db"].users.find_one({"id": uid}, {"_id": 0}))["phone"] == ("9000000001" if uid == TELE else "9000000002")
    # refusals released their keys: the matching confirmation now succeeds with the very same idempotency key
    assert (await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=good)).status_code == 200


@pytest.mark.asyncio
async def test_simultaneous_requests_with_the_same_key_share_one_result(api_client, isolated_db, login_helper):
    admin = await _admin(login_helper)
    body = await _previewed(api_client, admin, _body("9111111111"))
    results = await asyncio.gather(*[api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=body) for _ in range(4)])
    assert [r.status_code for r in results] == [200] * 4, [(r.status_code, r.text[:120]) for r in results]
    assert {r.json()["new_phone"] for r in results} == {"9111111111"} and sum(1 for r in results if not r.json().get("replayed")) == 1
    assert await isolated_db["db"].identity_audit.count_documents({"target_id": TELE}) == 1
    assert await isolated_db["db"].identity_operations.count_documents({"state": "done"}) == 1
    user = await isolated_db["db"].users.find_one({"id": TELE}, {"_id": 0})
    assert user["phone"] == "9111111111" and sum(1 for e in user["identity_events"] if e["type"] == "staff_phone_changed") == 1
    # a refused request shared by simultaneous callers is refused identically for all of them and leaves no reservation
    bad = await _previewed(api_client, admin, _body("9000000004", expected="9111111111"))
    results = await asyncio.gather(*[api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=bad) for _ in range(3)])
    assert {(r.status_code, r.json()["code"]) for r in results} == {(409, "CUSTOMER_PROMOTION_REQUIRED")}
    assert await isolated_db["db"].identity_operations.count_documents({"state": {"$ne": "done"}}) == 0


@pytest.mark.asyncio
async def test_failure_after_the_account_update_is_recoverable(api_client, isolated_db, login_helper, monkeypatch):
    db = isolated_db["db"]
    admin = await _admin(login_helper)
    tele_token = (await login_helper("9000000001"))["token"]
    body = await _previewed(api_client, admin, _body("9111111111"))
    from motor.motor_asyncio import AsyncIOMotorCollection
    real_insert = AsyncIOMotorCollection.insert_one
    calls = {"n": 0}

    async def broken_insert(self, *args, **kwargs):
        if self.name.endswith("identity_audit"):
            calls["n"] += 1
            raise RuntimeError("audit store unavailable")
        return await real_insert(self, *args, **kwargs)
    monkeypatch.setattr(AsyncIOMotorCollection, "insert_one", broken_insert)
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=body)
    assert res.status_code == 503 and res.json()["code"] == "OPERATION_INCOMPLETE" and calls["n"] == 1
    # the change itself stands, sessions are already gone, but no audit / replay record exists yet
    user = await db.users.find_one({"id": TELE}, {"_id": 0})
    assert user["phone"] == "9111111111" and user["phone_verified"] is False
    assert (await api_client.get("/api/auth/me", headers=_auth(tele_token))).status_code == 401
    assert await db.identity_audit.count_documents({"target_id": TELE}) == 0
    op = await db.identity_operations.find_one({}, {"_id": 0})
    assert op["state"] == "validated" and op["target_id"] == TELE and op["new_phone"] == "9111111111"
    # while the store is still broken every retry keeps reporting the incomplete state without touching the account again
    again = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=body)
    assert again.status_code == 503 and again.json()["code"] == "OPERATION_INCOMPLETE"
    assert sum(1 for e in (await db.users.find_one({"id": TELE}, {"_id": 0}))["identity_events"] if e["type"] == "staff_phone_changed") == 1
    # once the store is back, the same key finishes the bookkeeping exactly once and returns the normal result
    monkeypatch.setattr(AsyncIOMotorCollection, "insert_one", real_insert)
    done = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=body)
    assert done.status_code == 200 and done.json()["recovered"] is True and done.json()["new_phone"] == "9111111111"
    assert await db.identity_audit.count_documents({"target_id": TELE}) == 1
    assert (await db.identity_operations.find_one({}, {"_id": 0}))["state"] == "done"
    replay = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=body)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert await db.identity_audit.count_documents({"target_id": TELE}) == 1


@pytest.mark.asyncio
async def test_interrupted_operation_is_completed_by_the_next_operation_on_the_same_staff_member(api_client, isolated_db, login_helper, monkeypatch):
    db = isolated_db["db"]
    admin = await _admin(login_helper)
    body = await _previewed(api_client, admin, _body("9111111111"))
    from motor.motor_asyncio import AsyncIOMotorCollection
    real_update = AsyncIOMotorCollection.update_one
    calls = {"n": 0}

    async def flaky_update(self, *args, **kwargs):
        if self.name.endswith("identity_operations"):
            calls["n"] += 1
            if calls["n"] == 2:  # 1st call = intent before the account update (succeeds); 2nd = replay record after it (fails)
                raise RuntimeError("replay store unavailable")
        return await real_update(self, *args, **kwargs)
    monkeypatch.setattr(AsyncIOMotorCollection, "update_one", flaky_update)
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=body)
    assert res.status_code == 503 and res.json()["code"] == "OPERATION_INCOMPLETE"
    assert (await db.users.find_one({"id": TELE}, {"_id": 0}))["phone"] == "9111111111"
    assert await db.identity_audit.count_documents({"target_id": TELE}) == 1
    assert (await db.identity_operations.find_one({}, {"_id": 0}))["state"] == "validated"
    # the administrator moves on with a DIFFERENT key: the new operation first completes the dangling one, then applies
    monkeypatch.setattr(AsyncIOMotorCollection, "update_one", real_update)
    second = await _previewed(api_client, admin, _body("9222222222", expected="9111111111"))
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=second)
    assert res.status_code == 200 and "recovered" not in res.json()
    assert (await db.users.find_one({"id": TELE}, {"_id": 0}))["phone"] == "9222222222"
    assert await db.identity_operations.count_documents({"state": "done"}) == 2
    assert await db.identity_operations.count_documents({"state": {"$ne": "done"}}) == 0
    # the earlier operation was completed exactly once (no duplicate audit row) and now replays
    assert await db.identity_audit.count_documents({"target_id": TELE}) == 2
    replay = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=body)
    assert replay.status_code == 200 and replay.json()["replayed"] is True and replay.json()["new_phone"] == "9111111111"


@pytest.mark.asyncio
async def test_concurrent_submissions_produce_exactly_one_change(api_client, isolated_db, login_helper):
    admin = await _admin(login_helper)
    bodies = [await _previewed(api_client, admin, _body(n)) for n in ("9111111111", "9222222222", "9333333333")]
    results = await asyncio.gather(*[api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=b) for b in bodies])
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409, 409], [(r.status_code, r.text[:120]) for r in results]
    winner = next(r for r in results if r.status_code == 200).json()["new_phone"]
    losers = {r.json()["code"] for r in results if r.status_code == 409}
    assert losers <= {"VERSION_CONFLICT", "OPERATION_IN_PROGRESS"}
    user = await isolated_db["db"].users.find_one({"id": TELE}, {"_id": 0})
    assert user["phone"] == winner and user["phone_normalized"] == winner
    assert await isolated_db["db"].identity_audit.count_documents({"target_id": TELE}) == 1
    # the two other numbers were never written anywhere (no partial update, no stray identity)
    assert await isolated_db["db"].users.count_documents({"phone_normalized": {"$in": [b["new_phone"] for b in bodies if b["new_phone"] != winner]}}) == 0


@pytest.mark.asyncio
async def test_customer_promotion_keeps_two_people_separate(api_client, isolated_db, login_helper):
    db = isolated_db["db"]
    admin = await _admin(login_helper)
    preview = (await api_client.post(f"/api/integrations/staff/{TELE}/phone/preview", headers=_auth(admin), json={"new_phone": "9000000004"})).json()
    assert preview["status"] == "customer"
    customer_before = await db.users.find_one({"id": CUST}, {"_id": 0})
    tele_before = await db.users.find_one({"id": TELE}, {"_id": 0})
    # explicit promotion of the CUSTOMER's own account via the existing conversion operation (no manual ID typing by the admin:
    # the client passes the ID from the preview)
    res = await api_client.post(f"/api/integrations/staff/{preview['customer']['id']}/convert", headers=_auth(admin),
                                json={"role": "telecaller", "reason": "Joined the sales team as telecaller in September", "confirm_user_id": preview["customer"]["id"]})
    assert res.status_code == 200, res.text
    promoted = await db.users.find_one({"id": CUST}, {"_id": 0})
    assert promoted["role"] == "telecaller" and promoted["phone"] == "9000000004" and promoted["created_at"] == customer_before["created_at"]
    assert promoted["identity_events"][-1]["type"] == "conversion"
    tele_after = await db.users.find_one({"id": TELE}, {"_id": 0})
    assert tele_after["phone"] == tele_before["phone"] and tele_after.get("session_version", 0) == tele_before.get("session_version", 0), "the staff member being edited is untouched"
    assert await db.users.count_documents({"id": {"$in": [CUST, TELE]}}) == 2
    # afterwards the number counts as staff-owned for any further renumbering attempt
    res = await api_client.post(f"/api/integrations/staff/{TELE}/phone", headers=_auth(admin), json=_body("9000000004"))
    assert res.status_code == 409 and res.json()["code"] == "PHONE_OWNED_BY_STAFF"
