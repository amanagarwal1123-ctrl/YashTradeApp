"""Shared staff, requests ledger, assignment race, metrics, and rates authorization tests."""

from datetime import datetime, timedelta, timezone

import pytest


def _headers(token: str):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_last_admin_guard_blocks_demotion(api_client, login_helper):
    admin = await login_helper("9999813334")
    token = admin["token"]
    res = await api_client.patch("/api/integrations/staff/u_admin", json={"status": "inactive"}, headers=_headers(token))
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_service_key_exchange_requires_same_subject(api_client, login_helper, monkeypatch):
    monkeypatch.setenv("STAFF_SERVICE_KEY", "staff-service-key-1234567890-abcdef")
    tele = await login_helper("9000000001")
    token = tele["token"]

    denied = await api_client.post(
        "/api/integrations/staff/u_tele2/token",
        headers={**_headers(token), "X-Staff-Service-Key": "staff-service-key-1234567890-abcdef"},
    )
    assert denied.status_code == 403

    ok = await api_client.post(
        "/api/integrations/staff/u_tele1/token",
        headers={**_headers(token), "X-Staff-Service-Key": "staff-service-key-1234567890-abcdef"},
    )
    assert ok.status_code == 200
    assert ok.json().get("token")


@pytest.mark.asyncio
async def test_phone_change_conflict_has_no_partial_update(api_client, isolated_db, login_helper):
    auth = await login_helper("9000000004")
    token = auth["token"]

    req = await api_client.post(
        "/api/auth/phone-change/request",
        json={"new_phone": "9000000005"},
        headers=_headers(token),
    )
    assert req.status_code == 409

    still = await isolated_db["db"].users.find_one({"id": "u_cust1"}, {"_id": 0})
    assert still["phone"] == "9000000004"


@pytest.mark.asyncio
async def test_requests_listing_pagination_and_types_over_200(api_client, isolated_db, login_helper):
    admin = await login_helper("9999813334")
    token = admin["token"]
    now = datetime.now(timezone.utc)
    types = ["video_call", "ask_price", "callback", "similar_products", "hold_item", "quick_reorder", "cart_selection"]
    rows = []
    for i in range(210):
        t = types[i % len(types)]
        created = (now - timedelta(minutes=210 - i)).isoformat()
        rows.append(
            {
                "id": f"r{i:03d}",
                "request_type": t,
                "status": "pending",
                "user_id": "u_cust1",
                "user_name": "Customer One",
                "user_phone": "9000000004",
                "user_city": "Delhi",
                "shop_name": "Shop One",
                "assignee_id": "",
                "assigned_to": "",
                "created_at": created,
                "updated_at": created,
                "pending_since": created,
                "version": 0,
                "events": [{"id": f"e{i}", "type": "creation", "actor_id": "u_cust1", "actor_role": "customer", "timestamp": created, "status": "pending"}],
            }
        )
    await isolated_db["db"].requests.insert_many(rows)

    page2 = await api_client.get("/api/requests?page=2&limit=100&view=all", headers=_headers(token))
    assert page2.status_code == 200, page2.text
    data = page2.json()
    assert data["total"] >= 210
    assert len(data["requests"]) == 100
    assert set(types).issubset(set(data["open_counts_by_type"].keys()))


@pytest.mark.asyncio
async def test_telecaller_claim_race_and_resolver_ownership(api_client, isolated_db, login_helper):
    now = datetime.now(timezone.utc).isoformat()
    await isolated_db["db"].requests.insert_one(
        {
            "id": "race-1",
            "request_type": "callback",
            "status": "pending",
            "user_id": "u_cust1",
            "user_name": "Customer One",
            "user_phone": "9000000004",
            "user_city": "Delhi",
            "shop_name": "Shop One",
            "assignee_id": "",
            "assigned_to": "",
            "created_at": now,
            "updated_at": now,
            "pending_since": now,
            "version": 0,
            "events": [{"id": "e-race", "type": "creation", "actor_id": "u_cust1", "actor_role": "customer", "timestamp": now, "status": "pending"}],
        }
    )

    tele1 = (await login_helper("9000000001"))["token"]
    tele2 = (await login_helper("9000000002"))["token"]
    admin = (await login_helper("9999813334"))["token"]

    c1 = await api_client.post("/api/requests/race-1/claim", headers=_headers(tele1))
    assert c1.status_code == 200
    c2 = await api_client.post("/api/requests/race-1/claim", headers=_headers(tele2))
    assert c2.status_code == 409

    resolved = await api_client.patch(
        "/api/requests/race-1",
        json={"status": "completed", "action": "update", "version": c1.json()["version"]},
        headers=_headers(tele1),
    )
    assert resolved.status_code == 200
    resolver_id = resolved.json().get("resolver_id")
    assert resolver_id == "u_tele1"

    admin_note = await api_client.patch(
        "/api/requests/race-1",
        json={"notes": "admin note", "action": "update", "version": resolved.json()["version"]},
        headers=_headers(admin),
    )
    assert admin_note.status_code == 200
    assert admin_note.json().get("resolver_id") == "u_tele1"

    reopened = await api_client.patch(
        "/api/requests/race-1",
        json={"status": "pending", "action": "reopen", "version": admin_note.json()["version"]},
        headers=_headers(admin),
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_metrics_ist_summary_handles_zero_and_data(api_client, login_helper):
    admin = (await login_helper("9999813334"))["token"]

    empty = await api_client.get("/api/requests/metrics/summary?start=2035-01-01&end=2035-01-01", headers=_headers(admin))
    assert empty.status_code == 200
    assert empty.json()["received_cohort"]["received"] == 0

    today = datetime.now(timezone.utc).astimezone().date().isoformat()
    present = await api_client.get(f"/api/requests/metrics/summary?start={today}&end={today}", headers=_headers(admin))
    assert present.status_code == 200
    assert "telecallers" in present.json()


@pytest.mark.asyncio
async def test_rates_and_rate_slab_role_scope(api_client, login_helper):
    billing = (await login_helper("9000000003"))["token"]
    tele = (await login_helper("9000000001"))["token"]

    latest = await api_client.get("/api/rates/latest")
    assert latest.status_code == 200
    old = latest.json()
    gold_before = old["gold_physical_rate"]

    denied = await api_client.post("/api/rates", json={"version": old["version"], "silver_physical_rate": 123.4}, headers=_headers(tele))
    assert denied.status_code == 403

    ok = await api_client.post("/api/rates", json={"version": old["version"], "silver_physical_rate": 123.4}, headers=_headers(billing))
    assert ok.status_code == 200, ok.text
    assert ok.json()["silver_physical_rate"] == 123.4
    assert ok.json()["gold_physical_rate"] == gold_before

    slab_denied = await api_client.post(
        "/api/rate-list",
        json={"metal_type": "silver", "item_name": "X"},
        headers=_headers(tele),
    )
    assert slab_denied.status_code == 403

    slab_created = await api_client.post(
        "/api/rate-list",
        json={"metal_type": "silver", "item_name": "TEST slab", "purity": "925", "wastage": "2", "labour_kg": "100", "order": 1},
        headers=_headers(billing),
    )
    assert slab_created.status_code == 200
    sid = slab_created.json()["id"]

    slab_updated = await api_client.put(
        f"/api/rate-list/{sid}",
        json={"version": slab_created.json()["version"], "item_name": "TEST slab v2"},
        headers=_headers(billing),
    )
    assert slab_updated.status_code == 200
    assert slab_updated.json()["item_name"] == "TEST slab v2"
