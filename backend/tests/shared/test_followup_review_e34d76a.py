"""Regression tests for the independent FOLLOW-UP review of commit e34d76a (21 Sep 2026), defect groups G02-G04
(G01 - session isolation at asynchronous boundaries - is frontend and covered by `lateRefresh.test.ts`).
Each test states the scenario the review reproduced and asserts the CORRECTED behaviour on the real isolated database
with injected faults - the assertions describe correct behaviour, never the defect."""
from datetime import timedelta

import pytest

from shared import core as c, discovery, notifications, queries

pytestmark = pytest.mark.asyncio


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


def report_window():
    today = c.now().astimezone(queries.IST).date()
    return f"start={(today - timedelta(days=1)).isoformat()}&end={(today + timedelta(days=1)).isoformat()}"


async def completed_request(api_client, cust, staff, **body):
    rid = (await api_client.post("/api/requests", json={"request_type": "callback"}, headers=cust)).json()["id"]
    assert (await api_client.post(f"/api/requests/{rid}/claim", headers=staff)).status_code == 200
    assert (await api_client.post(f"/api/requests/{rid}/complete", json=body, headers=staff)).status_code == 200
    return rid


async def failing_reopen(api_client, admin, rid, key=None):
    """Reopen whose request write succeeds but whose ledger supersession fails (the review's G02-A fault)."""
    async def boom(rid_, intent):
        raise RuntimeError("ledger store unavailable")
    body = {"action": "reopen", "status": "pending", "reason": "customer called back"}
    if key:
        body["idempotency_key"] = key
    with pytest.MonkeyPatch.context() as fault:
        fault.setattr(queries, "supersede_completion_rows", boom)
        with pytest.raises(RuntimeError):
            await api_client.patch(f"/api/requests/{rid}", json=body, headers=admin)


# ---- G02-A: reopen whose ledger write fails -------------------------------------------------------------------------

async def test_g02a_interrupted_reopen_supersession_is_recovered_by_retry_report_worker_and_detail(api_client, isolated_db, seeded_users, login_helper):
    """Review: the request became pending, the ledger row kept `superseded_at=None` (still counted), the same-key retry
    returned early and the reconciliation only looked at resolved requests - unrecoverable. Now the supersession is a
    durable intent stored WITH the request write and every recovery path settles it."""
    db = isolated_db["db"]
    admin, t1, cust = await auth(login_helper, "9000000000"), await auth(login_helper, "9000000001"), await auth(login_helper, "9000000004")
    # (1) same-key retry
    rid = await completed_request(api_client, cust, t1, outcome="converted")
    await failing_reopen(api_client, admin, rid, key="reopen-1")
    doc = await db.requests.find_one({"id": rid}, {"_id": 0})
    assert doc["status"] == "pending" and doc["ledger_pending"] == [{"action": "supersede", "sequence": 1, "at": doc["ledger_pending"][0]["at"], "actor_id": "u_admin", "reason": "customer called back"}]
    assert (await db.request_completions.find_one({"request_id": rid}))["superseded_at"] is None       # the partial state the review reproduced
    retry = await api_client.patch(f"/api/requests/{rid}", json={"action": "reopen", "status": "pending", "reason": "customer called back", "idempotency_key": "reopen-1"}, headers=admin)
    assert retry.status_code == 200 and retry.json()["status"] == "pending"
    row = await db.request_completions.find_one({"request_id": rid}, {"_id": 0})
    assert row["superseded_at"] == doc["ledger_pending"][0]["at"] and row["superseded_by"] == "u_admin" and row["reopen_reason"] == "customer called back"
    assert (await db.requests.find_one({"id": rid}, {"_id": 0}))["ledger_pending"] == []
    # (2) recovery WITHOUT any user retry: the worker/report reconciliation settles the indexed intent
    rid2 = await completed_request(api_client, cust, t1)
    await failing_reopen(api_client, admin, rid2)
    assert await queries.reconcile_completion_ledger() == 1
    assert await queries.reconcile_completion_ledger() == 0
    assert (await db.request_completions.find_one({"request_id": rid2}))["superseded_at"] is not None
    # (3) the detail view settles it too
    rid3 = await completed_request(api_client, cust, t1)
    await failing_reopen(api_client, admin, rid3)
    assert (await api_client.get(f"/api/requests/{rid3}", headers=admin)).status_code == 200
    assert (await db.request_completions.find_one({"request_id": rid3}))["superseded_at"] is not None
    # (4) the report itself never counts a reopened completion, even when nothing else ran in between
    rid4 = await completed_request(api_client, cust, t1)
    await failing_reopen(api_client, admin, rid4)
    report = (await api_client.get(f"/api/requests/reports/completions?{report_window()}", headers=admin)).json()
    assert report["total_completed"] == 0 and report["total_records"] == 0
    assert await db.requests.count_documents({"ledger_pending.at": {"$exists": True}}) == 0


async def test_g02a_re_completion_after_a_half_done_reopen_counts_once_and_is_never_superseded(api_client, isolated_db, seeded_users, login_helper):
    """Review requirement: recovery must preserve completion sequence boundaries and survive a later re-completion
    without superseding that newer event (concurrent reopen / re-completion)."""
    db = isolated_db["db"]
    admin, t1, cust = await auth(login_helper, "9000000000"), await auth(login_helper, "9000000001"), await auth(login_helper, "9000000004")
    rid = await completed_request(api_client, cust, t1, outcome="converted")
    await failing_reopen(api_client, admin, rid)
    # the telecaller simply continues working: takes the reopened query and completes it again
    assert (await api_client.post(f"/api/requests/{rid}/claim", headers=t1)).status_code == 200
    assert (await api_client.post(f"/api/requests/{rid}/complete", json={"outcome": "other"}, headers=t1)).status_code == 200
    rows = await db.request_completions.find({"request_id": rid}, {"_id": 0}).sort("sequence", 1).to_list(None)
    assert [r["sequence"] for r in rows] == [1, 2] and rows[0]["superseded_at"] is not None and rows[1]["superseded_at"] is None
    report = (await api_client.get(f"/api/requests/reports/completions?{report_window()}", headers=admin)).json()
    assert report["total_completed"] == 1 and report["total_records"] == 1 and report["records"][0]["sequence"] == 2
    # boundary at the function level: a stale supersede intent for sequence 1 applied AFTER sequence 2 exists (a
    # recovery that runs late) touches sequence 1 only
    stale = {"action": "supersede", "sequence": 1, "at": c.stamp(), "actor_id": "u_admin", "reason": "late recovery"}
    await db.requests.update_one({"id": rid}, {"$push": {"ledger_pending": stale}})
    assert await queries.reconcile_completion_ledger() == 0                       # nothing left to supersede at sequence 1
    rows = await db.request_completions.find({"request_id": rid}, {"_id": 0}).sort("sequence", 1).to_list(None)
    assert rows[1]["superseded_at"] is None and rows[0]["reopen_reason"] == "customer called back"   # sequence 2 intact, first supersession kept
    assert (await db.requests.find_one({"id": rid}, {"_id": 0}))["ledger_pending"] == []
    # a completion intent whose row insert failed, followed by a reopen: the reopen writes the row first, then supersedes
    rid2 = (await api_client.post("/api/requests", json={"request_type": "callback"}, headers=cust)).json()["id"]
    await api_client.post(f"/api/requests/{rid2}/claim", headers=t1)

    async def boom(doc):
        raise RuntimeError("ledger store unavailable")
    with pytest.MonkeyPatch.context() as fault:
        fault.setattr(queries, "insert_completion_row", boom)
        with pytest.raises(RuntimeError):
            await api_client.post(f"/api/requests/{rid2}/complete", json={}, headers=t1)
    assert await db.request_completions.count_documents({"request_id": rid2}) == 0
    assert (await api_client.patch(f"/api/requests/{rid2}", json={"action": "reopen", "status": "pending", "reason": "wrong outcome"}, headers=admin)).status_code == 200
    rows = await db.request_completions.find({"request_id": rid2}, {"_id": 0}).to_list(None)
    assert len(rows) == 1 and rows[0]["sequence"] == 1 and rows[0]["superseded_at"] is not None
    assert (await db.requests.find_one({"id": rid2}, {"_id": 0}))["ledger_pending"] == []


# ---- G02-B: bounded reconciliation with forward progress ------------------------------------------------------------

async def test_g02b_reconciliation_reaches_missing_rows_beyond_the_first_batch_and_intents_immediately(api_client, isolated_db, seeded_users, login_helper):
    """Review: with 501 resolved requests, the newest 500 already had rows and the oldest missing row was never
    examined, no matter how often reconciliation ran. Now (1) records resolved by builds without intents are walked
    with a durable cursor that advances every call and wraps, so every record is examined within one full walk, and
    (2) intents are settled on the first call regardless of how many resolved records exist."""
    db = isolated_db["db"]
    admin, t1, cust = await auth(login_helper, "9000000000"), await auth(login_helper, "9000000001"), await auth(login_helper, "9000000004")
    now = c.now()
    docs, rows = [], []
    for i in range(502):   # legacy build: no `ledger_pending`; g02b-0000 is the NEWEST, g02b-0501 the OLDEST
        ts = (now - timedelta(seconds=i)).isoformat()
        docs.append({"id": f"g02b-{i:04d}", "status": "resolved", "completed_by_id": "u_tele1", "completed_by_name": "Tele One", "completed_by_role": "telecaller",
                     "resolved_at": ts, "completion_count": 1, "created_at": ts, "user_id": "u_cust1", "user_name": "Customer One", "request_type": "callback",
                     "version": 3, "events": [], "outcome": "other"})
        if 0 < i < 501:   # rows exist for all but the newest AND the oldest record
            rows.append({"id": f"row-{i}", "key": f"g02b-{i:04d}:1", "request_id": f"g02b-{i:04d}", "sequence": 1, "actor_id": "u_tele1", "actor_name": "Tele One",
                         "actor_role": "telecaller", "completed_at": ts, "completed_date_ist": c.now().astimezone(queries.IST).date().isoformat(),
                         "customer_id": "u_cust1", "outcome": "other", "superseded_at": None})
    await db.requests.insert_many(docs)
    await db.request_completions.insert_many(rows)
    # batch 1 (500 records, oldest first) repairs the oldest; batch 2 reaches the two remaining records and repairs the newest
    assert await queries.reconcile_completion_ledger() == 1
    assert await db.request_completions.count_documents({"key": "g02b-0501:1"}) == 1
    assert await db.request_completions.count_documents({"key": "g02b-0000:1"}) == 0
    assert await queries.reconcile_completion_ledger() == 1
    assert await db.request_completions.count_documents({"key": "g02b-0000:1"}) == 1
    cursor = await db.maintenance_cursors.find_one({"_id": queries.SWEEP_CURSOR})
    assert cursor["cycles"] == 1 and cursor["after"] is None                     # the walk wrapped: the next call starts over
    assert await queries.reconcile_completion_ledger() == 0
    assert await db.request_completions.count_documents({}) == 502
    # an intent left by an interrupted completion of THIS build is settled on the first call, whatever the backlog
    rid = (await api_client.post("/api/requests", json={"request_type": "ask_price"}, headers=cust)).json()["id"]
    await api_client.post(f"/api/requests/{rid}/claim", headers=t1)

    async def boom(doc):
        raise RuntimeError("ledger store unavailable")
    with pytest.MonkeyPatch.context() as fault:
        fault.setattr(queries, "insert_completion_row", boom)
        with pytest.raises(RuntimeError):
            await api_client.post(f"/api/requests/{rid}/complete", json={}, headers=t1)
    assert await queries.reconcile_completion_ledger() == 1
    assert await db.request_completions.count_documents({"request_id": rid}) == 1
    # the report (which runs the reconciliation) sees every completion exactly once
    report = (await api_client.get(f"/api/requests/reports/completions?{report_window()}&limit=1", headers=admin)).json()
    assert report["total_completed"] == 503 and report["total_records"] == 503


# ---- G03: full-catalogue rotation ---------------------------------------------------------------------------------

async def test_g03_rotation_over_the_whole_catalogue_never_starves_old_unseen_products(api_client, isolated_db, seeded_users, login_helper):
    """Review: with 9,001 eligible products and 5,000 seen, the oldest unseen product could never enter the selected
    window (at most 5,000 exclusions, then the newest 4,000). Now unseen candidates come from an indexed walk over the
    complete catalogue that continues where the account's previous session stopped and wraps around: every unseen
    product is offered within one rotation, a seen product is never re-offered as unseen, pages stay stable,
    exhaustion is reported correctly and accounts are isolated."""
    db = isolated_db["db"]
    now = c.now()
    total = 9001
    await db.products.insert_many([{"id": f"g03-{i:05d}", "title": f"P{i}", "metal_type": "silver", "visibility": "visible", "is_deleted": False,
                                    "created_at": (now - timedelta(seconds=i)).isoformat()} for i in range(total)])   # g03-00000 newest ... g03-09000 OLDEST
    newest_5000 = [f"g03-{i:05d}" for i in range(5000)]
    seen_ts = lambda i: (now - timedelta(days=1) + timedelta(seconds=i)).isoformat()
    await db.product_impressions.insert_many([{"user_id": "u_cust1", "product_id": pid, "seen_at": seen_ts(i), "first_seen_at": seen_ts(i), "count": 1, "session_id": ""}
                                              for i, pid in enumerate(newest_5000)])   # > 5,000 viewed products: the newest 5,000
    cust = await auth(login_helper, "9000000004")
    seen = set(newest_5000)
    s1 = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=cust)).json()
    assert s1["unseen"] == discovery.MAX_SESSION_IDS == 4000 and s1["truncated"] is True and s1["exhausted"] is False and s1["seen"] == 0
    order1 = (await db.discovery_sessions.find_one({"id": s1["session_id"]}))["order"]
    assert len(set(order1)) == 4000 and set(order1) == {f"g03-{i:05d}" for i in range(5000, 9000)}   # the next 4,000 unseen in catalogue order, no repeat
    # stable pagination: a page is a fixed slice of the stored order, re-reading gives the same ids
    page2 = (await api_client.get(f"/api/discovery/sessions/{s1['session_id']}?page=2&limit=50", headers=cust)).json()
    assert [p["id"] for p in page2["products"]] == order1[50:100] and page2["pages"] == 80
    assert [p["id"] for p in (await api_client.get(f"/api/discovery/sessions/{s1['session_id']}?page=1&limit=50", headers=cust)).json()["products"]] == order1[:50]
    # the account refreshes WITHOUT viewing anything: the rotation continues - the oldest product, unseen since the
    # beginning, is offered now (the review's starved product), followed by still-unseen products, never a seen one
    s2 = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=cust)).json()
    order2 = (await db.discovery_sessions.find_one({"id": s2["session_id"]}))["order"]
    assert "g03-09000" in order2[:s2["unseen"]] and s2["unseen"] == 4000
    assert set(order2[:s2["unseen"]]).isdisjoint(seen) and len(set(order2)) == 4000
    # after actually viewing every product offered so far the catalogue is exhausted for this account: the fallback is
    # the least-recently-seen products (the original 5,000 lead), bounded, and `exhausted` is reported
    ts = c.stamp()
    viewed = set(order1) | set(order2[:s2["unseen"]])
    await db.product_impressions.insert_many([{"user_id": "u_cust1", "product_id": pid, "seen_at": ts, "first_seen_at": ts, "count": 1, "session_id": s2["session_id"]} for pid in viewed])
    assert len(seen | viewed) == total
    s3 = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=cust)).json()
    assert s3["unseen"] == 0 and s3["exhausted"] is True and s3["truncated"] is False and s3["seen"] == 4000
    assert {p["id"] for p in s3["products"]} <= seen and all(p["discovery"]["seen_before"] for p in s3["products"])
    # account isolation: another account's rotation starts at the newest product and ignores this account's history
    other = await auth(login_helper, "9000000005")
    s4 = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=other)).json()
    order4 = (await db.discovery_sessions.find_one({"id": s4["session_id"]}))["order"]
    assert s4["unseen"] == 4000 and set(order4) == {f"g03-{i:05d}" for i in range(4000)}
    # new arrivals lead the next session of a rotation in progress (they are not parked until the walk wraps)
    await db.products.insert_one({"id": "g03-new", "title": "New", "metal_type": "silver", "visibility": "visible", "is_deleted": False, "created_at": c.stamp()})
    s5 = (await api_client.post("/api/discovery/sessions", json={"limit": 50}, headers=other)).json()
    order5 = (await db.discovery_sessions.find_one({"id": s5["session_id"]}))["order"]
    assert "g03-new" in order5[:s5["unseen"]] and s5["unseen"] == 4000 and len(set(order5)) == 4000
    assert set(order5) - {"g03-new"} <= {f"g03-{i:05d}" for i in range(4000, 8000)}
    # filters keep their own continuation and the first account's cursor was never touched by the other account
    cursors = {(d["user_id"], d["filter_key"]): d async for d in db.discovery_cursors.find({}, {"_id": 0})}
    assert set(cursors) == {("u_cust1", "||"), ("u_cust2", "||")} and cursors[("u_cust1", "||")]["sessions"] == 3


# ---- G04-A: partial fan-out ----------------------------------------------------------------------------------------

async def register(api_client, headers, token):
    assert (await api_client.post("/api/notifications/devices", json={"token": token, "platform": "android"}, headers=headers)).status_code == 200


async def test_g04a_partial_query_fan_out_is_completed_by_the_retry_and_never_mistaken_for_done(api_client, isolated_db, seeded_users, login_helper, recording_transport, monkeypatch):
    """Review: after the first batch was stored and a later batch failed, the retry answered duplicate=True - the
    remaining recipients never got a batch and no inbox rows were repaired. Now the event carries a frozen audience and
    a completion state: a retry completes the remaining chunks and inbox rows and only a complete event is a duplicate."""
    db = isolated_db["db"]
    cust, t1, t2 = await auth(login_helper, "9000000004"), await auth(login_helper, "9000000001"), await auth(login_helper, "9000000002")
    tokens = {"u_tele1": "ExponentPushToken[g04aaaaaaaaaaaaaa]", "u_tele2": "ExponentPushToken[g04bbbbbbbbbbbbbb]"}
    await register(api_client, t1, tokens["u_tele1"]); await register(api_client, t2, tokens["u_tele2"])
    monkeypatch.setattr(notifications, "USERS_PER_BATCH", 1)   # two telecallers -> two chunks: the multi-batch algorithm at small scale
    real_enqueue, calls = notifications.enqueue, {"n": 0}

    async def second_batch_fails(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("outbox unavailable")
        return await real_enqueue(*a, **k)
    monkeypatch.setattr(notifications, "enqueue", second_batch_fails)
    r = await api_client.post("/api/requests", json={"request_type": "callback"}, headers={**cust, "Idempotency-Key": "g04-1"})
    assert r.status_code == 200                                                          # the customer's request never fails
    rid = r.json()["id"]
    assert (await db.requests.find_one({"id": rid}))["notify_state"] == "pending"
    assert await db.notification_outbox.count_documents({"request_id": rid}) == 1       # exactly the partial state the review reproduced
    event = await db.notification_events.find_one({"id": f"query:{rid}"}, {"_id": 0})
    assert event["state"] == "pending" and set(event["recipients"]) == {"u_tele1", "u_tele2"}
    # a retry while the fault persists changes nothing and keeps the marker pending
    monkeypatch.setattr(notifications, "enqueue", second_batch_fails); calls["n"] = 1
    assert await queries.reconcile_pending_notifications(min_age_seconds=0) == 0
    assert (await db.requests.find_one({"id": rid}))["notify_state"] == "pending"
    # the outbox is back: the worker's reconcile completes the remaining recipient - not "duplicate"
    monkeypatch.setattr(notifications, "enqueue", real_enqueue)
    assert await queries.reconcile_pending_notifications(min_age_seconds=0) == 1
    jobs = await db.notification_outbox.find({"request_id": rid}, {"_id": 0}).to_list(None)
    assert sorted(j["key"] for j in jobs) == [f"query:{rid}:0", f"query:{rid}:1"]
    assert {m["to"] for j in jobs for m in j["messages"]} == set(tokens.values())          # queued recipient set: both devices
    assert {n["user_id"] async for n in db.notifications.find({"request_id": rid})} == {"u_tele1", "u_tele2"}   # inbox set: both
    assert await db.notifications.count_documents({"request_id": rid}) == 2
    assert (await db.notification_events.find_one({"id": f"query:{rid}"}))["state"] == "complete"
    assert (await db.requests.find_one({"id": rid}))["notify_state"] == "queued"
    # now it IS a duplicate: same-key creation retry, direct re-notification and the worker add nothing
    again = await api_client.post("/api/requests", json={"request_type": "callback"}, headers={**cust, "Idempotency-Key": "g04-1"})
    assert again.status_code == 200 and again.json()["id"] == rid
    assert (await notifications.query_created(await db.requests.find_one({"id": rid}, {"_id": 0})))["duplicate"] is True
    assert await db.notification_outbox.count_documents({"request_id": rid}) == 2 and await db.notifications.count_documents({"request_id": rid}) == 2
    await notifications.tick()
    assert sorted(m["to"] for batch in recording_transport for m in batch) == sorted(tokens.values())   # each device exactly once


async def test_g04a_batch_stored_but_inbox_rows_missing_is_repaired_without_a_second_batch(api_client, isolated_db, seeded_users, login_helper, recording_transport):
    """Review (second variant): one batch for two staff accounts was stored, the inbox insertion failed, and every retry
    answered duplicate=True - both inboxes stayed empty for ever. This is the state an earlier build left behind;
    recovery must complete the inbox rows without queueing the batch again."""
    db = isolated_db["db"]
    t1, t2 = await auth(login_helper, "9000000001"), await auth(login_helper, "9000000002")
    await register(api_client, t1, "ExponentPushToken[g04cccccccccccccc]"); await register(api_client, t2, "ExponentPushToken[g04dddddddddddddd]")
    doc = {"id": "req-g04-inbox", "request_type": "callback", "shop_name": "Shop One", "product_ids": []}
    # the earlier build's partial state: batch stored, inbox rows missing, and (new) the event left pending
    devices = await notifications.devices_for(["u_tele1", "u_tele2"])
    rows = {d["user_id"]: notifications.inbox_row(d["user_id"], "New customer query", "b", "operational", "/staff-requests?request=req-g04-inbox", request_id="req-g04-inbox", key_prefix="query:req-g04-inbox") for d in devices}
    assert await notifications.enqueue("query:req-g04-inbox:0", "operational", [notifications.message_for(d, rows[d["user_id"]]) for d in devices], request_id="req-g04-inbox")
    await db.notification_events.insert_one({"id": "query:req-g04-inbox", "kind": "operational", "recipients": ["u_tele1", "u_tele2"], "title": "New customer query", "body": "b",
                                             "destination": "/staff-requests?request=req-g04-inbox", "image_url": "", "campaign_id": "", "request_id": "req-g04-inbox",
                                             "state": "pending", "created_at": c.stamp(), "attempts": 1})
    assert await db.notifications.count_documents({"request_id": "req-g04-inbox"}) == 0
    result = await notifications.query_created(doc)
    assert result.get("duplicate") is not True and result["existing_batches"] == 1 and result["batches"] == 0
    assert {n["user_id"] async for n in db.notifications.find({"request_id": "req-g04-inbox"})} == {"u_tele1", "u_tele2"}
    assert await db.notification_outbox.count_documents({"request_id": "req-g04-inbox"}) == 1        # no second batch
    assert (await notifications.query_created(doc))["duplicate"] is True
    await notifications.tick()
    assert len(recording_transport) == 1 and len(recording_transport[0]) == 2


# ---- G04-B: interrupted campaigns ----------------------------------------------------------------------------------

class ProcessStop(BaseException):
    """Models an abrupt process stop: no `except Exception` handler runs."""


async def test_g04b_campaign_interrupted_by_a_process_stop_is_resumed_by_the_worker_after_the_lease_expires(api_client, isolated_db, seeded_users, login_helper, recording_transport, monkeypatch):
    """Review: a process stop after `status=sending` stranded the campaign for ever (a later send: CAMPAIGN_ALREADY_SENT;
    nothing queued). Now the fan-out runs under a durable lease and the outbox worker resumes the same idempotent event
    once the lease expired, then finalises the campaign."""
    db = isolated_db["db"]
    admin = await auth(login_helper, "9000000000")
    tokens = {"u_cust1": "ExponentPushToken[g04eeeeeeeeeeeeee]", "u_cust2": "ExponentPushToken[g04ffffffffffffff]"}
    for uid, token in tokens.items():
        await register(api_client, await auth(login_helper, seeded_users[uid]["phone"]), token)
    cid = (await api_client.post("/api/admin/notifications/campaigns", json={"title": "Diwali", "body": "Offer", "destination": "/(tabs)", "audience": {"target": "customers"}}, headers=admin)).json()["id"]
    real_fan_out = notifications.fan_out

    async def stopped(*a, **k):
        raise ProcessStop()
    monkeypatch.setattr(notifications, "fan_out", stopped)
    admin_user = await db.users.find_one({"id": "u_admin"}, {"_id": 0})
    with pytest.raises(ProcessStop):
        await notifications.send_campaign(cid, notifications.SendConfirmation(confirm_users=2), admin_user)
    campaign = await db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    assert campaign["status"] == "sending" and campaign["fanout"]["state"] == "pending" and campaign["fanout"]["lease_until"] > c.stamp()
    assert await db.notification_outbox.count_documents({}) == 0 and await db.notifications.count_documents({}) == 0 and recording_transport == []
    monkeypatch.setattr(notifications, "fan_out", real_fan_out)
    # while the lease is valid the original process may still be working: nothing is resumed
    await notifications.tick()
    assert (await db.notification_campaigns.find_one({"id": cid}))["status"] == "sending"
    # restart: the lease expires and the worker's pass completes the campaign end to end
    await db.notification_campaigns.update_one({"id": cid}, {"$set": {"fanout.lease_until": (c.now() - timedelta(seconds=1)).isoformat()}})
    await notifications.tick()
    campaign = await db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    assert campaign["status"] == "sent" and campaign["fanout"]["state"] == "complete" and campaign["fanout"]["resumes"] == 1
    assert campaign["stats"]["users"] == 2 and campaign["stats"]["devices"] == 2 and campaign["stats"]["batches"] == 1 and campaign["stats"]["accepted"] == 2
    assert {n["user_id"] async for n in db.notifications.find({"campaign_id": cid})} == {"u_cust1", "u_cust2"}       # inbox set
    assert sorted(m["to"] for batch in recording_transport for m in batch) == sorted(tokens.values())                 # queued/sent set
    assert await db.notifications.count_documents({"campaign_id": cid}) == 2
    # the contract is unchanged for a second send, and further worker passes change nothing
    again = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 2}, headers=admin)
    assert again.status_code == 409 and again.json()["code"] == "CAMPAIGN_ALREADY_SENT"
    await notifications.tick()
    assert await db.notification_outbox.count_documents({"campaign_id": cid}) == 1 and len(recording_transport) == 1


async def test_g04b_resend_after_a_partial_campaign_completes_the_frozen_audience_only(api_client, isolated_db, seeded_users, login_helper, recording_transport, monkeypatch):
    """Eligibility changes between the attempt that failed after the first batch and the resend: a customer who joined
    since is NOT silently added to the half-sent campaign, a device unlinked since receives no push (its owner keeps the
    inbox row), and nothing already stored is duplicated. Inbox and queued sets are asserted, not the HTTP status."""
    db = isolated_db["db"]
    admin = await auth(login_helper, "9000000000")
    tokens = {"u_cust1": "ExponentPushToken[g04gggggggggggggg]", "u_cust2": "ExponentPushToken[g04hhhhhhhhhhhhhh]"}
    sessions = {}
    for uid, token in tokens.items():
        sessions[uid] = await auth(login_helper, seeded_users[uid]["phone"])
        await register(api_client, sessions[uid], token)
    monkeypatch.setattr(notifications, "USERS_PER_BATCH", 1)
    cid = (await api_client.post("/api/admin/notifications/campaigns", json={"title": "T", "body": "B", "destination": "/(tabs)", "audience": {"target": "customers"}}, headers=admin)).json()["id"]
    real_enqueue, calls = notifications.enqueue, {"n": 0}

    async def second_batch_fails(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("outbox unavailable")
        return await real_enqueue(*a, **k)
    monkeypatch.setattr(notifications, "enqueue", second_batch_fails)
    failed = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 2}, headers=admin)
    assert failed.status_code == 503 and failed.json()["code"] == "FAN_OUT_FAILED"
    assert (await db.notification_campaigns.find_one({"id": cid}))["status"] == "draft"
    assert await db.notification_outbox.count_documents({"campaign_id": cid}) == 1
    assert (await db.notification_events.find_one({"id": f"campaign:{cid}"}))["state"] == "pending"
    # the world changes before the resend
    monkeypatch.setattr(notifications, "enqueue", real_enqueue)
    await db.users.insert_one({k: v for k, v in seeded_users["u_cust2"].items() if k != "_id"} | {"id": "u_joined", "phone": "9000000008", "phone_normalized": "9000000008", "name": "Joined Later"})
    await register(api_client, await auth(login_helper, "9000000008"), "ExponentPushToken[g04iiiiiiiiiiiiii]")
    await api_client.post("/api/notifications/devices/unlink", json={"token": tokens["u_cust2"]}, headers=sessions["u_cust2"])
    # the confirmation refers to the FROZEN audience (2), not to today's 3 eligible users
    changed = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 3}, headers=admin)
    assert changed.status_code == 409 and changed.json()["code"] == "AUDIENCE_CHANGED"
    ok = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 2}, headers=admin)
    assert ok.status_code == 200, ok.text
    await notifications.tick()
    campaign = await db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    assert campaign["status"] == "sent" and campaign["fanout"]["state"] == "complete"
    assert {n["user_id"] async for n in db.notifications.find({"campaign_id": cid})} == {"u_cust1", "u_cust2"}   # frozen audience, both inbox rows
    assert await db.notifications.count_documents({"campaign_id": cid}) == 2
    jobs = await db.notification_outbox.find({"campaign_id": cid}, {"_id": 0}).to_list(None)
    assert len(jobs) == 1 and [m["to"] for m in jobs[0]["messages"]] == [tokens["u_cust1"]]                          # no batch for the unlinked device
    assert [m["to"] for batch in recording_transport for m in batch] == [tokens["u_cust1"]]
    assert await db.notifications.count_documents({"user_id": "u_joined"}) == 0
    assert (await notifications.fan_out(f"campaign:{cid}", "marketing", ["u_joined"], "T", "B", "/(tabs)", campaign_id=cid))["duplicate"] is True


async def test_g04b_campaign_is_not_marked_sent_while_its_fan_out_is_still_queueing_batches(api_client, isolated_db, seeded_users, login_helper, recording_transport, monkeypatch):
    """The worker may process the first batch before the fan-out stored the last one: an empty outbox in between is not
    "everything sent". The campaign becomes `sent` only after the fan-out completed and every batch was processed."""
    db = isolated_db["db"]
    admin = await auth(login_helper, "9000000000")
    for uid, token in {"u_cust1": "ExponentPushToken[g04jjjjjjjjjjjjjj]", "u_cust2": "ExponentPushToken[g04kkkkkkkkkkkkkk]"}.items():
        await register(api_client, await auth(login_helper, seeded_users[uid]["phone"]), token)
    monkeypatch.setattr(notifications, "USERS_PER_BATCH", 1)
    cid = (await api_client.post("/api/admin/notifications/campaigns", json={"title": "T", "body": "B", "destination": "/(tabs)", "audience": {"target": "customers"}}, headers=admin)).json()["id"]
    real_enqueue, seen_status = notifications.enqueue, {}

    async def worker_runs_between_batches(*a, **k):
        stored = await real_enqueue(*a, **k)
        if a[0].endswith(":0"):
            job = await notifications.claim_job()            # the worker processes batch 0 before batch 1 exists
            await notifications.process_job(job)
            seen_status["after_first_batch"] = (await db.notification_campaigns.find_one({"id": cid}))["status"]
        return stored
    monkeypatch.setattr(notifications, "enqueue", worker_runs_between_batches)
    ok = await api_client.post(f"/api/admin/notifications/campaigns/{cid}/send", json={"confirm_users": 2}, headers=admin)
    assert ok.status_code == 200 and ok.json()["status"] == "queued" and ok.json()["batches"] == 2
    assert seen_status["after_first_batch"] == "sending"                                 # not prematurely "sent"
    await notifications.tick()
    campaign = await db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    assert campaign["status"] == "sent" and campaign["stats"]["accepted"] == 2 and campaign["stats"]["batches"] == 2
    assert len([m for batch in recording_transport for m in batch]) == 2
