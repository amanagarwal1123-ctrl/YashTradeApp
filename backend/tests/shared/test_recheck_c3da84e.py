"""Regression tests for the independent RECHECK of commit c3da84e (21 Sep 2026): G04b (provider sub-request progress)
and the notification-composer access question raised by the browser plan (both administrator paths, no bypass).
G01c (response bodies that complete after the account changed) is frontend and covered by `lateRefresh.test.ts` and
`authSessionWeb.test.tsx`. Assertions describe the CORRECT behaviour on the real isolated database with injected faults."""
import secrets

import pytest

from shared import core as c, notifications, review_seed

pytestmark = pytest.mark.asyncio


async def auth(login_helper, phone):
    body = await login_helper(phone)
    return {"Authorization": f"Bearer {body['token']}"}


# ---- G04b: a later provider sub-request failure never resends an accepted sub-request -------------------------------

async def test_g04b_later_sub_request_failure_keeps_the_accepted_sub_request_and_retries_only_the_remainder(api_client, isolated_db, seeded_users, login_helper, monkeypatch):
    """Recheck: 25 recipients x 5 devices = one 125-message outbox job; provider call 1 accepted 100 messages, call 2
    failed; the job went back to pending WITHOUT the 100 tickets and the retry sent 100 + 25 again. Now every accepted
    sub-request is stored before the next one is attempted, the retry sends the 25 unsent messages only, every device
    is handed to the provider exactly once and the campaign counts each acceptance once."""
    db = isolated_db["db"]
    admin = await auth(login_helper, "9000000000")
    template = {k: v for k, v in seeded_users["u_cust2"].items() if k != "_id"}
    users = [{**template, "id": f"u_g04b_{i:02d}", "phone": f"91000004{i:02d}", "phone_normalized": f"91000004{i:02d}", "name": f"Recipient {i:02d}"} for i in range(25)]
    await db.users.insert_many([dict(u) for u in users])
    devices = [{"id": secrets.token_hex(12), "token": f"ExponentPushToken[g04b{i:02d}d{d}xxxxxxxxxxxx]", "user_id": u["id"], "role": "customer",
                "platform": "android", "enabled": True, "created_at": c.stamp(), "updated_at": c.stamp()} for i, u in enumerate(users) for d in range(5)]
    await db.push_devices.insert_many([dict(d) for d in devices])
    all_tokens = sorted(d["token"] for d in devices)
    calls = []

    async def provider(messages):
        calls.append([m["to"] for m in messages])
        if len(calls) == 2:
            raise RuntimeError("provider unavailable")            # the second sub-request fails before acceptance
        return [{"status": "ok", "id": f"t-{len(calls)}-{i}"} for i, _ in enumerate(messages)]
    monkeypatch.setattr(notifications, "transport", provider)
    cid = (await api_client.post("/api/admin/notifications/campaigns", json={"title": "Festive", "body": "Offer", "destination": "/(tabs)",
                                 "audience": {"target": "selected", "customer_ids": [u["id"] for u in users]}}, headers=admin)).json()["id"]
    ok = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 25}, headers=admin)
    assert ok.status_code == 200, ok.text
    assert ok.json()["batches"] == 1 and ok.json()["devices"] == 125 and ok.json()["status"] == "queued"
    # attempt 1: sub-request 1 (100) accepted, sub-request 2 (25) fails
    await notifications.tick()
    job = await db.notification_outbox.find_one({"campaign_id": cid}, {"_id": 0})
    assert [len(call) for call in calls] == [100, 25]
    assert job["status"] == "pending" and job["attempts"] == 1 and job["errors"][0]["error"] == "RuntimeError"
    assert len(job["tickets"]) == 100 and sorted(t["token"] for t in job["tickets"]) == sorted(calls[0])   # the accepted sub-request is kept
    assert all(t["status"] == "ok" and t["ticket_id"].startswith("t-1-") for t in job["tickets"])
    campaign = await db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    assert campaign["status"] == "queued" and campaign["stats"]["accepted"] == 0                          # counted once, when the job completes
    # attempt 2 (backoff elapsed): only the 25 unsent messages are re-validated and sent
    await db.notification_outbox.update_one({"id": job["id"]}, {"$set": {"next_attempt_at": c.stamp()}})
    await notifications.tick()
    job = await db.notification_outbox.find_one({"campaign_id": cid}, {"_id": 0})
    assert [len(call) for call in calls] == [100, 25, 25]
    assert sorted(calls[2]) == sorted(set(all_tokens) - set(calls[0])) == sorted(calls[1])                # the remainder, nothing accepted before
    assert sorted(calls[0] + calls[2]) == all_tokens                                                       # each device handed over exactly once
    assert job["status"] == "sent" and job["attempts"] == 2 and job["accepted"] == 125 and job["errors_count"] == 0 and job["skipped_count"] == 0
    assert len(job["tickets"]) == 125 and sorted(t["token"] for t in job["tickets"]) == all_tokens
    campaign = await db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    assert campaign["status"] == "sent" and campaign["stats"]["accepted"] == 125 and campaign["stats"]["errors"] == 0 and campaign["stats"]["batches"] == 1
    assert await db.notifications.count_documents({"campaign_id": cid}) == 25
    # further passes change nothing
    await notifications.tick()
    assert len(calls) == 3 and (await db.notification_campaigns.find_one({"id": cid}))["stats"]["accepted"] == 125


async def test_g04b_retry_revalidates_only_the_unsent_remainder_and_keeps_earlier_tickets(api_client, isolated_db, seeded_users, login_helper, monkeypatch):
    """Eligibility changes between the failed attempt and the retry apply to the remainder only: a device unlinked
    since the first sub-request was accepted is neither re-sent nor counted as skipped; a device unlinked in the
    remainder is skipped; a DeviceNotRegistered ticket of the first sub-request stays recorded and invalidated."""
    db = isolated_db["db"]
    admin = await auth(login_helper, "9000000000")
    template = {k: v for k, v in seeded_users["u_cust2"].items() if k != "_id"}
    users = [{**template, "id": f"u_g04c_{i:02d}", "phone": f"91000005{i:02d}", "phone_normalized": f"91000005{i:02d}", "name": f"Recipient {i:02d}"} for i in range(2)]
    await db.users.insert_many([dict(u) for u in users])
    devices = [{"id": secrets.token_hex(12), "token": f"ExponentPushToken[g04c{i}d{d}xxxxxxxxxxxxxx]", "user_id": u["id"], "role": "customer",
                "platform": "android", "enabled": True, "created_at": c.stamp(), "updated_at": c.stamp()} for i, u in enumerate(users) for d in range(2)]
    await db.push_devices.insert_many([dict(d) for d in devices])
    monkeypatch.setattr(notifications, "BATCH", 2)                 # four messages -> two provider sub-requests
    calls = []

    async def provider(messages):
        calls.append([m["to"] for m in messages])
        if len(calls) == 2:
            raise RuntimeError("provider unavailable")
        return [{"status": "ok" if i == 0 else "error", "id": f"t-{len(calls)}-{i}", "details": {} if i == 0 else {"error": "DeviceNotRegistered"}} for i, _ in enumerate(messages)]
    monkeypatch.setattr(notifications, "transport", provider)
    cid = (await api_client.post("/api/admin/notifications/campaigns", json={"title": "T", "body": "B", "destination": "/(tabs)",
                                 "audience": {"target": "selected", "customer_ids": [u["id"] for u in users]}}, headers=admin)).json()["id"]
    assert (await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 2}, headers=admin)).status_code == 200
    await notifications.tick()
    job = await db.notification_outbox.find_one({"campaign_id": cid}, {"_id": 0})
    first, second = calls[0], calls[1]
    assert job["status"] == "pending" and [t["token"] for t in job["tickets"]] == first
    assert (await db.push_devices.find_one({"token": first[1]}))["enabled"] is False                      # invalidated by its ticket, durably
    # the world changes before the retry: one accepted device and one unsent device are unlinked
    await db.push_devices.update_one({"token": first[0]}, {"$set": {"enabled": False}})
    await db.push_devices.update_one({"token": second[0]}, {"$set": {"enabled": False}})
    await db.notification_outbox.update_one({"id": job["id"]}, {"$set": {"next_attempt_at": c.stamp()}})
    await notifications.tick()
    job = await db.notification_outbox.find_one({"campaign_id": cid}, {"_id": 0})
    assert calls[2] == [second[1]]                                                                          # only the still-eligible remainder
    assert job["status"] == "sent" and [t["token"] for t in job["tickets"]] == first + [second[1]]
    assert job["accepted"] == 2 and job["errors_count"] == 1 and job["invalid_tokens"] == 1
    assert job["skipped"] == [{"token_tail": second[0][-6:], "user_id": users[1]["id"], "reason": "device_unlinked"}] and job["skipped_count"] == 1
    campaign = await db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    stats = campaign["stats"]
    assert campaign["status"] == "sent" and (stats["accepted"], stats["errors"], stats["invalid_tokens"], stats["skipped"], stats["batches"]) == (2, 1, 1, 1, 1)


# ---- notification composer access: ordinary administrator AND review administrator, no bypass ----------------------

async def review_login(api_client, reviewer_id, key):
    res = await api_client.post("/api/auth/review/login", json={"reviewer_id": reviewer_id, "access_key": key})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


async def test_notification_composer_apis_accept_both_administrator_paths_and_keep_scopes_apart(api_client, review_env, seeded_users, login_helper):
    """Browser plan: the composer page (`/admin-notifications`) only checks the shared admin role; its APIs use the
    shared `c.admin` dependency whose scope/account/session checks live in core. An ordinary administrator (OTP
    session, production scope) and the review administrator (review-scope session) both reach every composer API;
    non-administrators of either scope are denied identically; and each scope sees only its own campaigns."""
    with c.scoped(c.REVIEW):
        await review_seed.seed_dataset()
        keys = await review_seed.provision_accounts()
    ordinary_admin, telecaller, customer = await auth(login_helper, "9000000000"), await auth(login_helper, "9000000001"), await auth(login_helper, "9000000004")
    review_admin = await review_login(api_client, "store-review-admin", keys["store-review-admin"])
    review_customer = await review_login(api_client, "store-review-customer", keys["store-review-customer"])
    review_telecaller = await review_login(api_client, "store-review-telecaller", keys["store-review-telecaller"])
    draft = {"title": "Composer check", "body": "Synthetic draft", "destination": "/notifications", "audience": {"target": "customers"}}
    created = {}
    for label, headers in (("ordinary", ordinary_admin), ("review", review_admin)):
        filters = await api_client.get("/api/admin/notifications/filters", headers=headers)
        assert filters.status_code == 200 and set(filters.json()) >= {"cities", "customer_types", "telecallers", "targets"}, (label, filters.text)
        audience = await api_client.post("/api/admin/notifications/audience", json={"target": "customers"}, headers=headers)
        assert audience.status_code == 200 and audience.json()["users"] >= 1, (label, audience.text)
        campaign = await api_client.post("/api/admin/notifications/campaigns", json=draft, headers=headers)
        assert campaign.status_code == 200 and campaign.json()["status"] == "draft", (label, campaign.text)
        created[label] = campaign.json()["id"]
        detail = await api_client.get(f"/api/admin/notifications/campaigns/{created[label]}", headers=headers)
        assert detail.status_code == 200 and detail.json()["outbox"] == []
        outbox = await api_client.get("/api/admin/notifications/outbox", headers=headers)
        assert outbox.status_code == 200 and outbox.json()["provider"]["provider"] == "expo_push_service"
    # the review administrator's list holds the review draft only; the ordinary administrator's list the production one only
    review_list = (await api_client.get("/api/admin/notifications/campaigns", headers=review_admin)).json()
    ordinary_list = (await api_client.get("/api/admin/notifications/campaigns", headers=ordinary_admin)).json()
    assert [cp["id"] for cp in review_list["campaigns"]] == [created["review"]] and [cp["id"] for cp in ordinary_list["campaigns"]] == [created["ordinary"]]
    assert (await api_client.get(f"/api/admin/notifications/campaigns/{created['ordinary']}", headers=review_admin)).status_code == 404
    assert (await api_client.get(f"/api/admin/notifications/campaigns/{created['review']}", headers=ordinary_admin)).status_code == 404
    assert await review_env["primary"].notification_campaigns.count_documents({}) == 1
    assert await review_env["db"].notification_campaigns.count_documents({}) == 1
    # non-administrators of both scopes are denied with the same permission error; a review session in the production
    # scope never counts as an administrator either (scope is checked before the role)
    for headers in (telecaller, customer, review_customer, review_telecaller):
        for method, path, body in (("get", "/api/admin/notifications/filters", None), ("get", "/api/admin/notifications/campaigns", None),
                                   ("post", "/api/admin/notifications/campaigns", draft), ("post", "/api/admin/notifications/audience", {"target": "customers"})):
            res = await (api_client.get(path, headers=headers) if method == "get" else api_client.post(path, json=body, headers=headers))
            assert res.status_code == 403 and res.json()["code"] == "PERMISSION_DENIED", (path, res.text)
    assert (await api_client.get("/api/admin/notifications/filters")).status_code == 401
    # the review administrator's own profile is what the composer page checks (`role === 'admin'`), flagged as review
    me = (await api_client.get("/api/auth/me", headers=review_admin)).json()
    assert me["role"] == "admin" and me["review_environment"] is True
