"""Central query workspace: fresh-first list, atomic first claim, ownership, heads, completion ledger, IST reports,
release on staff disable, creation-path notifications (R11-R14, R12, R15 subrows)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from shared import core as c
from shared import notifications, queries

pytestmark = pytest.mark.asyncio


async def auth(login_helper, phone):
    body = await login_helper(phone)
    return {"Authorization": f"Bearer {body['token']}"}


async def seed_products(db, n=3):
    now = datetime.now(timezone.utc).isoformat()
    for i in range(n):
        await db.products.insert_one({"id": f"p{i}", "title": f"Ring {i}", "product_code": f"R{i}", "metal_type": "silver", "category": "rings",
                                      "images": [f"/api/files/yash-trade/products/p{i}.png"], "storage_path": f"yash-trade/products/p{i}.png",
                                      "thumbnail_path": f"yash-trade/products/p{i}_t.png", "visibility": "visible", "is_deleted": False,
                                      "created_at": now, "updated_at": now, "version": 0, "weight": 12.5 + i})


@pytest.fixture
def push_double(monkeypatch):
    sent = []

    async def fake_send(messages):
        sent.append(list(messages))
        return [{"status": "ok", "id": f"t{len(sent)}-{i}"} for i, _ in enumerate(messages)]

    monkeypatch.setattr(notifications, "transport", fake_send)
    return sent


async def test_creation_paths_notify_telecallers_once_and_first_claim_wins(api_client, isolated_db, seeded_users, login_helper, push_double):
    db = isolated_db["db"]
    await seed_products(db)
    for uid, tok in (("u_tele1", "ExponentPushToken[tele1aaaaaaaaaa]"), ("u_tele2", "ExponentPushToken[tele2bbbbbbbbbb]")):
        h = await auth(login_helper, seeded_users[uid]["phone"])
        r = await api_client.post("/api/notifications/devices", json={"token": tok, "platform": "android"}, headers=h)
        assert r.status_code == 200, r.text
    cust = await auth(login_helper, seeded_users["u_cust1"]["phone"])
    body = {"request_type": "ask_price", "product_ids": ["p0", "p1"], "notes": "price please"}
    r1 = await api_client.post("/api/requests", json=body, headers={**cust, "Idempotency-Key": "k-1"})
    r2 = await api_client.post("/api/requests", json=body, headers={**cust, "Idempotency-Key": "k-1"})  # retry
    assert r1.status_code == 200 and r2.status_code == 200 and r1.json()["id"] == r2.json()["id"]
    rid = r1.json()["id"]
    assert r1.json()["head"] == "pending"  # customer view: lifecycle only
    # one inbox row per telecaller, one outbox batch, despite the retried creation
    assert await db.notifications.count_documents({"request_id": rid}) == 2
    assert await db.notification_outbox.count_documents({"request_id": rid}) == 1
    # cart path raises the same event
    await db.cart.insert_one({"id": "c1", "user_id": "u_cust1", "product_id": "p2", "quantity": 1, "status": "active", "notes": ""})
    r = await api_client.post("/api/cart/submit", json={"notes": "cart"}, headers=cust)
    assert r.status_code == 200, r.text
    assert await db.notifications.count_documents({"request_id": r.json()["request_id"]}) == 2
    # worker delivers through the (fake) provider and records acceptance
    await notifications.tick()
    assert len(push_double) == 2 and all(m["data"]["destination"].startswith("/staff-requests?request=") for batch in push_double for m in batch)
    assert not any("9000000004" in (m["body"] + m["title"]) for batch in push_double for m in batch)  # no phone on the lock screen
    job = await db.notification_outbox.find_one({"request_id": rid})
    assert job["status"] == "sent" and job["accepted"] == 2
    # both telecallers see it fresh-first; simultaneous claims -> exactly one winner
    t1, t2 = await auth(login_helper, "9000000001"), await auth(login_helper, "9000000002")
    listing = await api_client.get("/api/requests?view=all_pending", headers=t1)
    assert listing.status_code == 200 and listing.json()["requests"][0]["id"] == r.json()["request_id"]  # newest cart request on top
    assert listing.json()["sort"] == "fresh" and listing.json()["counts"]["all_pending"] == 2
    a, b = await asyncio.gather(api_client.post(f"/api/requests/{rid}/claim", headers=t1), api_client.post(f"/api/requests/{rid}/claim", headers=t2))
    codes = sorted([a.status_code, b.status_code])
    assert codes == [200, 409], (a.text, b.text)
    loser = a if a.status_code == 409 else b
    assert loser.json()["code"] in {"ALREADY_ASSIGNED", "VERSION_CONFLICT"}
    winner_headers = t1 if a.status_code == 200 else t2
    other_headers = t2 if a.status_code == 200 else t1
    doc = await db.requests.find_one({"id": rid}, {"_id": 0})
    assert doc["status"] == "in_progress" and doc["claimed_at"] and doc["assignee_id"] in {"u_tele1", "u_tele2"}
    # idempotent re-claim by the winner, denied edits by the other telecaller
    again = await api_client.post(f"/api/requests/{rid}/claim", headers=winner_headers)
    assert again.status_code == 200 and again.json().get("already_claimed") is True
    denied = await api_client.patch(f"/api/requests/{rid}", json={"head": "contacted", "notes": "x"}, headers=other_headers)
    assert denied.status_code == 403 and denied.json()["code"] == "CLAIM_REQUIRED"
    denied_complete = await api_client.post(f"/api/requests/{rid}/complete", json={}, headers=other_headers)
    assert denied_complete.status_code == 403
    # the winner works the query: head, follow-up, note; stays in pending list
    work = await api_client.patch(f"/api/requests/{rid}", json={"head": "follow_up", "follow_up_at": "2026-09-22T10:00:00+05:30", "notes": "call tomorrow", "version": doc["version"]}, headers=winner_headers)
    assert work.status_code == 200, work.text
    assert work.json()["head"] == "follow_up" and work.json()["follow_up_at"] == "2026-09-22T04:30:00+00:00"
    pending = await api_client.get("/api/requests?view=my_pending", headers=winner_headers)
    assert [q["id"] for q in pending.json()["requests"]] == [rid]
    detail = await api_client.get(f"/api/requests/{rid}", headers=winner_headers)
    assert detail.status_code == 200
    d = detail.json()
    assert [i["product_id"] for i in d["items"]] == ["p0", "p1"] and d["items"][0]["available"] is True and d["items"][0]["weight"] == 12.5
    assert d["contact"] == {"tel": "+919000000004", "whatsapp": "919000000004"} and d["customer_phone_display"].startswith("+91")
    assert d["permissions"]["can_work"] is True
    # billing reads the same central state but cannot work it
    bill = await auth(login_helper, "9000000003")
    r = await api_client.get("/api/requests?view=all_pending", headers=bill)
    assert r.status_code == 200 and r.json()["permissions"] == {"can_work": False, "can_assign": False, "can_reopen": False}
    assert (await api_client.post(f"/api/requests/{rid}/claim", headers=bill)).status_code == 403
    # Mark Complete: atomic, idempotent, leaves pending, appears in completed history + ledger once
    done = await api_client.post(f"/api/requests/{rid}/complete", json={"outcome": "converted", "notes": "ordered"}, headers=winner_headers)
    assert done.status_code == 200 and done.json()["status"] == "resolved" and done.json()["outcome"] == "converted"
    retry = await api_client.post(f"/api/requests/{rid}/complete", json={"outcome": "converted"}, headers=winner_headers)
    assert retry.status_code == 200 and retry.json().get("already_completed") is True
    assert await db.request_completions.count_documents({"request_id": rid}) == 1
    assert rid not in [q["id"] for q in (await api_client.get("/api/requests?view=all_pending", headers=t1)).json()["requests"]]
    mine = await api_client.get("/api/requests?view=my_completed", headers=winner_headers)
    assert [q["id"] for q in mine.json()["requests"]] == [rid]
    # product later hidden: detail keeps the snapshot with an explicit unavailable state
    await db.products.update_one({"id": "p0"}, {"$set": {"visibility": "hidden"}})
    d = (await api_client.get(f"/api/requests/{rid}", headers=winner_headers)).json()
    assert d["items"][0]["available"] is False and d["items"][0]["image_state"] == "unavailable" and d["items"][0]["title"] == "Ring 0"
    # customer view exposes lifecycle only, no staff internals
    my = await api_client.get("/api/requests/my", headers=cust)
    row = next(q for q in my.json()["requests"] if q["id"] == rid)
    assert row["status"] == "resolved" and "events" not in row and "assignee_id" not in row and "follow_up_at" not in row


async def test_admin_reports_reopen_and_staff_disable_release(api_client, isolated_db, seeded_users, login_helper, push_double):
    db = isolated_db["db"]
    await seed_products(db, 1)
    admin, t1, cust = await auth(login_helper, "9999813334"), await auth(login_helper, "9000000001"), await auth(login_helper, "9000000004")
    ids = []
    for i in range(3):
        r = await api_client.post("/api/requests", json={"request_type": "callback", "notes": f"n{i}"}, headers={**cust, "Idempotency-Key": f"cb-{i}"})
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    for rid in ids[:2]:
        assert (await api_client.post(f"/api/requests/{rid}/claim", headers=t1)).status_code == 200
    assert (await api_client.post(f"/api/requests/{ids[0]}/complete", json={"outcome": "not_interested"}, headers=t1)).status_code == 200
    today = c.now().astimezone(queries.IST).date().isoformat()
    report = await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)
    assert report.status_code == 200, report.text
    assert report.json()["telecallers"] == [{"id": "u_tele1", "name": "Tele One", "role": "telecaller", "completed": 1, "records": 1, "account_status": "active"}]
    # telecaller sees only their own row; billing is denied
    own = await api_client.get(f"/api/requests/reports/completions?date={today}", headers=t1)
    assert own.json()["total_completed"] == 1
    assert (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=await auth(login_helper, "9000000003"))).status_code == 403
    # admin reopen requires a reason, supersedes the completion, count drops to 0; re-completion counts again once
    assert (await api_client.patch(f"/api/requests/{ids[0]}", json={"action": "reopen", "status": "pending"}, headers=admin)).status_code == 422
    reopened = await api_client.patch(f"/api/requests/{ids[0]}", json={"action": "reopen", "status": "pending", "reason": "customer called back"}, headers=admin)
    assert reopened.status_code == 200 and reopened.json()["status"] == "pending" and reopened.json()["assignee_id"] == ""
    assert (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)).json()["total_completed"] == 0
    assert (await api_client.post(f"/api/requests/{ids[0]}/claim", headers=t1)).status_code == 200
    assert (await api_client.post(f"/api/requests/{ids[0]}/complete", json={}, headers=t1)).status_code == 200
    assert (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)).json()["total_completed"] == 1
    assert await db.request_completions.count_documents({"request_id": ids[0]}) == 2
    # admin reassignment needs a reason and is audited; telecaller cannot reassign
    assert (await api_client.patch(f"/api/requests/{ids[1]}", json={"action": "assign", "assigned_to": "u_tele2"}, headers=admin)).status_code == 422
    assert (await api_client.patch(f"/api/requests/{ids[1]}", json={"action": "assign", "assigned_to": "u_tele2", "reason": "load balance"}, headers=t1)).status_code == 403
    moved = await api_client.patch(f"/api/requests/{ids[1]}", json={"action": "assign", "assigned_to": "u_tele2", "reason": "load balance"}, headers=admin)
    assert moved.status_code == 200 and moved.json()["assignee_id"] == "u_tele2" and moved.json()["events"][-1]["type"] == "assignment"
    # stale version from the old screen is refused
    assert (await api_client.patch(f"/api/requests/{ids[1]}", json={"notes": "late", "version": 0}, headers=admin)).status_code == 409
    # disabling a telecaller releases their open queries and cuts their devices/sessions
    t2 = await auth(login_helper, "9000000002")
    assert (await api_client.post("/api/notifications/devices", json={"token": "ExponentPushToken[tele2cccccccccc]", "platform": "ios"}, headers=t2)).status_code == 200
    r = await api_client.patch("/api/integrations/staff/u_tele2", json={"status": "inactive"}, headers=admin)
    assert r.status_code == 200 and r.json()["queries_released"] == 1
    doc = await db.requests.find_one({"id": ids[1]}, {"_id": 0})
    assert doc["status"] == "pending" and doc["assignee_id"] == "" and doc["events"][-1]["type"] == "release"
    assert (await db.push_devices.find_one({"user_id": "u_tele2"}))["enabled"] is False
    assert (await api_client.get("/api/auth/me", headers=t2)).status_code == 401
    # invalid inputs
    assert (await api_client.patch(f"/api/requests/{ids[2]}", json={"head": "bogus"}, headers=admin)).status_code == 422
    assert (await api_client.get("/api/requests?view=nonsense", headers=admin)).status_code == 422
    # upload executive has no query access at all
    await db.users.insert_one({**{k: v for k, v in seeded_users["u_tele1"].items() if k != "_id"}, "id": "u_upload", "phone": "9000000009", "phone_normalized": "9000000009", "role": "upload_executive", "name": "Uploader"})
    up = await auth(login_helper, "9000000009")
    assert (await api_client.get("/api/requests?view=all_pending", headers=up)).status_code == 403
    assert (await api_client.get("/api/requests/staff-options", headers=up)).status_code == 403
    assert (await api_client.get("/api/customers", headers=up)).status_code == 403


async def test_search_and_pagination_cover_full_history(api_client, isolated_db, seeded_users, login_helper):
    db = isolated_db["db"]
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    rows = []
    for i in range(130):
        ts = old if i < 5 else (datetime.now(timezone.utc) - timedelta(minutes=i)).isoformat()
        rows.append({"id": f"legacy{i:03d}", "request_type": "callback", "user_id": "u_cust2", "user_name": "Customer Two", "user_phone": "9000000005",
                     "status": "pending", "created_at": ts, "notes": "old one" if i < 5 else "recent"})
    await db.requests.insert_many(rows)
    admin = await auth(login_helper, "9999813334")
    page1 = await api_client.get("/api/requests?view=all_pending&limit=100", headers=admin)
    page2 = await api_client.get("/api/requests?view=all_pending&limit=100&page=2", headers=admin)
    assert page1.json()["total"] == 130 and page1.json()["pages"] == 2 and len(page2.json()["requests"]) == 30
    seen = [q["id"] for q in page1.json()["requests"]] + [q["id"] for q in page2.json()["requests"]]
    assert len(set(seen)) == 130
    # 400-day-old rows are still searchable (no implicit window), legacy rows default to head=new
    found = await api_client.get("/api/requests?search=old%20one", headers=admin)
    assert found.json()["total"] == 5 and all(q["head"] == "new" for q in found.json()["requests"])
