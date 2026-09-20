"""Regression tests for the independent review of commit 2093300 (20 Sep 2026), findings F02-F07. Each test first
states the defective scenario the review reproduced and asserts the CORRECTED behaviour on the real isolated database.
F01 (late refresh) is covered by the Jest suite `lateRefresh.test.ts`; F08/F09 are frontend (RequestDetail / navigation)."""
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from shared import core as c, discovery, notifications, queries, queue_reset

pytestmark = pytest.mark.asyncio
IST = ZoneInfo("Asia/Kolkata")


async def auth(login_helper, phone):
    body = await login_helper(phone)
    return {"Authorization": f"Bearer {body['token']}"}


@pytest.fixture
def recording_transport(monkeypatch):
    sent = []

    async def fake_send(messages):
        sent.append(list(messages))
        return [{"status": "ok", "id": f"t-{len(sent)}-{i}"} for i, _ in enumerate(messages)]
    monkeypatch.setattr(notifications, "transport", fake_send)
    return sent


# ---- F02 --------------------------------------------------------------------------------------------------------------

async def test_f02_queued_messages_are_revalidated_before_dispatch(api_client, isolated_db, seeded_users, login_helper, recording_transport):
    """Review: a message queued for A was still sent after the token was unlinked and re-registered by B. Now every
    message is re-checked immediately before the send: unlinked device, device now owned by another account, disabled
    account, marketing opt-out and role change after queueing are all excluded and accounted for."""
    db = isolated_db["db"]
    admin = await auth(login_helper, "9999813334")
    tokens = {"u_cust1": "ExponentPushToken[f02aaaaaaaaaaaaa]", "u_cust2": "ExponentPushToken[f02bbbbbbbbbbbbb]", "u_tele1": "ExponentPushToken[f02ccccccccccccc]",
              "u_tele2": "ExponentPushToken[f02ddddddddddddd]"}
    sessions = {}
    for uid, tok in tokens.items():
        sessions[uid] = await auth(login_helper, seeded_users[uid]["phone"])
        assert (await api_client.post("/api/notifications/devices", json={"token": tok, "platform": "android"}, headers=sessions[uid])).status_code == 200
    # marketing batch for the two customers + operational query alert for the two telecallers, both queued NOW
    await notifications.fan_out("f02-marketing", "marketing", ["u_cust1", "u_cust2"], "Offer", "body", "/(tabs)")
    await notifications.fan_out("f02-query", "operational", ["u_tele1", "u_tele2"], "New query", "body", "/staff-requests?request=x", request_id="req-x")
    assert await db.notification_outbox.count_documents({"status": "pending"}) == 2
    # ... and the world changes before the worker runs:
    # cust1 signs out (device unlinked) and the same phone is used by a new account u_other (device re-registered)
    other = await auth(login_helper, "9000000006")
    await api_client.post("/api/notifications/devices/unlink", json={"token": tokens["u_cust1"]}, headers=sessions["u_cust1"])
    await api_client.post("/api/notifications/devices", json={"token": tokens["u_cust1"], "platform": "android"}, headers=other)
    # cust2 opts out of marketing
    await api_client.put("/api/notifications/preferences", json={"marketing": False}, headers=sessions["u_cust2"])
    # tele1 is disabled, tele2 is converted to a customer role
    assert (await api_client.patch("/api/integrations/staff/u_tele1", json={"status": "inactive"}, headers=admin)).status_code == 200
    await db.users.update_one({"id": "u_tele2"}, {"$set": {"role": "customer"}})
    await db.push_devices.update_one({"token": tokens["u_tele2"]}, {"$set": {"enabled": True}})   # device still linked: only the role changed
    await notifications.tick()
    assert recording_transport == []                                        # nothing eligible was left -> nothing reached the provider
    jobs = {j["key"]: j for j in await db.notification_outbox.find({}, {"_id": 0}).to_list(None)}
    assert jobs["f02-marketing:0"]["status"] == "sent" and jobs["f02-marketing:0"]["accepted"] == 0
    assert sorted(s["reason"] for s in jobs["f02-marketing:0"]["skipped"]) == ["device_reassigned", "marketing_opt_out"]
    assert sorted(s["reason"] for s in jobs["f02-query:0"]["skipped"]) == ["account_unusable", "role_changed"]
    # the opted-out customer's unread marketing row is withdrawn from the inbox as well; the new account got nothing
    assert await db.notifications.count_documents({"user_id": "u_cust2", "kind": "marketing"}) == 0
    assert await db.notifications.count_documents({"user_id": other and (await db.users.find_one({"phone_normalized": "9000000006"}))["id"]}) == 0
    # a still-eligible recipient in the same batch IS sent: re-queue for cust1's new device owner and an active telecaller
    await db.users.update_one({"id": "u_tele2"}, {"$set": {"role": "telecaller"}})
    await notifications.fan_out("f02-query2", "operational", ["u_tele2"], "New query", "body", "/staff-requests?request=y", request_id="req-y")
    await notifications.tick()
    assert [m["to"] for m in recording_transport[-1]] == [tokens["u_tele2"]]


# ---- F03 --------------------------------------------------------------------------------------------------------------

async def test_f03_completion_ledger_survives_a_crash_between_the_two_writes(api_client, isolated_db, seeded_users, login_helper, monkeypatch):
    """Review: the request was marked resolved but the ledger insert failed; retries (same or new key) returned early
    and the staff report lost the record forever. Now the resolved request document is the source of truth and any
    retry, the report itself and the detail view re-derive the missing ledger row exactly once."""
    db = isolated_db["db"]
    admin, t1, cust = await auth(login_helper, "9999813334"), await auth(login_helper, "9000000001"), await auth(login_helper, "9000000004")
    rid = (await api_client.post("/api/requests", json={"request_type": "callback"}, headers=cust)).json()["id"]
    assert (await api_client.post(f"/api/requests/{rid}/claim", headers=t1)).status_code == 200

    async def boom(doc, user, ts):
        raise RuntimeError("ledger store unavailable")
    monkeypatch.setattr(queries, "record_completion", boom)
    with pytest.raises(RuntimeError):
        await api_client.post(f"/api/requests/{rid}/complete", json={"outcome": "converted", "idempotency_key": "done-1"}, headers=t1)
    monkeypatch.undo()
    doc = await db.requests.find_one({"id": rid}, {"_id": 0})
    assert doc["status"] == "resolved" and doc["completed_by_id"] == "u_tele1" and doc["completed_by_role"] == "telecaller"
    assert await db.request_completions.count_documents({"request_id": rid}) == 0          # the partial write the review reproduced
    # same-key retry repairs the ledger (and adds nothing else)
    again = await api_client.post(f"/api/requests/{rid}/complete", json={"outcome": "converted", "idempotency_key": "done-1"}, headers=t1)
    assert again.status_code == 200
    rows = await db.request_completions.find({"request_id": rid}, {"_id": 0}).to_list(None)
    assert len(rows) == 1 and rows[0]["actor_id"] == "u_tele1" and rows[0]["completed_at"] == doc["resolved_at"] and rows[0]["outcome"] == "converted"
    # a new-key retry and the report never add a second row; the report counts it exactly once
    assert (await api_client.post(f"/api/requests/{rid}/complete", json={"idempotency_key": "done-2"}, headers=t1)).json()["already_completed"] is True
    today = c.now().astimezone(queries.IST).date().isoformat()
    report = (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)).json()
    assert report["total_completed"] == 1 and report["total_records"] == 1
    # crash variant with NO retry from the telecaller: the report / startup reconcile repairs it
    rid2 = (await api_client.post("/api/requests", json={"request_type": "ask_price"}, headers=cust)).json()["id"]
    await api_client.post(f"/api/requests/{rid2}/claim", headers=t1)
    monkeypatch.setattr(queries, "record_completion", boom)
    with pytest.raises(RuntimeError):
        await api_client.post(f"/api/requests/{rid2}/complete", json={}, headers=t1)
    monkeypatch.undo()
    assert await queries.reconcile_completion_ledger() == 1
    assert await queries.reconcile_completion_ledger() == 0
    assert (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)).json()["total_completed"] == 2
    # reopen supersedes only the completion sequence it read: a re-completion afterwards is a fresh, counted record
    assert (await api_client.patch(f"/api/requests/{rid}", json={"action": "reopen", "status": "pending", "reason": "customer called back"}, headers=admin)).status_code == 200
    await api_client.post(f"/api/requests/{rid}/claim", headers=t1)
    assert (await api_client.post(f"/api/requests/{rid}/complete", json={}, headers=t1)).status_code == 200
    rows = await db.request_completions.find({"request_id": rid}, {"_id": 0}).sort("sequence", 1).to_list(None)
    assert [r["sequence"] for r in rows] == [1, 2] and rows[0]["superseded_at"] and rows[1]["superseded_at"] is None
    assert (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)).json()["total_completed"] == 2


# ---- F04 --------------------------------------------------------------------------------------------------------------

def ist(y, m, d, hh, mm, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=IST).astimezone(timezone.utc)


async def test_f04_post_boundary_edit_cannot_keep_yesterdays_claim(api_client, isolated_db, seeded_users, login_helper, monkeypatch):
    """Review: a note typed at 03:00:01 bumped updated_at and made yesterday's assignment ineligible for the release.
    Now eligibility follows the assignment's age (claimed_at), the worker releases it anyway, AND the work mutation
    itself releases an expired assignment before the edit - the old claimant cannot edit or complete without taking
    the query again, while a genuinely new post-boundary claim and a completion are respected."""
    db = isolated_db["db"]
    clock = {"now": ist(2026, 9, 19, 22, 0)}
    monkeypatch.setattr(c, "now", lambda: clock["now"])
    t1, t2, cust, admin = await auth(login_helper, "9000000001"), await auth(login_helper, "9000000002"), await auth(login_helper, "9000000004"), await auth(login_helper, "9999813334")
    await db.queue_cycles.insert_one({"_id": "2026-09-19", "status": "completed"})   # yesterday's cycle already ran
    rid = (await api_client.post("/api/requests", json={"request_type": "callback"}, headers=cust)).json()["id"]
    assert (await api_client.post(f"/api/requests/{rid}/claim", headers=t1)).status_code == 200
    assert (await api_client.patch(f"/api/requests/{rid}", json={"head": "follow_up", "notes": "call tomorrow"}, headers=t1)).status_code == 200
    # 03:00:01 IST next day - the worker has NOT run yet (30 s poll gap); yesterday's claimant tries to keep working
    clock["now"] = ist(2026, 9, 20, 3, 0, 1)
    edit = await api_client.patch(f"/api/requests/{rid}", json={"notes": "still mine?"}, headers=t1)
    assert edit.status_code == 403 and edit.json()["code"] == "CLAIM_REQUIRED"
    doc = await db.requests.find_one({"id": rid}, {"_id": 0})
    assert doc["assignee_id"] == "" and doc["head"] == "new" and doc["status"] == "pending" and doc["reset_cycle"] == "2026-09-20"
    assert doc["previous_assignment"]["assignee_id"] == "u_tele1" and doc["previous_assignment"]["head"] == "follow_up"
    assert doc["events"][-1]["type"] == "daily_release" and doc["reset_count"] == 1
    # the released query is claimable immediately by anyone (here the other telecaller); that claim is post-boundary
    assert (await api_client.post(f"/api/requests/{rid}/claim", headers=t2)).status_code == 200
    # the worker pass for the same cycle releases nothing more and never touches the new claim
    results = await queue_reset.tick()
    assert results and results[0]["completed"] and results[0]["released"] == 0
    doc = await db.requests.find_one({"id": rid}, {"_id": 0})
    assert doc["assignee_id"] == "u_tele2" and doc["reset_count"] == 1
    # predicate level (the review's exact reproduction): updated_at after the boundary alone never protects a stale claim
    cycle_id, boundary = queue_reset.boundary_for(clock["now"])
    stale = {"id": "stale", "status": "in_progress", "assignee_id": "u_tele1", "assigned_to": "u_tele1", "head": "contacted", "version": 1,
             "created_at": ist(2026, 9, 19, 12, 0).isoformat(), "claimed_at": ist(2026, 9, 19, 12, 5).isoformat(), "updated_at": ist(2026, 9, 20, 3, 0, 1).isoformat(), "events": []}
    await db.requests.insert_one(dict(stale))
    assert await db.requests.count_documents({"id": "stale", **queue_reset.candidate_query(cycle_id, boundary.isoformat())}) == 1
    # a completion typed by the old claimant after the boundary (before the worker) is refused too - nothing is lost
    fresh_claim = {"id": "fresh", "status": "in_progress", "assignee_id": "u_tele2", "assigned_to": "u_tele2", "head": "new", "version": 1,
                   "created_at": ist(2026, 9, 19, 12, 0).isoformat(), "claimed_at": ist(2026, 9, 20, 3, 0, 0).isoformat(), "updated_at": ist(2026, 9, 20, 3, 0, 0).isoformat(), "events": []}
    await db.requests.insert_one(dict(fresh_claim))
    assert await db.requests.count_documents({"id": "fresh", **queue_reset.candidate_query(cycle_id, boundary.isoformat())}) == 0
    await queue_reset.run_cycle(cycle_id, boundary)   # idempotent second run of the same cycle
    assert (await db.requests.find_one({"id": "stale"}))["assignee_id"] == "" and (await db.requests.find_one({"id": "fresh"}))["assignee_id"] == "u_tele2"
    # detail view after the boundary reflects the release (never shows yesterday's claimant as the owner)
    await db.requests.insert_one({**stale, "id": "stale2", "reset_cycle": None})
    await db.requests.update_one({"id": "stale2"}, {"$unset": {"reset_cycle": ""}})
    detail = (await api_client.get("/api/requests/stale2", headers=admin)).json()
    assert detail["assignee_id"] == "" and detail["permissions"]["can_claim"] is True


# ---- F05 --------------------------------------------------------------------------------------------------------------

async def test_f05_old_unseen_products_beyond_the_session_bound_are_still_discoverable(api_client, isolated_db, seeded_users, login_helper, monkeypatch):
    """Review: with > MAX_SESSION_IDS eligible products, an old product outside the newest window could never appear.
    Now unseen candidates come from the complete catalogue; the bound applies to the session only."""
    db = isolated_db["db"]
    monkeypatch.setattr(discovery, "MAX_SESSION_IDS", 40)   # same algorithm, smaller bound keeps the test fast
    now = datetime.now(timezone.utc)
    await db.products.insert_many([{"id": f"f05-{i:03d}", "title": f"P{i}", "metal_type": "silver", "visibility": "visible", "is_deleted": False,
                                    "created_at": (now - timedelta(minutes=i)).isoformat()} for i in range(41)])   # f05-040 is the OLDEST
    cust = await auth(login_helper, "9000000004")
    newest = [f"f05-{i:03d}" for i in range(40)]
    for start in range(0, 40, 50):
        await api_client.post("/api/discovery/impressions", json={"product_ids": newest[start:start + 50]}, headers=cust)
    s = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=cust)).json()
    assert s["unseen"] == 1 and s["exhausted"] is False and s["products"][0]["id"] == "f05-040" and s["truncated"] is False
    assert s["total"] == 41 and len({p["id"] for p in s["products"]}) == 41       # unseen first, then the least-recently-seen fallback
    # a catalogue larger than the bound: the session is bounded (truncated=true) but every unseen product is reachable
    # over successive refreshes once the earlier ones were seen
    await db.products.insert_many([{"id": f"f05-x{i:03d}", "title": f"X{i}", "metal_type": "gold", "visibility": "visible", "is_deleted": False,
                                    "created_at": (now - timedelta(days=1, minutes=i)).isoformat()} for i in range(45)])
    s2 = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=cust)).json()
    assert s2["truncated"] is True and s2["unseen"] == 40 and s2["seen"] == 0
    seen_now = [p["id"] for p in s2["products"]]
    assert set(seen_now) <= {"f05-040", *[f"f05-x{i:03d}" for i in range(45)]}
    await api_client.post("/api/discovery/impressions", json={"product_ids": seen_now[:40]}, headers=cust)
    s3 = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=cust)).json()
    assert s3["unseen"] == 6 and set(p["id"] for p in s3["products"][:6]).isdisjoint(seen_now) and s3["truncated"] is False


# ---- F06 --------------------------------------------------------------------------------------------------------------

async def test_f06_query_alert_is_never_lost_when_the_outbox_is_unavailable_at_creation(api_client, isolated_db, seeded_users, login_helper, recording_transport, monkeypatch):
    """Review: an enqueue failure at creation was logged and forgotten; the outbox worker had nothing to retry. Now the
    request carries a durable `notify_state=pending` marker that the worker (and a same-key creation retry) turns into
    the one operational event - for both creation paths (POST /requests and the cart submission)."""
    db = isolated_db["db"]
    cust, t1 = await auth(login_helper, "9000000004"), await auth(login_helper, "9000000001")
    await api_client.post("/api/notifications/devices", json={"token": "ExponentPushToken[f06ttttttttttttt]", "platform": "android"}, headers=t1)
    await db.products.insert_one({"id": "pf06", "title": "Chain", "metal_type": "silver", "visibility": "visible", "is_deleted": False, "created_at": c.stamp()})

    async def outbox_down(*a, **k):
        raise RuntimeError("outbox unavailable")
    monkeypatch.setattr(notifications, "fan_out", outbox_down)
    r = await api_client.post("/api/requests", json={"request_type": "callback", "notes": "hi"}, headers={**cust, "Idempotency-Key": "f06-1"})
    assert r.status_code == 200                                                # the customer's request never fails
    rid = r.json()["id"]
    assert (await api_client.post("/api/cart/add", json={"product_id": "pf06", "quantity": 1}, headers=cust)).status_code == 200
    cart = await api_client.post("/api/cart/submit", json={"notes": "cart"}, headers=cust)
    assert cart.status_code == 200
    rid_cart = cart.json()["request_id"]
    for x in (rid, rid_cart):
        doc = await db.requests.find_one({"id": x}, {"_id": 0})
        assert doc["notify_state"] == "pending" and doc["notify_attempts"] == 1 and doc["notify_errors"][0]["error"] == "RuntimeError"
    assert await db.notification_outbox.count_documents({}) == 0 and await db.notifications.count_documents({}) == 0
    monkeypatch.undo()
    # (a) the same-key creation retry queues the alert
    again = await api_client.post("/api/requests", json={"request_type": "callback", "notes": "hi"}, headers={**cust, "Idempotency-Key": "f06-1"})
    assert again.status_code == 200 and again.json()["id"] == rid
    assert (await db.requests.find_one({"id": rid}))["notify_state"] == "queued"
    assert await db.notification_outbox.count_documents({"request_id": rid}) == 1
    # (b) the worker reconciles the cart request without any client action (after the settle delay), exactly once
    assert await queries.reconcile_pending_notifications(min_age_seconds=0) == 1
    assert await queries.reconcile_pending_notifications(min_age_seconds=0) == 0
    assert (await db.requests.find_one({"id": rid_cart}))["notify_state"] == "queued"
    await notifications.tick()
    delivered = sorted(m["data"]["request_id"] for batch in recording_transport for m in batch)
    assert delivered == sorted([rid, rid_cart])                              # one alert per query, none duplicated
    assert await db.notifications.count_documents({"user_id": "u_tele1", "kind": "operational"}) == 2
    # the outbox worker's own pass performs the same reconcile (no separate scheduler needed)
    await db.requests.update_one({"id": rid_cart}, {"$set": {"notify_state": "pending", "created_at": (c.now() - timedelta(minutes=5)).isoformat()}})
    await notifications.tick()
    assert (await db.requests.find_one({"id": rid_cart}))["notify_state"] == "queued"
    assert await db.notification_outbox.count_documents({"request_id": rid_cart}) == 1   # idempotent on the request id


async def test_f06_campaign_never_sticks_in_sending_and_a_resend_completes_without_duplicates(api_client, isolated_db, seeded_users, login_helper, recording_transport, monkeypatch):
    db = isolated_db["db"]
    admin = await auth(login_helper, "9999813334")
    for uid in ("u_cust1", "u_cust2"):
        h = await auth(login_helper, seeded_users[uid]["phone"])
        await api_client.post("/api/notifications/devices", json={"token": f"ExponentPushToken[camp{uid}xxxxxxx]"[:30] + "]", "platform": "android"}, headers=h)
    cid = (await api_client.post("/api/admin/notifications/campaigns", json={"title": "T", "body": "B", "destination": "/(tabs)", "audience": {"target": "customers"}}, headers=admin)).json()["id"]
    real_enqueue = notifications.enqueue
    calls = {"n": 0}

    async def flaky_enqueue(*a, **k):
        calls["n"] += 1
        raise RuntimeError("outbox down")
    monkeypatch.setattr(notifications, "enqueue", flaky_enqueue)
    failed = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 2}, headers=admin)
    assert failed.status_code == 503 and failed.json()["code"] == "FAN_OUT_FAILED"
    campaign = await db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    assert campaign["status"] == "draft" and campaign["send_errors"][0]["error"] == "RuntimeError"   # not stuck in "sending"
    monkeypatch.setattr(notifications, "enqueue", real_enqueue)
    ok = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 2}, headers=admin)
    assert ok.status_code == 200 and ok.json()["batches"] == 1
    await notifications.tick()
    assert (await db.notification_campaigns.find_one({"id": cid}))["status"] == "sent"
    assert await db.notifications.count_documents({"campaign_id": cid}) == 2                    # one inbox row per recipient, no duplicates
    assert len(recording_transport) == 1 and len(recording_transport[0]) == 2


# ---- F07 --------------------------------------------------------------------------------------------------------------

async def test_f07_completed_query_then_customer_deletion_scrubs_the_ledger_but_keeps_attribution(api_client, isolated_db, seeded_users, login_helper, recording_transport):
    db = isolated_db["db"]
    admin, t1, cust = await auth(login_helper, "9999813334"), await auth(login_helper, "9000000001"), await auth(login_helper, "9000000004")
    rid = (await api_client.post("/api/requests", json={"request_type": "callback"}, headers=cust)).json()["id"]
    await api_client.post(f"/api/requests/{rid}/claim", headers=t1)
    assert (await api_client.post(f"/api/requests/{rid}/complete", json={"outcome": "converted"}, headers=t1)).status_code == 200
    row = await db.request_completions.find_one({"request_id": rid}, {"_id": 0})
    assert row["customer_name"] == "Customer One" and row["shop_name"]                  # personal data present before deletion
    # an unsent marketing message for the customer is queued as well
    await api_client.post("/api/notifications/devices", json={"token": "ExponentPushToken[f07cccccccccccccc]"[:30] + "]", "platform": "android"}, headers=cust)
    await notifications.fan_out("f07-mkt", "marketing", ["u_cust1", "u_cust2"], "Offer", "B", "/(tabs)")
    r = await api_client.post("/api/customers/u_cust1/delete", json={"reason": "customer asked", "confirm_user_id": "u_cust1", "confirm_phone_last4": "0004"}, headers=admin)
    assert r.status_code == 200, r.text
    row = await db.request_completions.find_one({"request_id": rid}, {"_id": 0})
    assert row["customer_name"] == "Deleted customer" and row["shop_name"] == "" and row["customer_anonymized"] is True
    assert row["actor_id"] == "u_tele1" and row["actor_name"] == "Tele One" and row["outcome"] == "converted"   # attribution kept
    job = await db.notification_outbox.find_one({"key": "f07-mkt:0"}, {"_id": 0})
    assert [m["_user_id"] for m in job["messages"]] == ["u_cust2"]                    # unsent message for the erased account dropped
    from shared.people import erasure_report
    report = await erasure_report("u_cust1")
    assert report["by_collection"]["request_completions_with_personal_data"] == 0
    assert report["by_collection"]["notification_outbox_unsent_messages"] == 0
    assert report["local_personal_records_remaining"] == 0 and "request_completions" in report["retained_by_app"]
    today = c.now().astimezone(queries.IST).date().isoformat()
    assert (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)).json()["total_completed"] == 1
