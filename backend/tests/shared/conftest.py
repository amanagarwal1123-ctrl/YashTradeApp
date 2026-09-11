import io
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")

import server
from shared import core as c


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


@pytest_asyncio.fixture(loop_scope="function")
async def isolated_db(monkeypatch):
    """Isolated synthetic Mongo database for shared canonical flows."""
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        pytest.skip("MONGO_URL missing; cannot run isolated shared tests")

    client = AsyncIOMotorClient(mongo_url, maxPoolSize=10, minPoolSize=2)
    db_name = f"shared_test_{uuid.uuid4().hex[:10]}"
    db = client[db_name]
    await client.drop_database(db_name)

    sent_otps: dict[tuple[str, str], str] = {}
    object_store: dict[str, tuple[bytes, str]] = {}

    async def fake_sms(phone: str, otp: str, purpose: str):
        sent_otps[(phone, purpose)] = otp

    def fake_put(path: str, data: bytes, content_type: str):
        object_store[path] = (bytes(data), content_type)
        return {"path": path}

    def fake_get(path: str):
        if path not in object_store:
            raise FileNotFoundError(path)
        return object_store[path]

    monkeypatch.setenv("ENROLLMENT_INTEGRATION_KEY", "integration-key-1234567890-abcdef")
    monkeypatch.setenv("STAFF_SERVICE_KEY", "staff-service-key-1234567890-abcdef")

    c.configure(db, fake_sms, fake_put, fake_get)
    monkeypatch.setattr(server, "db", db, raising=False)
    monkeypatch.setattr(c, "db", db, raising=False)
    monkeypatch.setattr(c, "dispatch_sms", fake_sms, raising=False)
    monkeypatch.setattr(c, "put_object", fake_put, raising=False)
    monkeypatch.setattr(c, "get_object", fake_get, raising=False)

    await c.ensure_indexes()
    yield {
        "db": db,
        "sent_otps": sent_otps,
        "object_store": object_store,
    }

    await client.drop_database(db_name)
    client.close()


@pytest_asyncio.fixture
async def api_client(isolated_db):
    """ASGI API client bound to the patched app/db for shared module routes."""
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def seeded_users(isolated_db):
    """Synthetic users for auth, roles, and request workflows."""
    db = isolated_db["db"]
    now = _utc_now()
    users = [
        {
            "id": "u_admin",
            "phone": "9999813334",
            "phone_normalized": "9999813334",
            "name": "Owner Admin",
            "role": "admin",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "HQ",
            "location": "Delhi",
        },
        {
            "id": "u_tele1",
            "phone": "9000000001",
            "phone_normalized": "9000000001",
            "name": "Tele One",
            "role": "telecaller",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "TC",
            "location": "Ludhiana",
        },
        {
            "id": "u_tele2",
            "phone": "9000000002",
            "phone_normalized": "9000000002",
            "name": "Tele Two",
            "role": "telecaller",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "TC2",
            "location": "Amritsar",
        },
        {
            "id": "u_bill",
            "phone": "9000000003",
            "phone_normalized": "9000000003",
            "name": "Billing Exec",
            "role": "billing_executive",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "Billing",
            "location": "Jaipur",
        },
        {
            "id": "u_cust1",
            "phone": "9000000004",
            "phone_normalized": "9000000004",
            "name": "Customer One",
            "role": "customer",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "Shop One",
            "location": "Delhi",
        },
        {
            "id": "u_cust2",
            "phone": "9000000005",
            "phone_normalized": "9000000005",
            "name": "Customer Two",
            "role": "customer",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "Shop Two",
            "location": "Mumbai",
        },
        {
            "id": "u_inactive",
            "phone": "9000000006",
            "phone_normalized": "9000000006",
            "name": "Inactive User",
            "role": "customer",
            "account_status": "inactive",
            "status": "inactive",
            "session_version": 0,
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "Dormant",
            "location": "Noida",
        },
    ]
    await db.users.insert_many(users)
    await db.batches.insert_one({"id": "b1", "status": "visible", "name": "Batch 1", "created_at": now})
    await db.rates_current.insert_one({
        "_id": "canonical",
        "version": 0,
        "silver_physical_rate": 100.0,
        "silver_mcx_rate": 99.0,
        "silver_dollar_rate": 1.0,
        "gold_physical_rate": 5000.0,
        "gold_mcx_rate": 4900.0,
        "gold_dollar_rate": 2.0,
        "created_at": now,
        "updated_at": now,
    })
    return {u["id"]: u for u in users}


@pytest_asyncio.fixture
async def login_helper(api_client, isolated_db, seeded_users):
    """Helper to complete OTP login using intercepted transport OTP values."""

    async def _login(phone: str, purpose: str = "login", channel: str = "mobile", headers: dict | None = None):
        payload = {"phone": phone, "purpose": purpose, "channel": channel}
        send = await api_client.post("/api/auth/send-otp", json=payload, headers=headers)
        assert send.status_code == 200, send.text
        otp = isolated_db["sent_otps"].get((phone, purpose))
        assert otp, f"No intercepted OTP for {phone}/{purpose}"
        verify = await api_client.post(
            "/api/auth/verify-otp",
            json={**payload, "otp": otp, "challenge_id": send.json().get("challenge_id")},
            headers=headers,
        )
        assert verify.status_code == 200, verify.text
        return verify.json()

    return _login
