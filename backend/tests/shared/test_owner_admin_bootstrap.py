"""Default owner administrator (OWNER_ADMIN_PHONE).

Startup bootstrap proven on isolated synthetic databases (SMS intercepted, no real number contacted):
creation when missing, same-record promotion with history kept and old sessions revoked, idempotent restarts,
refusal on identity conflict / inactive / deleted identity / invalid configuration without any change, protection
from demotion, disabling and deletion, and sign-in with role=admin on BOTH surfaces - the mobile app (channel
"mobile") and the website's staff exchange (channel "portal" with the staff service key)."""
import pytest
from fastapi import HTTPException

import server
from shared import core as c
from shared import owner_admin, people

pytestmark = pytest.mark.asyncio
OWNER = "9999813334"
STAFF_HEADERS = {"X-Staff-Service-Key": "staff-service-key-1234567890-abcdef"}


async def otp_login(api_client, isolated_db, phone, channel="mobile", headers=None):
    await isolated_db["db"].otp_challenges.delete_many({"phone": phone})  # synthetic DB only: skip the 60 s resend cooldown
    payload = {"phone": phone, "purpose": "login", "channel": channel}
    send = await api_client.post("/api/auth/send-otp", json=payload, headers=headers)
    assert send.status_code == 200, send.text
    otp = isolated_db["sent_otps"][(phone, "login")]
    verify = await api_client.post("/api/auth/verify-otp", json={**payload, "otp": otp, "challenge_id": send.json().get("challenge_id")},
                                   headers=headers)
    assert verify.status_code == 200, verify.text
    return verify.json()


def bearer(session):
    return {"Authorization": f"Bearer {session['token']}"}


def customer(uid, phone, **extra):
    ts = c.stamp()
    return {"id": uid, "phone": phone, "phone_normalized": phone, "name": f"Customer {uid}", "role": "customer",
            "account_status": "active", "status": "active", "session_version": 0, "created_at": ts, "updated_at": ts,
            "onboarding_status": "completed", "phone_verified": True, "shop_name": "Shop " + uid, "location": "Delhi", **extra}


async def test_missing_owner_record_is_created_as_admin_and_signs_in_on_both_surfaces(api_client, isolated_db, monkeypatch):
    db = isolated_db["db"]
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    assert await owner_admin.ensure_owner_admin() is True
    assert owner_admin.status()["action"] == "created" and owner_admin.status()["phone_suffix"] == "3334"
    docs = await db.users.find({"$or": [{"phone_normalized": OWNER}, {"phone": OWNER}]}, {"_id": 0}).to_list(5)
    assert len(docs) == 1
    owner = docs[0]
    assert owner["role"] == "admin" and c.account_status(owner) == "active" and owner["phone_normalized"] == OWNER
    assert not {"password", "password_hash", "otp", "access_key", "secret_hash"} & set(owner)  # nothing but the OTP flow signs in
    assert owner["identity_events"] == [{**owner["identity_events"][0], "type": "owner_admin_bootstrap", "old_role": None, "new_role": "admin", "created": True}]
    # Health reports the database fact, never a login.
    health = (await api_client.get("/api/health")).json()
    assert health["flows"]["owner_admin"]["ready"] is True and health["flows"]["owner_admin"]["state"] == "created"
    assert health["flows"]["owner_admin"]["phone_suffix"] == "3334" and health["configuration"]["OWNER_ADMIN_PHONE"] is True
    assert health["account_role_verified"] is False and health["capabilities"]["owner_admin_bootstrap"] == 1
    # Restart: nothing changes (same id, no second event, no session bump).
    assert await owner_admin.ensure_owner_admin() is True and owner_admin.status()["action"] == "already_admin"
    again = await db.users.find_one({"phone_normalized": OWNER}, {"_id": 0})
    assert again["id"] == owner["id"] and len(again["identity_events"]) == 1 and again["session_version"] == 0
    assert await db.users.count_documents({}) == 1
    # App: normal OTP login carries role=admin; website: portal exchange with the staff key carries role=admin.
    mobile = await otp_login(api_client, isolated_db, OWNER)
    assert mobile["user"]["role"] == "admin" and mobile["user"]["id"] == owner["id"]
    me = await api_client.get("/api/auth/me", headers=bearer(mobile))
    assert me.status_code == 200 and me.json()["role"] == "admin"
    portal = await otp_login(api_client, isolated_db, OWNER, channel="portal", headers=STAFF_HEADERS)
    assert portal["user"]["role"] == "admin" and portal["user"]["id"] == owner["id"]
    assert (await api_client.get("/api/auth/me", headers=bearer(portal))).json()["role"] == "admin"
    assert set(isolated_db["sent_otps"]) == {(OWNER, "login")}  # only the owner's own number ever received a code


async def test_existing_customer_record_is_promoted_on_the_same_id_and_old_sessions_are_revoked(api_client, isolated_db, monkeypatch):
    db = isolated_db["db"]
    history = [{"type": "enrollment", "at": c.stamp(), "source": "website"}]
    await db.users.insert_many([customer("bcdf18c9-test-owner", OWNER, name="Yash Owner", session_version=3, identity_events=list(history),
                                         registered_at="2025-01-01T00:00:00+00:00", reward_points=120),
                                customer("u_other", "9000000009")])
    old_owner = await otp_login(api_client, isolated_db, OWNER)
    other = await otp_login(api_client, isolated_db, "9000000009")
    assert old_owner["user"]["role"] == "customer"
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    assert await owner_admin.ensure_owner_admin() is True and owner_admin.status()["action"] == "promoted"
    owner = await db.users.find_one({"phone_normalized": OWNER}, {"_id": 0})
    assert owner["id"] == "bcdf18c9-test-owner" and owner["role"] == "admin" and owner["session_version"] == 4
    assert owner["name"] == "Yash Owner" and owner["reward_points"] == 120 and owner["registered_at"] == "2025-01-01T00:00:00+00:00"
    assert owner["identity_events"][0] == history[0]
    assert owner["identity_events"][1]["type"] == "owner_admin_bootstrap" and owner["identity_events"][1]["old_role"] == "customer"
    assert owner["identity_events"][1]["actor_id"] == "system:owner_admin_bootstrap"
    assert await db.users.count_documents({"$or": [{"phone_normalized": OWNER}, {"phone": OWNER}]}) == 1  # no duplicate admin
    # Old owner sessions are gone; the other account's session is untouched.
    assert (await api_client.get("/api/auth/me", headers=bearer(old_owner))).json()["code"] == "SESSION_REVOKED"
    assert (await api_client.post("/api/auth/refresh", json={"refresh_token": old_owner["refresh_token"]})).status_code == 401
    assert (await api_client.get("/api/auth/me", headers=bearer(other))).status_code == 200
    assert (await db.users.find_one({"id": "u_other"}, {"_id": 0}))["role"] == "customer"
    assert await db.session_families.count_documents({"user_id": "u_other", "revoked": False}) == 1
    # Fresh sign-ins carry the role on both surfaces.
    fresh = await otp_login(api_client, isolated_db, OWNER)
    assert fresh["user"]["role"] == "admin" and fresh["user"]["id"] == "bcdf18c9-test-owner"
    portal = await otp_login(api_client, isolated_db, OWNER, channel="portal", headers=STAFF_HEADERS)
    assert portal["user"]["role"] == "admin"
    # Restart keeps the new sessions.
    assert await owner_admin.ensure_owner_admin() is True and owner_admin.status()["action"] == "already_admin"
    assert (await db.users.find_one({"id": "bcdf18c9-test-owner"}, {"_id": 0}))["session_version"] == 4
    assert (await api_client.get("/api/auth/me", headers=bearer(fresh))).status_code == 200
    health = (await api_client.get("/api/health")).json()
    assert health["flows"]["owner_admin"]["ready"] is True and health["flows"]["owner_admin"]["state"] == "already_admin"


async def test_bootstrap_refuses_conflicts_inactive_deleted_and_invalid_configuration_without_changes(api_client, isolated_db, monkeypatch):
    db = isolated_db["db"]
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    # Two records carry the phone (one legacy formatting without phone_normalized): refuse, change nothing.
    legacy = {**customer("u_legacy", "+91 99998 13334"), "phone_normalized": None}
    del legacy["phone_normalized"]
    await db.users.insert_many([customer("u_first", OWNER), legacy])
    before = [d async for d in db.users.find({}, {"_id": 0}).sort("id", 1)]
    assert await owner_admin.ensure_owner_admin() is False and owner_admin.status()["reason"] == "OWNER_ADMIN_IDENTITY_CONFLICT"
    assert [d async for d in db.users.find({}, {"_id": 0}).sort("id", 1)] == before
    health = await api_client.get("/api/health")
    assert health.status_code == 503 and health.json()["flows"]["owner_admin"] == {
        "ready": False, "issues": ["OWNER_ADMIN_IDENTITY_CONFLICT"], "state": None, "phone_suffix": "3334",
        "detail": "2 records carry the owner phone; nothing changed"}
    # An inactive record is never promoted or reactivated.
    await db.users.delete_many({})
    await db.users.insert_one(customer("u_inactive", OWNER, account_status="inactive", status="inactive"))
    assert await owner_admin.ensure_owner_admin() is False and owner_admin.status()["reason"] == "OWNER_ADMIN_ACCOUNT_INACTIVE"
    doc = await db.users.find_one({"id": "u_inactive"}, {"_id": 0})
    assert doc["role"] == "customer" and doc["account_status"] == "inactive" and "identity_events" not in doc
    # A deleted identity is never resurrected.
    await db.users.delete_many({})
    await db.deleted_identities.insert_one({"phone_hash": c.keyed(OWNER), "user_id": "u_gone", "deleted_at": c.stamp()})
    assert await owner_admin.ensure_owner_admin() is False and owner_admin.status()["reason"] == "OWNER_ADMIN_DELETED_IDENTITY"
    assert await db.users.count_documents({}) == 0
    await db.deleted_identities.delete_many({})
    # Missing, placeholder or invalid phone: reported as configuration, nothing created.
    for value in ("", "SET_IN_PUBLISH_SECRETS", "12345", "abc"):
        monkeypatch.setenv("OWNER_ADMIN_PHONE", value)
        assert owner_admin.configured_phone() == ""
        assert await owner_admin.ensure_owner_admin() is False and owner_admin.status()["reason"] == "OWNER_ADMIN_PHONE"
    assert await db.users.count_documents({}) == 0
    body = (await api_client.get("/api/health")).json()
    assert body["flows"]["owner_admin"]["issues"] == ["OWNER_ADMIN_PHONE"] and body["configuration"]["OWNER_ADMIN_PHONE"] is False
    # +91 / spaced spellings normalise to the same national number.
    monkeypatch.setenv("OWNER_ADMIN_PHONE", "+91 99998-13334")
    assert owner_admin.configured_phone() == OWNER
    # Never inside the store-review scope.
    with c.scoped(c.REVIEW):
        with pytest.raises(RuntimeError):
            await owner_admin.ensure_owner_admin()


async def test_owner_admin_is_protected_from_demotion_disabling_and_deletion(api_client, isolated_db, monkeypatch):
    db = isolated_db["db"]
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    assert await owner_admin.ensure_owner_admin() is True
    owner = await db.users.find_one({"phone_normalized": OWNER}, {"_id": 0})
    await db.users.insert_one({**customer("u_admin2", "9000000002", name="Second Admin"), "role": "admin"})
    admin2 = await otp_login(api_client, isolated_db, "9000000002")
    for updates in ({"role": "telecaller"}, {"status": "inactive"}, {"account_status": "disabled"}):
        res = await api_client.patch(f"/api/integrations/staff/{owner['id']}", json=updates, headers=bearer(admin2))
        assert res.status_code == 409 and res.json()["code"] == "OWNER_ADMIN_PROTECTED", res.text
    res = await api_client.delete(f"/api/integrations/staff/{owner['id']}", headers=bearer(admin2))
    assert res.status_code == 409 and res.json()["code"] == "OWNER_ADMIN_PROTECTED"
    unchanged = await db.users.find_one({"id": owner["id"]}, {"_id": 0})
    assert unchanged["role"] == "admin" and c.account_status(unchanged) == "active" and unchanged["session_version"] == owner["session_version"]
    # Harmless edits stay possible; the second admin can still be demoted by the owner (the guard is owner-specific).
    renamed = await api_client.patch(f"/api/integrations/staff/{owner['id']}", json={"name": "Yash Owner"}, headers=bearer(admin2))
    assert renamed.status_code == 200 and renamed.json()["user"]["role"] == "admin"
    owner_session = await otp_login(api_client, isolated_db, OWNER)
    demoted = await api_client.patch("/api/integrations/staff/u_admin2", json={"role": "telecaller"}, headers=bearer(owner_session))
    assert demoted.status_code == 200 and demoted.json()["user"]["role"] == "telecaller"
    # Deletion paths: admins cannot use self-deletion at all, and erase() refuses the owner record explicitly.
    res = await api_client.post("/api/auth/delete-account/request", headers=bearer(owner_session))
    assert res.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await people.erase(await db.users.find_one({"id": owner["id"]}, {"_id": 0}), "website")
    assert exc.value.detail["code"] == "OWNER_ADMIN_PROTECTED"
    assert await db.deleted_identities.count_documents({}) == 0
    assert owner_admin.is_owner(owner) and not owner_admin.is_owner({"phone": "9000000002"}) and not owner_admin.is_owner(None)


async def test_real_startup_handler_runs_the_bootstrap_after_indexes(api_client, isolated_db, monkeypatch):
    db = isolated_db["db"]
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    monkeypatch.setattr(server, "init_storage", lambda: None, raising=False)

    async def no_provider_call(force=False):
        return {"skipped": True}

    monkeypatch.setattr(server, "_msg91_preflight", no_provider_call, raising=False)
    await server.startup()
    owner = await db.users.find_one({"phone_normalized": OWNER}, {"_id": 0})
    assert owner and owner["role"] == "admin" and owner_admin.status()["action"] == "created"
    indexes = await db.users.index_information()
    assert any(spec.get("unique") and spec["key"] == [("phone_normalized", 1)] for spec in indexes.values())
    health = (await api_client.get("/api/health")).json()
    assert health["flows"]["owner_admin"]["ready"] is True
