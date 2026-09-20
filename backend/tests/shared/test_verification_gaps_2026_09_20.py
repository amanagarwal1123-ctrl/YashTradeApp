"""Verification gaps closed on 20 Sep 2026 (brief R09-D, R13-A, R15-B):
- push receipts: Expo receipts are fetched after the provider delay, DeviceNotRegistered receipts disable exactly that
  device, a receipts-transport failure leaves the batch for the next pass (never marked checked);
- deletion integrity: deleting the completing telecaller keeps the immutable completion attribution and the admin
  report; deleting a customer anonymizes (never deletes) their queries and leaves products / completion ledger intact.
"""
from datetime import timedelta

import pytest

from shared import core as c, notifications, queries

pytestmark = pytest.mark.asyncio


async def auth(login_helper, phone):
    body = await login_helper(phone)
    return {"Authorization": f"Bearer {body['token']}"}


async def test_receipts_disable_unregistered_devices_and_retry_on_transport_failure(api_client, isolated_db, seeded_users, login_helper, monkeypatch):
    db = isolated_db["db"]
    sent = []

    async def fake_send(messages):
        sent.append(list(messages))
        return [{"status": "ok", "id": f"ticket-{i}"} for i, _ in enumerate(messages)]

    calls = {"receipts": 0}

    async def failing_receipts(ids):
        calls["receipts"] += 1
        raise RuntimeError("receipts endpoint down")

    monkeypatch.setattr(notifications, "transport", fake_send)
    monkeypatch.setattr(notifications, "receipts_transport", failing_receipts)
    h1, h2 = await auth(login_helper, "9000000004"), await auth(login_helper, "9000000005")
    for h, tok in ((h1, "ExponentPushToken[rcpt1aaaaaaaaaaa]"), (h2, "ExponentPushToken[rcpt2bbbbbbbbbbb]")):
        assert (await api_client.post("/api/notifications/devices", json={"token": tok, "platform": "android"}, headers=h)).status_code == 200
    await notifications.fan_out("receipts:1", "operational", ["u_cust1", "u_cust2"], "Hello", "receipt test", "/notifications")
    await notifications.tick()
    job = await db.notification_outbox.find_one({"key": "receipts:1:0"}, {"_id": 0})
    assert job["status"] == "sent" and len(job["tickets"]) == 2 and job.get("receipts_checked_at") is None
    # too early: Expo asks for a delay before receipts are fetched -> nothing is asked yet
    await notifications.check_receipts()
    assert calls["receipts"] == 0
    # after the delay a transport failure leaves the job unchecked (retried on the next pass), never silently "checked"
    await db.notification_outbox.update_one({"key": "receipts:1:0"}, {"$set": {"sent_at": (c.now() - timedelta(minutes=notifications.RECEIPT_DELAY_MINUTES + 1)).isoformat()}})
    await notifications.check_receipts()
    assert calls["receipts"] == 1
    assert (await db.notification_outbox.find_one({"key": "receipts:1:0"})).get("receipts_checked_at") is None

    async def receipts(ids):
        return {"ticket-0": {"status": "ok"}, "ticket-1": {"status": "error", "message": "gone", "details": {"error": "DeviceNotRegistered"}}}
    monkeypatch.setattr(notifications, "receipts_transport", receipts)
    await notifications.check_receipts()
    job = await db.notification_outbox.find_one({"key": "receipts:1:0"}, {"_id": 0})
    assert job["receipts_checked_at"] and job["receipts"] == {"ok": 1, "error": 1, "invalid_tokens": 1}
    dead = await db.push_devices.find_one({"token": "ExponentPushToken[rcpt2bbbbbbbbbbb]"}, {"_id": 0})
    alive = await db.push_devices.find_one({"token": "ExponentPushToken[rcpt1aaaaaaaaaaa]"}, {"_id": 0})
    assert dead["enabled"] is False and dead["unlink_reason"] == "DeviceNotRegistered" and alive["enabled"] is True
    # a second pass does not re-check the same batch; the disabled device is excluded from the next fan-out
    await notifications.check_receipts()
    await notifications.fan_out("receipts:2", "operational", ["u_cust1", "u_cust2"], "Again", "second", "/notifications")
    await notifications.tick()
    assert [m["to"] for m in sent[-1]] == ["ExponentPushToken[rcpt1aaaaaaaaaaa]"]


async def test_deleting_staff_and_customers_keeps_completion_attribution_and_business_records(api_client, isolated_db, seeded_users, login_helper):
    db = isolated_db["db"]
    admin, t1, cust = await auth(login_helper, "9999813334"), await auth(login_helper, "9000000001"), await auth(login_helper, "9000000004")
    await db.products.insert_one({"id": "p_keep", "title": "Bangle", "metal_type": "silver", "visibility": "visible", "is_deleted": False, "created_at": c.stamp()})
    done = (await api_client.post("/api/requests", json={"request_type": "ask_price", "product_ids": ["p_keep"], "notes": "price please"}, headers=cust)).json()
    pending = (await api_client.post("/api/requests", json={"request_type": "callback", "notes": "call me"}, headers=cust)).json()
    assert (await api_client.post(f"/api/requests/{done['id']}/claim", headers=t1)).status_code == 200
    assert (await api_client.post(f"/api/requests/{done['id']}/complete", json={"outcome": "converted"}, headers=t1)).status_code == 200
    assert (await api_client.post(f"/api/requests/{pending['id']}/claim", headers=t1)).status_code == 200
    today = c.now().astimezone(queries.IST).date().isoformat()
    before = (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)).json()
    assert before["total_completed"] == 1 and before["telecallers"][0]["id"] == "u_tele1"

    # 1) delete the telecaller: open query released, completed query and its ledger row keep the attribution
    r = await api_client.post("/api/integrations/staff/u_tele1/delete", json={"reason": "left the company", "confirm_user_id": "u_tele1", "confirm_phone_last4": "0001"}, headers=admin)
    assert r.status_code == 200 and r.json()["deleted"] is True and r.json()["queries_released"] == 1
    ledger = await db.request_completions.find_one({"request_id": done["id"]}, {"_id": 0})
    assert ledger["actor_id"] == "u_tele1" and ledger["actor_name"] == "Tele One" and ledger["superseded_at"] is None
    after = (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)).json()
    assert after["total_completed"] == 1 and after["telecallers"][0]["id"] == "u_tele1" and after["telecallers"][0]["account_status"] == "deleted"
    assert (await db.requests.find_one({"id": done["id"]}))["status"] == "resolved"
    released = await db.requests.find_one({"id": pending["id"]}, {"_id": 0})
    assert released["status"] == "pending" and released["assignee_id"] == "" and released["events"][-1]["type"] == "release"
    assert (await db.users.find_one({"id": "u_tele1"}))["account_status"] == "deleted"
    assert await db.session_families.count_documents({"user_id": "u_tele1", "revoked": False}) == 0
    assert (await api_client.get("/api/auth/me", headers=t1)).status_code == 401

    # 2) delete the customer: queries are anonymized, never removed; products and the completion ledger untouched
    await api_client.post("/api/wishlist/p_keep", headers=cust)
    r = await api_client.post("/api/customers/u_cust1/delete", json={"reason": "customer asked", "confirm_user_id": "u_cust1", "confirm_phone_last4": "0004"}, headers=admin)
    assert r.status_code == 200, r.text
    assert await db.requests.count_documents({"user_id": "u_cust1"}) == 2
    for doc in await db.requests.find({"user_id": "u_cust1"}, {"_id": 0}).to_list(None):
        assert doc["anonymized"] is True and doc["user_name"] == "Deleted customer" and doc["notes"] == "" and doc.get("user_phone", "") == ""
        assert "customer_phone" not in doc and "customer_snapshot" in doc and doc["customer_snapshot"] == {}
        assert all("notes" not in e and "actor_name" not in e for e in doc["events"])
    assert (await db.requests.find_one({"id": done["id"]}))["status"] == "resolved" and (await db.requests.find_one({"id": done["id"]}))["product_ids"] == ["p_keep"]
    assert await db.products.count_documents({"id": "p_keep", "is_deleted": {"$ne": True}}) == 1
    assert await db.wishlists.count_documents({"user_id": "u_cust1"}) == 0
    assert await db.request_completions.count_documents({"request_id": done["id"]}) == 1
    assert (await api_client.get(f"/api/requests/reports/completions?date={today}", headers=admin)).json()["total_completed"] == 1
    tomb = await db.users.find_one({"id": "u_cust1"}, {"_id": 0})
    assert tomb["account_status"] == "deleted" and tomb["phone"] == "deleted:u_cust1" and tomb["name"] == "Deleted customer"
    assert (await api_client.get("/api/auth/me", headers=cust)).status_code == 401
    # the staff view of the anonymized query shows no personal data and does not crash
    t2 = await auth(login_helper, "9000000002")
    detail = await api_client.get(f"/api/requests/{done['id']}", headers=t2)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["customer_deleted"] is True and body.get("customer_phone", "") in ("", None) and body["customer_name"] == "Deleted customer"
    assert body["contact"] == {"tel": "", "whatsapp": ""} and body["customer_phone_display"] == ""
    listed = (await api_client.get("/api/requests?view=all_pending&search=deleted", headers=t2)).json()
    assert all(r.get("customer_phone", "") in ("", None) for r in listed["requests"])
