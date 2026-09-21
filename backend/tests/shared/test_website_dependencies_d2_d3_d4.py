"""Website dependencies D2/D3/D4 ported from YashTradeWeb tests/shared_v1/test_bff_followup_core_regressions.py.

The website keeps three strict XFAIL cases against app pin 6a6cddd. These tests assert the DESIRED
behaviour directly against the canonical app and must pass; they use only the isolated synthetic
database and intercepted SMS transport.
"""
from datetime import datetime, timedelta, timezone

import pytest

from httpx import ASGITransport, AsyncClient

import server

pytestmark = pytest.mark.asyncio
KEY = {"X-Integration-Key": "integration-key-1234567890-abcdef"}


def bearer(session):
    return {"Authorization": f"Bearer {session['token']}"}


# ----------------------------------------------------------------------------- D2 -----
async def test_d2_static_customer_search_reaches_billing_handler_before_dynamic_route(api_client, login_helper, seeded_users):
    billing = await login_helper("9000000003")
    assert billing["user"]["role"] == "billing_executive"
    res = await api_client.get("/api/customers/search?q=Customer", headers=bearer(billing))
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["customers"], list) and body["limit"] == 20
    names = {row["name"] for row in body["customers"]}
    assert {"Customer One", "Customer Two"} <= names
    # Lookup envelope only exposes canonical public fields, never raw documents.
    assert all("session_version" not in row and "identity_events" not in row for row in body["customers"])
    assert all(row["role"] == "customer" for row in body["customers"])


async def test_d2_search_role_scope_and_directory_protection(api_client, login_helper, seeded_users):
    admin = await login_helper("9000000000")
    res = await api_client.get("/api/customers/search?q=90000000", headers=bearer(admin))
    assert res.status_code == 200 and len(res.json()["customers"]) >= 2
    # Short/blank terms never enumerate the directory; deleted customers are excluded.
    short = await api_client.get("/api/customers/search?q=9", headers=bearer(admin))
    assert short.status_code == 200 and short.json() == {"customers": [], "query": "9", "limit": 20, "minimum_length": 2}
    # Inactive customers are still findable (they are not deleted); deleted ones are not.
    tele = await login_helper("9000000001")
    assert (await api_client.get("/api/customers/search?q=Customer", headers=bearer(tele))).status_code == 403
    cust = await login_helper("9000000004")
    assert (await api_client.get("/api/customers/search?q=Customer", headers=bearer(cust))).status_code == 403
    assert (await api_client.get("/api/customers/search?q=Customer")).status_code == 401


async def test_d2_dynamic_customer_id_route_still_resolves(api_client, login_helper, seeded_users):
    admin = await login_helper("9000000000")
    detail = await api_client.get("/api/customers/u_cust1", headers=bearer(admin))
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == "u_cust1" and detail.json()["detail_limit"] == 100
    assert detail.json()["complete_history"].startswith("/api/requests?customer_id=u_cust1")
    # Unknown canonical IDs are 404 CUSTOMER_NOT_FOUND on the dynamic route too (never a phone-parse 422).
    missing = await api_client.get("/api/customers/u_does_not_exist", headers=bearer(admin))
    assert missing.status_code == 404 and missing.json()["code"] == "CUSTOMER_NOT_FOUND"
    # Billing is admin-only for the dynamic profile route, as before.
    billing = await login_helper("9000000003")
    assert (await api_client.get("/api/customers/u_cust1", headers=bearer(billing))).status_code == 403
    # The legacy server.py handler is no longer registered twice.
    assert [r.path for r in server.app.routes if getattr(r, "path", "") == "/api/customers/search"].count("/api/customers/search") == 1


# ----------------------------------------------------------------------------- D3 -----
async def seed_history(db, owner, count, name, phone, start_days=30):
    rows = []
    base = datetime.now(timezone.utc)
    for i in range(count):
        created = (base - timedelta(days=start_days) + timedelta(minutes=i)).isoformat()
        rows.append({"_id": f"{owner}-{i:04d}", "id": f"{owner}-{i:04d}", "request_type": ["callback", "ask_price", "video_call"][i % 3],
                     "status": ["pending", "resolved", "cancelled", "in_progress"][i % 4], "user_id": owner, "user_name": name,
                     "user_phone": phone, "user_city": "Delhi", "shop_name": "Shop", "assignee_id": "", "assigned_to": "",
                     "created_at": created, "updated_at": created, "pending_since": created, "version": 0, "events": []})
    await db.requests.insert_many(rows)


async def test_d3_customer_id_filter_exact_paginated_history_over_100_records(api_client, login_helper, seeded_users, isolated_db):
    db = isolated_db["db"]
    # Customer One has 130 legacy user_id-backed rows; Customer Two has 40 rows that carry Customer One's
    # OLD name and phone snapshot (a name/phone change scenario). Phone search would mix them; ID must not.
    await seed_history(db, "u_cust1", 130, "Customer One", "9000000004")
    await seed_history(db, "u_cust2", 40, "Customer One", "9000000004", start_days=10)
    admin = await login_helper("9000000000")
    page1 = await api_client.get("/api/requests?customer_id=u_cust1&page=1&limit=100&status=all&sort=newest", headers=bearer(admin))
    assert page1.status_code == 200, page1.text
    body = page1.json()
    assert body["total"] == 130 and body["pages"] == 2 and len(body["requests"]) == 100 and body["customer_id"] == "u_cust1"
    page2 = await api_client.get("/api/requests?customer_id=u_cust1&page=2&limit=100&status=all&sort=newest", headers=bearer(admin))
    assert page2.status_code == 200 and len(page2.json()["requests"]) == 30
    ids = {r["id"] for r in body["requests"]} | {r["id"] for r in page2.json()["requests"]}
    assert len(ids) == 130 and all(i.startswith("u_cust1-") for i in ids)
    assert all(r["customer_id"] == "u_cust1" for r in body["requests"] + page2.json()["requests"])
    # Text search follows the LIVE identity (enrichment) and mixes both customers; the ID filter does not.
    by_text = await api_client.get("/api/requests?search=Customer&status=all&limit=100", headers=bearer(admin))
    assert by_text.json()["total"] == 170
    other = await api_client.get("/api/requests?customer_id=u_cust2&status=all&limit=100", headers=bearer(admin))
    assert other.json()["total"] == 40
    # Existing filters/totals compose with the ID scope.
    resolved = await api_client.get("/api/requests?customer_id=u_cust1&status=resolved&limit=100", headers=bearer(admin))
    assert resolved.status_code == 200 and resolved.json()["total"] == len([i for i in range(130) if i % 4 == 1])
    typed = await api_client.get("/api/requests?customer_id=u_cust1&request_type=callback&status=all&limit=100", headers=bearer(admin))
    assert typed.json()["total"] == len([i for i in range(130) if i % 3 == 0])


async def test_d3_customer_id_validation_missing_ids_role_scope_and_deleted_history(api_client, login_helper, seeded_users, isolated_db):
    admin = await login_helper("9000000000")
    bad = await api_client.get("/api/requests?customer_id=%24where%3A1", headers=bearer(admin))
    assert bad.status_code == 422 and bad.json()["code"] == "INVALID_FILTER"
    too_long = await api_client.get("/api/requests?customer_id=" + "a" * 65, headers=bearer(admin))
    assert too_long.status_code == 422 and too_long.json()["code"] == "INVALID_FILTER"
    missing = await api_client.get("/api/requests?customer_id=u_nobody", headers=bearer(admin))
    assert missing.status_code == 404 and missing.json()["code"] == "CUSTOMER_NOT_FOUND"
    empty = await api_client.get("/api/requests?customer_id=u_cust2&status=all", headers=bearer(admin))
    assert empty.status_code == 200 and empty.json()["total"] == 0 and empty.json()["requests"] == []
    # Telecaller and billing keep their existing scopes; customers are denied entirely.
    await seed_history(isolated_db["db"], "u_cust1", 6, "Customer One", "9000000004")
    tele = await login_helper("9000000001")
    tele_view = await api_client.get("/api/requests?customer_id=u_cust1&status=all", headers=bearer(tele))
    assert tele_view.status_code == 200 and tele_view.json()["total"] == 6
    billing = await login_helper("9000000003")
    billing_view = await api_client.get("/api/requests?customer_id=u_cust1", headers=bearer(billing))
    assert billing_view.status_code == 200 and billing_view.json()["total"] == 3  # open backlog default preserved
    cust = await login_helper("9000000004")
    assert (await api_client.get("/api/requests?customer_id=u_cust1", headers=bearer(cust))).status_code == 403
    # Deleted customer: the tombstone keeps the canonical ID, so anonymized history stays reachable.
    await isolated_db["db"].otp_challenges.delete_many({"phone": "9000000004"})  # lift the 60s resend cooldown from login
    send = await api_client.post("/api/auth/delete-account/request", headers=bearer(cust))
    assert send.status_code == 200
    otp = isolated_db["sent_otps"][("9000000004", "account_deletion")]
    confirm = await api_client.post("/api/auth/delete-account/confirm", json={"otp": otp, "challenge_id": send.json()["challenge_id"]}, headers=bearer(cust))
    assert confirm.status_code == 200 and confirm.json()["deleted"] is True
    after = await api_client.get("/api/requests?customer_id=u_cust1&status=all", headers=bearer(admin))
    assert after.status_code == 200 and after.json()["total"] == 6
    assert all(r["user_phone"] != "9000000004" and r["customer_name"] == "Deleted customer" for r in after.json()["requests"])


# ----------------------------------------------------------------------------- D4 -----
def outbox_rows(count, acked_first=0):
    now = datetime.now(timezone.utc)
    return [{"id": f"ev-{i:03d}", "type": "account_erased", "user_id": f"u_del_{i:03d}", "status": "pending",
             "created_at": (now + timedelta(seconds=i)).isoformat(), "required_acknowledgements": ["website", "sms_provider", "ai_provider"],
             "acknowledged": ["website"] if i <= acked_first else []} for i in range(1, count + 1)]


async def test_d4_101st_event_visible_after_first_100_website_acks(api_client, isolated_db):
    await isolated_db["db"].integration_outbox.insert_many(outbox_rows(101, acked_first=100))
    res = await api_client.get("/api/integrations/deletions", headers=KEY)
    assert res.status_code == 200, res.text
    body = res.json()
    ids = {e["id"] for e in body["events"]}
    assert ids == {"ev-101"} and body["consumer"] == "website" and body["has_more"] is False and body["remaining_for_consumer"] == 1
    # Other providers' pending states are untouched: the acknowledged rows are still pending globally.
    assert await isolated_db["db"].integration_outbox.count_documents({"status": "pending"}) == 101


async def test_d4_stable_cursor_pagination_without_gaps_or_duplicates(api_client, isolated_db):
    await isolated_db["db"].integration_outbox.insert_many(outbox_rows(120))
    seen, cursor, pages = [], "", 0
    while True:
        res = await api_client.get(f"/api/integrations/deletions?limit=50{'&after=' + cursor if cursor else ''}", headers=KEY)
        assert res.status_code == 200, res.text
        body = res.json()
        seen += [e["id"] for e in body["events"]]
        pages += 1
        if not body["has_more"]:
            assert body["next_cursor"] is None
            break
        cursor = body["next_cursor"]
    assert pages == 3 and len(seen) == 120 and len(set(seen)) == 120 and seen == sorted(seen)
    assert (await api_client.get("/api/integrations/deletions?after=not-a-cursor", headers=KEY)).status_code == 422
    assert (await api_client.get("/api/integrations/deletions?limit=0", headers=KEY)).status_code == 422
    assert (await api_client.get("/api/integrations/deletions?limit=501", headers=KEY)).status_code == 422


async def test_d4_idempotent_consumer_specific_ack_retry_and_authorization(api_client, isolated_db):
    db = isolated_db["db"]
    await db.integration_outbox.insert_many(outbox_rows(3))
    first = await api_client.post("/api/integrations/deletions/ev-001/ack", headers=KEY)
    assert first.status_code == 200 and first.json()["acknowledged_by"] == ["website"] and first.json()["all_acknowledged"] is False
    # Interrupted consumer retries the same acknowledgement: identical result, no duplicate entries.
    again = await api_client.post("/api/integrations/deletions/ev-001/ack", headers=KEY)
    assert again.status_code == 200 and again.json()["acknowledged_by"] == ["website"]
    doc = await db.integration_outbox.find_one({"id": "ev-001"}, {"_id": 0})
    assert doc["acknowledged"] == ["website"] and doc["status"] == "pending" and "website" in doc["acknowledged_at"]
    listed = await api_client.get("/api/integrations/deletions", headers=KEY)
    assert {e["id"] for e in listed.json()["events"]} == {"ev-002", "ev-003"}
    assert (await api_client.post("/api/integrations/deletions/ev-999/ack", headers=KEY)).status_code == 404
    # Global completion only when EVERY required consumer has acknowledged (other providers record separately).
    await db.integration_outbox.update_one({"id": "ev-002"}, {"$addToSet": {"acknowledged": {"$each": ["sms_provider", "ai_provider"]}}})
    complete = await api_client.post("/api/integrations/deletions/ev-002/ack", headers=KEY)
    assert complete.json()["all_acknowledged"] is True
    assert (await db.integration_outbox.find_one({"id": "ev-002"}))["status"] == "acknowledged"
    # Missing/invalid credentials are refused; the consumer identity cannot be chosen by the client.
    assert (await api_client.get("/api/integrations/deletions")).status_code == 401
    assert (await api_client.get("/api/integrations/deletions", headers={"X-Integration-Key": "wrong-key-1234567890-abcdefghij"})).status_code == 401
    assert (await api_client.post("/api/integrations/deletions/ev-003/ack", headers={"X-Integration-Key": "x"})).status_code == 401
    spoof = await api_client.get("/api/integrations/deletions?consumer=sms_provider", headers=KEY)
    assert spoof.status_code == 200 and spoof.json()["consumer"] == "website"


async def test_d4_deleted_customer_is_not_resurrected_by_enrollment_after_ack(api_client, login_helper, seeded_users, isolated_db):
    cust = await login_helper("9000000005")
    await isolated_db["db"].otp_challenges.delete_many({"phone": "9000000005"})  # lift the 60s resend cooldown from login
    send = await api_client.post("/api/auth/delete-account/request", headers=bearer(cust))
    otp = isolated_db["sent_otps"][("9000000005", "account_deletion")]
    confirm = await api_client.post("/api/auth/delete-account/confirm", json={"otp": otp, "challenge_id": send.json()["challenge_id"]}, headers=bearer(cust))
    assert confirm.status_code == 200
    ref = confirm.json()["reference"]
    outbox = await api_client.get("/api/integrations/deletions", headers=KEY)
    assert ref in {e["id"] for e in outbox.json()["events"]}
    assert (await api_client.post(f"/api/integrations/deletions/{ref}/ack", headers=KEY)).status_code == 200
    assert ref not in {e["id"] for e in (await api_client.get("/api/integrations/deletions", headers=KEY)).json()["events"]}
    # A queued website retry that holds a grant issued BEFORE the deletion cannot resurrect the account ...
    from shared import core as c
    await isolated_db["db"].auth_grants.insert_one({"hash": c.digest("pre-deletion-grant"), "phone": "9000000005", "purpose": "enrollment", "subject": "u_cust2",
        "used": False, "issued_at": c.now() - c.timedelta(minutes=4), "expires_at": c.now() + c.timedelta(minutes=1)})
    blocked = await api_client.post("/api/integrations/enrollments", headers=KEY, json={"phone": "9000000005", "name": "Ghost", "shop_name": "Ghost",
        "location": "Ghost", "verification_grant": "pre-deletion-grant", "idempotency_key": "idem-ghost-01", "consent_version": "v1",
        "consent_terms": True, "consent_privacy": True})
    assert blocked.status_code == 409 and blocked.json()["code"] == "DELETED_IDENTITY"
    assert (await isolated_db["db"].users.find_one({"id": "u_cust2"}))["account_status"] == "deleted"
    # ... while a FRESH verification after the deletion may start a new registration (new identity, history erased).
    await isolated_db["db"].otp_challenges.delete_many({"phone": "9000000005"})
    fresh = await api_client.post("/api/auth/send-otp", json={"phone": "9000000005", "purpose": "enrollment", "channel": "portal"}, headers=KEY)
    assert fresh.status_code == 200 and fresh.json()["account_exists"] is False
