"""R08 (15-second server-driven OTP cooldown), R01-B (sliding session, refresh race), R05 (MCX units), R09 (admin
notification campaigns, audience, permissions, idempotent send, invalid-token cleanup, preferences, logout unlink),
R10 (Upload Executive access matrix), R15 (real staff/customer deletion vs disable), R03 (discovery sessions)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from shared import auth, commerce, core as c, notifications

pytestmark = pytest.mark.asyncio


async def auth_headers(login_helper, phone):
    body = await login_helper(phone)
    return {"Authorization": f"Bearer {body['token']}"}, body


# ---- R08 --------------------------------------------------------------------------------------------------------------

async def test_otp_cooldown_is_15_seconds_server_driven_and_atomic(api_client, isolated_db, seeded_users, monkeypatch):
    clock = {"now": datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(c, "now", lambda: clock["now"])
    payload = {"phone": "9000000004", "purpose": "login", "channel": "mobile"}
    first = await api_client.post("/api/auth/send-otp", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["resend_after"] == 15 and first.json()["resend_at"] == (clock["now"] + timedelta(seconds=15)).isoformat()
    assert first.json()["server_time"] == clock["now"].isoformat() and first.json()["expires_in"] == 600
    clock["now"] += timedelta(seconds=14, microseconds=999000)
    early = await api_client.post("/api/auth/send-otp", json=payload)
    assert early.status_code == 429 and early.json()["code"] == "OTP_COOLDOWN" and early.json()["retry_after"] == 1 and early.headers["retry-after"] == "1"
    clock["now"] += timedelta(microseconds=1000)   # exactly 15 s
    ok = await api_client.post("/api/auth/send-otp", json=payload)
    assert ok.status_code == 200, ok.text
    # the previous code is superseded; the fresh one verifies
    clock["now"] += timedelta(seconds=20)
    otp = isolated_db["sent_otps"][("9000000004", "login")]
    verify = await api_client.post("/api/auth/verify-otp", json={**payload, "otp": otp, "challenge_id": ok.json()["challenge_id"]})
    assert verify.status_code == 200
    # parallel taps: exactly one dispatch
    clock["now"] += timedelta(seconds=20)
    before = len(isolated_db["sent_otps"])
    results = await asyncio.gather(*[api_client.post("/api/auth/send-otp", json=payload) for _ in range(4)])
    assert sorted(r.status_code for r in results) == [200, 429, 429, 429]
    # abuse budget (5 per 10 minutes per number) still applies and reports the real retry time
    for _ in range(3):
        clock["now"] += timedelta(seconds=16)
        r = await api_client.post("/api/auth/send-otp", json=payload)
    assert r.status_code == 429 and r.json()["code"] == "OTP_RATE_LIMIT" and r.json()["retry_after"] > 15 and "resend_at" in r.json()
    # deletion purpose uses the same cooldown
    assert auth.RESEND_COOLDOWN_SECONDS == 15


# ---- R01-B ------------------------------------------------------------------------------------------------------------

async def test_session_family_slides_on_refresh_and_refresh_race_is_not_theft(api_client, isolated_db, seeded_users, login_helper, monkeypatch):
    db = isolated_db["db"]
    clock = {"now": datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(c, "now", lambda: clock["now"])
    headers, body = await auth_headers(login_helper, "9000000004")
    family = await db.session_families.find_one({"user_id": "u_cust1"})
    assert family["expires_at"] == (clock["now"] + timedelta(days=30)).isoformat()
    # 29 days later (past the access token, inside the idle window): refresh keeps the device signed in and slides expiry
    clock["now"] += timedelta(days=29)
    assert (await api_client.get("/api/auth/me", headers=headers)).status_code == 401
    refreshed = await api_client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    assert (await db.session_families.find_one({"user_id": "u_cust1"}))["expires_at"] == (clock["now"] + timedelta(days=30)).isoformat()
    assert refreshed.json()["session"]["idle_expiry_days"] == 30
    # 35 days after the ORIGINAL login the account is still usable (would have been logged out under the fixed 30-day rule)
    clock["now"] += timedelta(days=6)
    second = await api_client.post("/api/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]})
    assert second.status_code == 200   # (JWT `iat` in the faked future cannot be presented to /auth/me under a real clock; the family state is asserted directly)
    family = await db.session_families.find_one({"user_id": "u_cust1"})
    assert family["revoked"] is False and family["expires_at"] == (clock["now"] + timedelta(days=30)).isoformat()
    # concurrent duplicate refresh with the SAME token within the race window: 409, family NOT revoked
    race = await api_client.post("/api/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]})
    assert race.status_code == 409 and race.json()["code"] == "REFRESH_IN_PROGRESS"
    assert (await db.session_families.find_one({"user_id": "u_cust1"}))["revoked"] is False
    # later reuse of an old token is theft: family revoked, everything signed out (the newest refresh token dies with it)
    clock["now"] += timedelta(minutes=5)
    theft = await api_client.post("/api/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]})
    assert theft.status_code == 401 and theft.json()["code"] == "REFRESH_INVALID"
    assert (await db.session_families.find_one({"user_id": "u_cust1"}))["revoked"] is True
    assert (await api_client.post("/api/auth/refresh", json={"refresh_token": second.json()["refresh_token"]})).status_code == 401
    # idle expiry: a device silent for more than 30 days must sign in again
    h2, b2 = await auth_headers(login_helper, "9000000005")
    clock["now"] += timedelta(days=31)
    assert (await api_client.post("/api/auth/refresh", json={"refresh_token": b2["refresh_token"]})).status_code == 401
    # logout with the device token unlinks that device only (real clock again: JWT `iat` must not lie in the future)
    clock["now"] = datetime.now(timezone.utc)
    h3, b3 = await auth_headers(login_helper, "9000000001")
    await api_client.post("/api/notifications/devices", json={"token": "ExponentPushToken[dev1aaaaaaaaaaa]", "platform": "android"}, headers=h3)
    out = await api_client.post("/api/auth/logout", json={"push_token": "ExponentPushToken[dev1aaaaaaaaaaa]"}, headers=h3)
    assert out.status_code == 200
    assert (await db.push_devices.find_one({"token": "ExponentPushToken[dev1aaaaaaaaaaa]"}))["enabled"] is False
    assert (await api_client.post("/api/auth/refresh", json={"refresh_token": b3["refresh_token"]})).status_code == 401


# ---- R05 --------------------------------------------------------------------------------------------------------------

def test_mcx_unit_conversions_are_deterministic():
    assert commerce.mcx_canonical("silver", 100000) == 100.0
    assert commerce.mcx_canonical("gold", 75000) == 7500.0
    assert commerce.mcx_display("silver", 100.0) == 100000.0 and commerce.mcx_display("gold", 7500.0) == 75000.0
    assert commerce.mcx_display("silver", commerce.mcx_canonical("silver", 123456.78)) == 123456.78
    assert commerce.mcx_display("gold", commerce.mcx_canonical("gold", 74321.5)) == 74321.5


async def test_mcx_display_units_round_trip_and_calculated_physical(api_client, isolated_db, seeded_users, login_helper):
    admin, _ = await auth_headers(login_helper, "9999813334")
    latest = (await api_client.get("/api/rates/latest")).json()
    assert latest["units"]["mcx_display"] == {"silver": "INR/kg", "gold": "INR/10g"} and latest["mcx_units_verified"] is False
    assert latest["silver_mcx_display_rate"] == 99000.0 and latest["gold_mcx_display_rate"] == 49000.0   # seeded 99 INR/g, 4900 INR/g
    # unit-aware client saves market units; the physical rate is computed in matching INR/g
    r = await api_client.post("/api/rates", json={"version": latest["version"], "silver_mcx_display_rate": 100000, "gold_mcx_display_rate": 75000,
                                                  "silver_physical_mode": "calculated", "silver_physical_premium": 2.5,
                                                  "gold_physical_mode": "calculated", "gold_physical_premium": 40}, headers=admin)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["silver_mcx_rate"] == 100.0 and saved["gold_mcx_rate"] == 7500.0
    assert saved["silver_physical_rate"] == 102.5 and saved["gold_physical_rate"] == 7540.0
    assert saved["silver_mcx_display_rate"] == 100000.0 and saved["gold_mcx_display_rate"] == 75000.0 and saved["mcx_units_verified"] is True
    reread = (await api_client.get("/api/rates/latest")).json()
    assert reread["silver_mcx_display_rate"] == 100000.0 and reread["gold_physical_rate"] == 7540.0
    # an old client still writes canonical INR/g and reads the same numbers
    r = await api_client.post("/api/rates", json={"version": reread["version"], "silver_mcx_rate": 101}, headers=admin)
    assert r.status_code == 200 and r.json()["silver_mcx_display_rate"] == 101000.0 and r.json()["silver_physical_rate"] == 103.5
    # both forms at once is refused, nothing guessed
    both = await api_client.post("/api/rates", json={"version": r.json()["version"], "silver_mcx_rate": 1, "silver_mcx_display_rate": 1000}, headers=admin)
    assert both.status_code == 422 and both.json()["code"] == "MCX_UNIT_AMBIGUOUS"
    # movement comparison in display units
    assert commerce.mcx_display("silver", 101) - commerce.mcx_display("silver", 100) == 1000.0


# ---- R09 --------------------------------------------------------------------------------------------------------------

@pytest.fixture
def push_double(monkeypatch):
    sent, receipts = [], {}

    async def fake_send(messages):
        sent.append(list(messages))
        out = []
        for i, m in enumerate(messages):
            if m["to"].endswith("dead]"):
                out.append({"status": "error", "message": "not registered", "details": {"error": "DeviceNotRegistered"}})
            else:
                out.append({"status": "ok", "id": f"ticket-{len(sent)}-{i}"})
        return out

    async def fake_receipts(ids):
        return {i: receipts.get(i, {"status": "ok"}) for i in ids}

    monkeypatch.setattr(notifications, "transport", fake_send)
    monkeypatch.setattr(notifications, "receipts_transport", fake_receipts)
    return {"sent": sent, "receipts": receipts}


async def test_campaigns_audience_permissions_and_durable_delivery(api_client, isolated_db, seeded_users, login_helper, push_double):
    db = isolated_db["db"]
    await db.users.update_many({"id": {"$in": ["u_cust1", "u_cust2"]}}, {"$set": {"customer_type": "wholesale"}})
    await db.users.update_one({"id": "u_cust2"}, {"$set": {"assigned_salesperson": "u_tele1", "lead_status": "interested"}})
    tokens = {"u_cust1": ["ExponentPushToken[c1aaaaaaaaaaaaa]", "ExponentPushToken[c1bbbbbbbbbbbbb]"], "u_cust2": ["ExponentPushToken[c2cccccccccdead]"],
              "u_inactive": [], "u_tele1": ["ExponentPushToken[t1ddddddddddddd]"]}
    sessions = {}
    for uid, toks in tokens.items():
        if uid == "u_inactive":
            continue
        h, _ = await auth_headers(login_helper, seeded_users[uid]["phone"])
        sessions[uid] = h
        for t in toks:
            r = await api_client.post("/api/notifications/devices", json={"token": t, "platform": "android"}, headers=h)
            assert r.status_code == 200, r.text
    assert (await api_client.post("/api/notifications/devices", json={"token": "junk-token-value", "platform": "ios"}, headers=sessions["u_cust1"])).status_code == 422
    admin, _ = await auth_headers(login_helper, "9999813334")
    # non-admins are denied everything under /admin/notifications
    for h in (sessions["u_cust1"], sessions["u_tele1"]):
        assert (await api_client.get("/api/admin/notifications/filters", headers=h)).status_code == 403
        assert (await api_client.post("/api/admin/notifications/campaigns", json={"title": "x", "body": "y"}, headers=h)).status_code == 403
    filters = (await api_client.get("/api/admin/notifications/filters", headers=admin)).json()
    assert "Delhi" in filters["cities"] and filters["customer_types"] == ["wholesale"] and any(t["id"] == "u_tele1" for t in filters["telecallers"])
    # audience counts: users vs devices, AND/OR, exclusions
    a = (await api_client.post("/api/admin/notifications/audience", json={"target": "customers"}, headers=admin)).json()
    assert a["users"] == 2 and a["reachable_users"] == 2 and a["devices"] == 3          # inactive customer excluded
    a = (await api_client.post("/api/admin/notifications/audience", json={"target": "customers", "cities": ["delhi"], "customer_types": ["wholesale"], "match": "all"}, headers=admin)).json()
    assert a["users"] == 1
    a = (await api_client.post("/api/admin/notifications/audience", json={"target": "customers", "cities": ["mumbai"], "assigned_telecaller": "u_tele1", "match": "any"}, headers=admin)).json()
    assert a["users"] == 1
    a = (await api_client.post("/api/admin/notifications/audience", json={"target": "selected", "customer_ids": ["u_cust1", "u_inactive"]}, headers=admin)).json()
    assert a["users"] == 1
    # marketing opt-out excludes the person from campaigns but not from operational alerts
    assert (await api_client.put("/api/notifications/preferences", json={"marketing": False}, headers=sessions["u_cust2"])).status_code == 200
    a = (await api_client.post("/api/admin/notifications/audience", json={"target": "customers"}, headers=admin)).json()
    assert a["users"] == 1
    await api_client.put("/api/notifications/preferences", json={"marketing": True}, headers=sessions["u_cust2"])
    # draft -> preview -> test-send -> confirm with the inspected count -> queued -> worker -> sent + invalid token cleanup
    bad = await api_client.post("/api/admin/notifications/campaigns", json={"title": "Sale", "body": "b", "destination": "https://evil.example"}, headers=admin)
    assert bad.status_code == 422
    draft = await api_client.post("/api/admin/notifications/campaigns", json={"title": "Diwali offer", "body": "New silver collection is live", "image_url": "https://cdn.example.com/offer.png",
                                                                             "destination": "/(tabs)", "audience": {"target": "customers"}}, headers=admin)
    assert draft.status_code == 200, draft.text
    cid = draft.json()["id"]
    assert (await api_client.post(f"/api/admin/notifications/campaigns/{cid}/test", headers=admin)).status_code == 409   # admin has no device yet
    await api_client.post("/api/notifications/devices", json={"token": "ExponentPushToken[admin0000000000]", "platform": "ios"}, headers=admin)
    test = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/test", headers=admin)
    assert test.status_code == 200 and test.json()["devices"] == 1
    stale = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 5}, headers=admin)
    assert stale.status_code == 409 and stale.json()["code"] == "AUDIENCE_CHANGED"
    sent = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 2}, headers=admin)
    assert sent.status_code == 200 and sent.json()["users"] == 2 and sent.json()["devices"] == 3 and sent.json()["batches"] == 1
    dup = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 2}, headers=admin)
    assert dup.status_code == 409 and dup.json()["code"] == "CAMPAIGN_ALREADY_SENT"
    assert await db.notifications.count_documents({"campaign_id": cid, "kind": "marketing"}) == 3   # 2 recipients + admin test row
    await notifications.tick()
    batches = [b for b in push_double["sent"] if any(m["data"]["campaign_id"] == cid and m["to"] != "ExponentPushToken[admin0000000000]" for m in b)]
    assert len(batches) == 1 and len(batches[0]) == 3
    msg = batches[0][0]
    assert msg["richContent"] == {"image": "https://cdn.example.com/offer.png"} and msg["mutableContent"] is True and msg["channelId"] == "marketing"
    assert msg["data"]["destination"] == "/(tabs)" and "_user_id" not in msg
    campaign = (await api_client.get(f"/api/admin/notifications/campaigns/{cid}", headers=admin)).json()
    assert campaign["status"] == "sent" and campaign["stats"]["accepted"] == 3 and campaign["stats"]["invalid_tokens"] == 1 and campaign["stats"]["errors"] == 1
    assert (await db.push_devices.find_one({"token": "ExponentPushToken[c2cccccccccdead]"}))["enabled"] is False
    assert all(job["status"] == "sent" for job in campaign["outbox"])
    history = (await api_client.get("/api/admin/notifications/campaigns", headers=admin)).json()
    assert history["total"] == 1 and history["provider"]["provider"] == "expo_push_service"
    # inbox / read state for a recipient; nothing for the excluded inactive account
    inbox = (await api_client.get("/api/notifications/inbox", headers=sessions["u_cust1"])).json()
    assert inbox["unread"] == 1 and inbox["notifications"][0]["title"] == "Diwali offer"
    assert (await api_client.post(f"/api/notifications/inbox/{inbox['notifications'][0]['id']}/read", headers=sessions["u_cust1"])).status_code == 200
    assert (await api_client.get("/api/notifications/inbox", headers=sessions["u_cust1"])).json()["unread"] == 0
    assert (await api_client.post(f"/api/notifications/inbox/{inbox['notifications'][0]['id']}/read", headers=sessions["u_cust2"])).status_code == 404
    assert await db.notifications.count_documents({"user_id": "u_inactive"}) == 0
    # provider outage: retry with backoff, then success; no duplicate batch
    calls = {"n": 0}

    async def flaky(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("provider down")
        return [{"status": "ok", "id": f"late-{i}"} for i, _ in enumerate(messages)]
    notifications.transport = flaky
    await notifications.fan_out("manual:1", "operational", ["u_cust1"], "Hello", "retry me", "/notifications")
    await notifications.tick()
    job = await db.notification_outbox.find_one({"key": "manual:1:0"})
    assert job["status"] == "pending" and job["attempts"] == 1 and job["errors"][0]["error"] == "RuntimeError"
    await db.notification_outbox.update_one({"key": "manual:1:0"}, {"$set": {"next_attempt_at": c.stamp()}})
    await notifications.tick()
    job = await db.notification_outbox.find_one({"key": "manual:1:0"})
    assert job["status"] == "sent" and job["attempts"] == 2 and calls["n"] == 2
    # account switch on the same device re-links the token to the new account only
    h_other, _ = await auth_headers(login_helper, "9000000005")
    await api_client.post("/api/notifications/devices", json={"token": "ExponentPushToken[c1aaaaaaaaaaaaa]", "platform": "android"}, headers=h_other)
    dev = await db.push_devices.find_one({"token": "ExponentPushToken[c1aaaaaaaaaaaaa]"})
    assert dev["user_id"] == "u_cust2" and dev["enabled"] is True and await db.push_devices.count_documents({"token": "ExponentPushToken[c1aaaaaaaaaaaaa]"}) == 1


# ---- R10 --------------------------------------------------------------------------------------------------------------

async def test_upload_executive_matrix(api_client, isolated_db, seeded_users, login_helper):
    db = isolated_db["db"]
    admin, _ = await auth_headers(login_helper, "9999813334")
    created = await api_client.post("/api/integrations/staff", json={"phone": "9000000010", "name": "Uploader", "role": "upload_executive"}, headers=admin)
    assert created.status_code == 200 and created.json()["user"]["role"] == "upload_executive"
    up, body = await auth_headers(login_helper, "9000000010")
    assert body["user"]["role"] == "upload_executive"
    # portal (website) staff exchange accepts the role as staff
    await db.otp_challenges.delete_many({"phone": "9000000010"})   # test convenience: skip the 15 s cooldown of the sign-in above
    portal = await api_client.post("/api/auth/send-otp", json={"phone": "9000000010", "purpose": "login", "channel": "portal"},
                                   headers={"X-Staff-Service-Key": "staff-service-key-1234567890-abcdef"})
    assert portal.status_code == 200
    allowed = [("get", "/api/pdf-template/capabilities"), ("get", "/api/products?include_hidden=true"), ("get", "/api/admin/media/usage")]
    for method, path in allowed:
        r = await getattr(api_client, method)(path, headers=up)
        assert r.status_code == 200, (path, r.text)
    init = await api_client.post("/api/pdf-upload/init", json={"filename": "cat.pdf", "size": 1000, "total_chunks": 1, "sha256": "a" * 64}, headers=up)
    assert init.status_code in {200, 422}, init.text   # route reachable for the role (422 only for schema details, never 403)
    assert init.status_code != 403
    r = await api_client.post("/api/products", json={"title": "x"}, headers=up)
    assert r.status_code != 403
    r = await api_client.post("/api/banners", json={"title": "b", "image_url": "/api/files/x.png"}, headers=up)
    assert r.status_code != 403
    denied = [("get", "/api/customers"), ("get", "/api/customers/search?q=cu"), ("get", "/api/integrations/staff"), ("get", "/api/requests?view=all_pending"),
              ("get", "/api/requests/staff-options"), ("get", "/api/requests/metrics/summary"), ("get", "/api/admin/notifications/filters"),
              ("get", "/api/rates/audit"), ("get", "/api/analytics/dashboard"), ("get", "/api/telecaller/summary"), ("get", "/api/rewards/config"),
              ("get", "/api/admin/deletion-requests"), ("get", "/api/executives")]
    for method, path in denied:
        r = await getattr(api_client, method)(path, headers=up)
        assert r.status_code == 403, (path, r.status_code, r.text)
    assert (await api_client.post("/api/rates", json={"version": 0, "silver_mcx_rate": 1}, headers=up)).status_code == 403
    assert (await api_client.patch("/api/integrations/staff/u_tele1", json={"status": "inactive"}, headers=up)).status_code == 403
    # disabled upload executive loses access immediately; role change revokes sessions
    r = await api_client.patch(f"/api/integrations/staff/{body['user']['id']}", json={"status": "inactive"}, headers=admin)
    assert r.status_code == 200
    assert (await api_client.get("/api/pdf-template/capabilities", headers=up)).status_code == 401
    # customer cannot reach content routes
    cust, _ = await auth_headers(login_helper, "9000000004")
    assert (await api_client.get("/api/pdf-template/capabilities", headers=cust)).status_code == 403
    assert c.ROLE_LABELS["upload_executive"] == "Upload Executive"


# ---- R15 --------------------------------------------------------------------------------------------------------------

async def test_disable_vs_delete_for_staff_and_customers(api_client, isolated_db, seeded_users, login_helper):
    db = isolated_db["db"]
    admin, _ = await auth_headers(login_helper, "9999813334")
    t1, t1_body = await auth_headers(login_helper, "9000000001")
    await api_client.post("/api/notifications/devices", json={"token": "ExponentPushToken[t1xxxxxxxxxxxxx]", "platform": "android"}, headers=t1)
    # legacy DELETE alias still DISABLES and says so
    r = await api_client.delete("/api/integrations/staff/u_tele1", headers=admin)
    assert r.status_code == 200 and r.json()["disabled"] is True and r.json()["deleted"] is False
    assert (await api_client.get("/api/auth/me", headers=t1)).status_code == 401
    assert (await api_client.post("/api/auth/refresh", json={"refresh_token": t1_body["refresh_token"]})).status_code == 401
    assert (await api_client.post("/api/auth/send-otp", json={"phone": "9000000001", "purpose": "login", "channel": "mobile"})).status_code == 403
    assert (await db.push_devices.find_one({"user_id": "u_tele1"}))["enabled"] is False
    # re-enable is explicit and reversible
    r = await api_client.patch("/api/integrations/staff/u_tele1", json={"status": "active"}, headers=admin)
    assert r.status_code == 200 and r.json()["user"]["status"] == "active"
    t1, _ = await auth_headers(login_helper, "9000000001")
    assert (await api_client.get("/api/auth/me", headers=t1)).status_code == 200
    # deletion requires step-up (recent OTP) + confirmations; owner and self protected; idempotent retry
    payload = {"reason": "left the company last week", "confirm_user_id": "u_tele1", "confirm_phone_last4": "0001"}
    wrong = await api_client.post("/api/integrations/staff/u_tele1/delete", json={**payload, "confirm_phone_last4": "9999"}, headers=admin)
    assert wrong.status_code == 409 and wrong.json()["code"] == "CONFIRMATION_REQUIRED"
    owner = await api_client.post("/api/integrations/staff/u_admin/delete", json={"reason": "should never work", "confirm_user_id": "u_admin", "confirm_phone_last4": "3334"}, headers=admin)
    assert owner.status_code == 409 and owner.json()["code"] in {"OWNER_ADMIN_PROTECTED", "SELF_DELETION_DENIED", "LAST_ADMIN"}
    # give the telecaller an open claimed query first
    await db.products.insert_one({"id": "p1", "title": "Ring", "metal_type": "silver", "visibility": "visible", "is_deleted": False, "created_at": c.stamp()})
    cust, _ = await auth_headers(login_helper, "9000000004")
    rid = (await api_client.post("/api/requests", json={"request_type": "callback"}, headers=cust)).json()["id"]
    assert (await api_client.post(f"/api/requests/{rid}/claim", headers=t1)).status_code == 200
    deleted = await api_client.post("/api/integrations/staff/u_tele1/delete", json=payload, headers=admin)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True and deleted.json()["queries_released"] == 1 and deleted.json()["reference"] == "DEL-u_tele1"
    again = await api_client.post("/api/integrations/staff/u_tele1/delete", json=payload, headers=admin)
    assert again.status_code == 200 and again.json()["already_deleted"] is True
    doc = await db.requests.find_one({"id": rid}, {"_id": 0})
    assert doc["status"] == "pending" and doc["assignee_id"] == ""
    tomb = await db.users.find_one({"id": "u_tele1"}, {"_id": 0})
    assert tomb["account_status"] == "deleted" and tomb["phone"].startswith("deleted:")
    assert (await api_client.get("/api/auth/me", headers=t1)).status_code == 401
    assert await db.push_devices.count_documents({"user_id": "u_tele1"}) == 0
    assert await db.identity_audit.count_documents({"type": "admin_account_deletion", "target_id": "u_tele1"}) == 1
    # the number is not silently re-enrolled as the old identity: a fresh sign-up is a NEW account
    send = await api_client.post("/api/auth/send-otp", json={"phone": "9000000001", "purpose": "login", "channel": "mobile"})
    assert send.status_code == 200 and send.json()["account_exists"] is False
    fresh = await api_client.post("/api/auth/verify-otp", json={"phone": "9000000001", "purpose": "login", "channel": "mobile", "accept_terms": True,
                                                              "otp": isolated_db["sent_otps"][("9000000001", "login")], "challenge_id": send.json()["challenge_id"]})
    assert fresh.status_code == 200 and fresh.json()["is_new_account"] is True
    assert fresh.json()["user"]["id"] != "u_tele1" and fresh.json()["user"]["role"] == "customer"
    # customer: disable (reversible, blocks auth) vs delete (erasure workflow)
    r = await api_client.patch("/api/customers/u_cust2", json={"account_status": "inactive"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "inactive"
    assert (await api_client.post("/api/auth/send-otp", json={"phone": "9000000005", "purpose": "login", "channel": "mobile"})).status_code == 403
    r = await api_client.patch("/api/customers/u_cust2", json={"account_status": "active"}, headers=admin)
    assert r.json()["status"] == "active"
    r = await api_client.post("/api/customers/u_cust2/delete", json={"reason": "customer asked by phone", "confirm_user_id": "u_cust2", "confirm_phone_last4": "0005"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "external_erasure_pending" and r.json()["provider_erasure"]
    assert (await api_client.post("/api/customers/u_cust1/delete", json={"reason": "wrong last four digits", "confirm_user_id": "u_cust1", "confirm_phone_last4": "0000"}, headers=admin)).status_code == 409
    # a non-recent admin session cannot delete (step-up)
    await db.session_families.update_many({"user_id": "u_admin"}, {"$set": {"authenticated_at": (c.now() - timedelta(hours=2)).isoformat()}})
    old = await api_client.post("/api/customers/u_cust1/delete", json={"reason": "stale session attempt", "confirm_user_id": "u_cust1", "confirm_phone_last4": "0004"}, headers=admin)
    assert old.status_code == 403 and old.json()["code"] == "RECENT_AUTH_REQUIRED"


# ---- R03 --------------------------------------------------------------------------------------------------------------

async def test_legacy_executives_routes_delegate_to_the_canonical_staff_directory(api_client, isolated_db, seeded_users, login_helper):
    """The panel's legacy /executives family (used by installed builds) must behave exactly like /integrations/staff:
    Upload Executive creatable, explicit promotion for customer numbers (never a silent upgrade), disabled accounts stay
    listed with their status so they can be re-enabled, disable revokes sessions and detaches devices."""
    db = isolated_db["db"]
    admin, _ = await auth_headers(login_helper, "9999813334")
    created = await api_client.post("/api/executives", json={"name": "Uma Upload", "phone": "9000000077", "code": "UP01", "role": "upload_executive"}, headers=admin)
    assert created.status_code == 200, created.text
    assert created.json()["role"] == "upload_executive" and created.json()["created"] is True
    uid = created.json()["id"]
    # a customer's number is never upgraded silently
    promo = await api_client.post("/api/executives", json={"name": "X", "phone": "9000000004", "code": "T9", "role": "executive"}, headers=admin)
    assert promo.status_code == 409 and promo.json()["code"] == "EXPLICIT_CONVERSION_REQUIRED" and promo.json()["customer"]["id"] == "u_cust1"
    # invalid role / invalid number are actionable errors, not silent failures
    bad_role = await api_client.post("/api/executives", json={"name": "X", "phone": "9000000078", "code": "T9", "role": "customer"}, headers=admin)
    assert bad_role.status_code == 422 and bad_role.json()["code"] == "STAFF_ROLE_REQUIRED"
    assert (await api_client.post("/api/executives", json={"name": "X", "phone": "12", "code": "T9", "role": "executive"}, headers=admin)).status_code == 422
    # the new account signs in and is then disabled through the legacy DELETE (reversible)
    up, up_body = await auth_headers(login_helper, "9000000077")
    await api_client.post("/api/notifications/devices", json={"token": "ExponentPushToken[upxxxxxxxxxxxxx]", "platform": "android"}, headers=up)
    disabled = await api_client.delete(f"/api/executives/{uid}", headers=admin)
    assert disabled.status_code == 200 and disabled.json()["disabled"] is True and disabled.json()["deleted"] is False
    assert (await api_client.get("/api/auth/me", headers=up)).status_code == 401
    assert (await api_client.post("/api/auth/refresh", json={"refresh_token": up_body["refresh_token"]})).status_code == 401
    assert (await db.push_devices.find_one({"user_id": uid}))["enabled"] is False
    listed = (await api_client.get("/api/executives", headers=admin)).json()["executives"]
    row = next(u for u in listed if u["id"] == uid)
    assert row["status"] == "inactive" and row["customer_code"] == "UP01"          # still visible -> can be re-enabled
    assert [u["id"] for u in (await api_client.get("/api/executives?status=inactive", headers=admin)).json()["executives"]] == [uid]
    enabled = await api_client.put(f"/api/executives/{uid}", json={"status": "active", "name": "Uma U."}, headers=admin)
    assert enabled.status_code == 200 and enabled.json()["status"] == "active" and enabled.json()["name"] == "Uma U."
    up, _ = await auth_headers(login_helper, "9000000077")
    assert (await api_client.get("/api/auth/me", headers=up)).status_code == 200
    # the login number is never changed through the generic update
    assert (await api_client.put(f"/api/executives/{uid}", json={"phone": "9000000079"}, headers=admin)).status_code == 409
    # owner protection surfaces as an actionable 409 on the legacy route as well
    guard = await api_client.delete("/api/executives/u_admin", headers=admin)
    assert guard.status_code == 409 and guard.json()["code"] in {"OWNER_ADMIN_PROTECTED", "LAST_ADMIN"}
    # non-admin staff cannot manage the directory
    assert (await api_client.get("/api/executives", headers=up)).status_code == 403


async def test_discovery_sessions_unseen_first_stable_pages_and_isolation(api_client, isolated_db, seeded_users, login_helper):
    db = isolated_db["db"]
    now = datetime.now(timezone.utc)
    await db.products.insert_many([{"id": f"d{i:02d}", "title": f"Item {i}", "metal_type": "silver" if i % 2 else "gold", "category": "rings",
                                    "visibility": "visible", "is_deleted": False, "created_at": (now - timedelta(minutes=i)).isoformat()} for i in range(45)] +
                                  [{"id": "hidden1", "title": "Hidden", "metal_type": "silver", "visibility": "hidden", "is_deleted": False, "created_at": now.isoformat()}])
    c1, _ = await auth_headers(login_helper, "9000000004")
    c2, _ = await auth_headers(login_helper, "9000000005")
    first = await api_client.post("/api/discovery/sessions", json={"limit": 20}, headers=c1)
    assert first.status_code == 200, first.text
    s = first.json()
    assert s["total"] == 45 and s["unseen"] == 45 and s["pages"] == 3 and len(s["products"]) == 20 and "hidden1" not in [p["id"] for p in s["products"]]
    # stable pagination within the session: pages 2 and 3 never repeat an id
    ids = [p["id"] for p in s["products"]]
    for page in (2, 3):
        r = await api_client.get(f"/api/discovery/sessions/{s['session_id']}?page={page}&limit=20", headers=c1)
        ids += [p["id"] for p in r.json()["products"]]
    assert len(ids) == 45 and len(set(ids)) == 45
    # another user cannot read this session
    assert (await api_client.get(f"/api/discovery/sessions/{s['session_id']}", headers=c2)).status_code == 404
    # only real impressions count: user 1 saw 10 items
    seen = ids[:10]
    r = await api_client.post("/api/discovery/impressions", json={"product_ids": seen, "session_id": s["session_id"]}, headers=c1)
    assert r.status_code == 200 and r.json()["seen_total"] == 10
    second = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=c1)).json()
    assert second["unseen"] == 35 and second["seen"] == 10
    order = [p["id"] for p in second["products"]]
    assert set(order[:35]).isdisjoint(seen) and order[35:] and set(order[35:]) == set(seen)
    assert all(p["discovery"]["seen_before"] is False for p in second["products"][:35]) and all(p["discovery"]["seen_before"] for p in second["products"][35:])
    # fresh shuffle on each refresh (45 items: identical order is astronomically unlikely)
    third = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=c1)).json()
    assert [p["id"] for p in third["products"]][:35] != order[:35]
    # user 2's history is separate; filters preserved
    other = (await api_client.post("/api/discovery/sessions", json={"metal_type": "silver"}, headers=c2)).json()
    assert other["unseen"] == other["total"] == 22 and all(p["metal_type"] == "silver" for p in other["products"])
    # exhaustion: everything seen -> fallback order, no infinite loading
    all_ids = [p["id"] for p in third["products"]]
    for start in range(0, 45, 50):
        await api_client.post("/api/discovery/impressions", json={"product_ids": all_ids[start:start+50]}, headers=c1)
    done = (await api_client.post("/api/discovery/sessions", json={"limit": 20}, headers=c1)).json()
    assert done["exhausted"] is True and done["unseen"] == 0 and done["pages"] == 3
    # new catalogue additions become discoverable, deleted ones disappear from pages
    await db.products.insert_one({"id": "brandnew", "title": "New", "metal_type": "gold", "visibility": "visible", "is_deleted": False, "created_at": c.stamp()})
    await db.products.update_one({"id": all_ids[0]}, {"$set": {"is_deleted": True}})
    latest = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=c1)).json()
    assert latest["unseen"] == 1 and latest["products"][0]["id"] == "brandnew" and all_ids[0] not in [p["id"] for p in latest["products"]]
    # empty catalogue for a filter: no infinite loading
    empty = (await api_client.post("/api/discovery/sessions", json={"category": "nothing-here"}, headers=c1)).json()
    assert empty["total"] == 0 and empty["pages"] == 1 and empty["exhausted"] is True
    # account deletion removes the viewing history
    from shared.people import erase
    await erase(await db.users.find_one({"id": "u_cust1"}, {"_id": 0}), "app")
    assert await db.product_impressions.count_documents({"user_id": "u_cust1"}) == 0
    assert await db.discovery_sessions.count_documents({"user_id": "u_cust1"}) == 0
