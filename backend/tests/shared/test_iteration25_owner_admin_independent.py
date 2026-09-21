"""Independent iteration-25 verification for the default owner-admin bootstrap.

Uses only the shared/conftest.py isolated fixtures (synthetic Mongo DB with intercepted SMS).
NEVER contacts a real phone. Every OTP is intercepted via isolated_db['sent_otps'].
"""
import pytest

import server  # noqa: F401 (imported for side-effects during app-based fixtures)
from shared import core as c
from shared import owner_admin

pytestmark = pytest.mark.asyncio

OWNER = "9000000000"
STAFF_HEADERS = {"X-Staff-Service-Key": "staff-service-key-1234567890-abcdef"}


# ---- helpers ---------------------------------------------------------------

async def _otp_login(api_client, isolated_db, phone, *, channel="mobile", headers=None):
    # Synthetic DB only: nuke otp_challenges to skip the 60-second cooldown between logins.
    await isolated_db["db"].otp_challenges.delete_many({"phone": phone})
    payload = {"phone": phone, "purpose": "login", "channel": channel}
    send = await api_client.post("/api/auth/send-otp", json=payload, headers=headers)
    assert send.status_code == 200, send.text
    otp = isolated_db["sent_otps"][(phone, "login")]
    verify = await api_client.post(
        "/api/auth/verify-otp",
        json={**payload, "otp": otp, "challenge_id": send.json().get("challenge_id")},
        headers=headers,
    )
    return verify


def _customer_doc(uid, phone, **extra):
    ts = c.stamp()
    return {"id": uid, "phone": phone, "phone_normalized": phone, "name": f"Customer {uid}",
            "role": "customer", "account_status": "active", "status": "active",
            "session_version": 0, "created_at": ts, "updated_at": ts,
            "onboarding_status": "completed", "phone_verified": True,
            "shop_name": "Shop " + uid, "location": "Delhi", **extra}


def _bearer(session):
    return {"Authorization": f"Bearer {session['token']}"}


# ---- (3a) empty DB: create + idempotent + both surfaces --------------------

async def test_a_empty_db_creates_owner_and_both_surfaces_return_admin(api_client, isolated_db, monkeypatch):
    db = isolated_db["db"]
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)

    assert await owner_admin.ensure_owner_admin() is True
    st = owner_admin.status()
    assert st["action"] == "created" and st["phone_suffix"] == "0000"

    docs = await db.users.find({"phone_normalized": OWNER}, {"_id": 0}).to_list(5)
    assert len(docs) == 1
    doc = docs[0]
    assert doc["role"] == "admin" and doc["account_status"] == "active"
    # No password/otp material on the record - real MSG91 OTP is the only sign-in path.
    assert not ({"password", "password_hash", "otp", "otp_hash", "access_key", "secret_hash"} & set(doc))
    owner_id = doc["id"]
    session_version_after_create = doc["session_version"]

    # Idempotent restart: same id, no promotion event added, session_version unchanged.
    assert await owner_admin.ensure_owner_admin() is True
    assert owner_admin.status()["action"] == "already_admin"
    after = await db.users.find_one({"phone_normalized": OWNER}, {"_id": 0})
    assert after["id"] == owner_id
    assert after["session_version"] == session_version_after_create
    assert await db.users.count_documents({"phone_normalized": OWNER}) == 1

    # Channel = mobile
    mobile = await _otp_login(api_client, isolated_db, OWNER)
    assert mobile.status_code == 200
    body = mobile.json()
    assert body["user"]["role"] == "admin"
    assert body["user"]["id"] == owner_id

    # Channel = portal with staff service key
    portal = await _otp_login(api_client, isolated_db, OWNER, channel="portal", headers=STAFF_HEADERS)
    assert portal.status_code == 200
    assert portal.json()["user"]["role"] == "admin"


# ---- (3b) legacy customer promotion, session revocation, no bleed ---------

async def test_b_legacy_customer_is_promoted_on_same_id_old_sessions_revoked(api_client, isolated_db, monkeypatch):
    db = isolated_db["db"]
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)

    # Legacy shape: only `phone`, no `phone_normalized`.
    legacy = _customer_doc("legacy-owner", OWNER, name="Legacy Owner")
    del legacy["phone_normalized"]
    await db.users.insert_many([legacy, _customer_doc("u_other", "9000000009")])

    # Old owner has an active OTP session as customer.
    old_owner = await _otp_login(api_client, isolated_db, OWNER)
    assert old_owner.status_code == 200
    old_owner_json = old_owner.json()
    assert old_owner_json["user"]["role"] == "customer"
    other = await _otp_login(api_client, isolated_db, "9000000009")
    assert other.status_code == 200
    other_json = other.json()

    prev_owner_doc = await db.users.find_one({"id": "legacy-owner"}, {"_id": 0})
    prev_sv = prev_owner_doc.get("session_version", 0)

    assert await owner_admin.ensure_owner_admin() is True
    assert owner_admin.status()["action"] == "promoted"

    promoted = await db.users.find_one({"id": "legacy-owner"}, {"_id": 0})
    assert promoted["role"] == "admin"
    assert promoted["session_version"] == prev_sv + 1
    events = promoted.get("identity_events") or []
    assert events and events[-1]["type"] == "owner_admin_bootstrap"
    assert events[-1]["old_role"] == "customer" and events[-1]["new_role"] == "admin"
    # No duplicate admin doc created for the number.
    assert await db.users.count_documents({"$or": [{"phone_normalized": OWNER}, {"phone": OWNER}]}) == 1

    # Old owner token is invalidated by the session bump.
    me = await api_client.get("/api/auth/me", headers=_bearer(old_owner_json))
    assert me.status_code == 401
    assert me.json().get("code") == "SESSION_REVOKED"

    # Unrelated customer's token and role untouched.
    me_other = await api_client.get("/api/auth/me", headers=_bearer(other_json))
    assert me_other.status_code == 200
    other_doc = await db.users.find_one({"id": "u_other"}, {"_id": 0})
    assert other_doc["role"] == "customer"
    assert other_doc.get("session_version", 0) == 0


# ---- (3c) two-record conflict is refused ----------------------------------

async def test_c_two_records_for_phone_are_refused_without_changes(api_client, isolated_db, monkeypatch):
    db = isolated_db["db"]
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)

    d1 = _customer_doc("u_first", OWNER)
    d2 = _customer_doc("u_second", "+91 90000 00000")
    del d2["phone_normalized"]  # legacy formatting, no normalized field -> regex still matches
    await db.users.insert_many([d1, d2])
    before = sorted([d async for d in db.users.find({}, {"_id": 0})], key=lambda x: x["id"])

    assert await owner_admin.ensure_owner_admin() is False
    st = owner_admin.status()
    assert st["reason"] == "OWNER_ADMIN_IDENTITY_CONFLICT"

    after = sorted([d async for d in db.users.find({}, {"_id": 0})], key=lambda x: x["id"])
    assert after == before  # nothing changed

    resp = await api_client.get("/api/health")
    assert resp.status_code == 503
    flow = resp.json()["flows"]["owner_admin"]
    assert flow["issues"] == ["OWNER_ADMIN_IDENTITY_CONFLICT"]
    assert flow["ready"] is False
    assert flow["phone_suffix"] == "0000"


# ---- (3d) owner protection through staff API ------------------------------

async def test_d_owner_record_is_protected_from_demotion_and_deletion(api_client, isolated_db, monkeypatch):
    db = isolated_db["db"]
    monkeypatch.setenv("OWNER_ADMIN_PHONE", OWNER)
    assert await owner_admin.ensure_owner_admin() is True
    owner = await db.users.find_one({"phone_normalized": OWNER}, {"_id": 0})

    # Seed a second admin who will attempt to touch the owner.
    await db.users.insert_one({**_customer_doc("u_admin2", "9000000002", name="Second Admin"),
                               "role": "admin"})
    admin2 = (await _otp_login(api_client, isolated_db, "9000000002")).json()

    r = await api_client.patch(f"/api/integrations/staff/{owner['id']}",
                               json={"role": "telecaller"}, headers=_bearer(admin2))
    assert r.status_code == 409
    assert r.json()["code"] == "OWNER_ADMIN_PROTECTED"

    d = await api_client.delete(f"/api/integrations/staff/{owner['id']}", headers=_bearer(admin2))
    assert d.status_code == 409
    assert d.json()["code"] == "OWNER_ADMIN_PROTECTED"

    # Harmless edit still allowed.
    rn = await api_client.patch(f"/api/integrations/staff/{owner['id']}",
                                json={"name": "X"}, headers=_bearer(admin2))
    assert rn.status_code == 200
    refreshed = await db.users.find_one({"id": owner["id"]}, {"_id": 0})
    assert refreshed["role"] == "admin" and refreshed["name"] == "X"


# ---- (4) regression sanity ------------------------------------------------

async def test_regression_last_admin_guard_still_holds_for_non_owner(api_client, isolated_db, monkeypatch):
    """A NON-owner sole active admin cannot demote itself: 409 LAST_ADMIN."""
    db = isolated_db["db"]
    # OWNER_ADMIN not configured for this test => sole admin is a plain admin, not the protected owner.
    monkeypatch.delenv("OWNER_ADMIN_PHONE", raising=False)
    await db.users.insert_one({**_customer_doc("u_sole_admin", "9000000008", name="Sole"),
                               "role": "admin"})
    session = (await _otp_login(api_client, isolated_db, "9000000008")).json()
    r = await api_client.patch("/api/integrations/staff/u_sole_admin",
                               json={"role": "telecaller"}, headers=_bearer(session))
    assert r.status_code == 409
    assert r.json()["code"] == "LAST_ADMIN"


async def test_regression_customer_portal_login_is_rejected_403_staff_only(api_client, isolated_db, monkeypatch):
    """A customer trying portal channel is refused with 403 STAFF_ONLY (staff key present)."""
    db = isolated_db["db"]
    await db.users.insert_one(_customer_doc("u_cust_portal", "9000000010"))
    r = await _otp_login(api_client, isolated_db, "9000000010", channel="portal", headers=STAFF_HEADERS)
    assert r.status_code == 403
    body = r.json()
    assert body.get("code") == "STAFF_ONLY", body
