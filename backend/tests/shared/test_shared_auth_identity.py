"""Shared canonical auth tests: OTP challenge, grant, refresh, and session rules."""

from datetime import datetime, timedelta, timezone

import pytest


def _integration_headers():
    return {"X-Integration-Key": "integration-key-1234567890-abcdef"}


@pytest.mark.asyncio
async def test_otp_no_fixed_code_and_single_use(api_client, isolated_db, seeded_users, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_INTEGRATION_KEY", "integration-key-1234567890-abcdef")
    monkeypatch.setenv("STAFF_SERVICE_KEY", "staff-service-key-1234567890-abcdef")

    # Start login OTP
    sent = await api_client.post("/api/auth/send-otp", json={"phone": "9000000004", "purpose": "login", "channel": "mobile"})
    assert sent.status_code == 200, sent.text
    challenge_id = sent.json()["challenge_id"]
    otp = isolated_db["sent_otps"][("9000000004", "login")]

    # Fixed OTP must not pass
    wrong = await api_client.post(
        "/api/auth/verify-otp",
        json={"phone": "9000000004", "purpose": "login", "channel": "mobile", "otp": "1234", "challenge_id": challenge_id},
    )
    assert wrong.status_code == 400

    ok = await api_client.post(
        "/api/auth/verify-otp",
        json={"phone": "9000000004", "purpose": "login", "channel": "mobile", "otp": otp, "challenge_id": challenge_id},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["id"] == "u_cust1"

    # Single-use challenge
    reused = await api_client.post(
        "/api/auth/verify-otp",
        json={"phone": "9000000004", "purpose": "login", "channel": "mobile", "otp": otp, "challenge_id": challenge_id},
    )
    assert reused.status_code == 400


@pytest.mark.asyncio
async def test_otp_cooldown_and_expiry(api_client, isolated_db, seeded_users):
    first = await api_client.post("/api/auth/send-otp", json={"phone": "9000000005", "purpose": "login", "channel": "mobile"})
    assert first.status_code == 200
    second = await api_client.post("/api/auth/send-otp", json={"phone": "9000000005", "purpose": "login", "channel": "mobile"})
    assert second.status_code == 429

    challenge_id = first.json()["challenge_id"]
    await isolated_db["db"].otp_challenges.update_one(
        {"id": challenge_id},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )
    otp = isolated_db["sent_otps"][("9000000005", "login")]
    expired = await api_client.post(
        "/api/auth/verify-otp",
        json={"phone": "9000000005", "purpose": "login", "channel": "mobile", "otp": otp, "challenge_id": challenge_id},
    )
    assert expired.status_code == 400


@pytest.mark.asyncio
async def test_inactive_user_cannot_start_login(api_client, seeded_users):
    sent = await api_client.post("/api/auth/send-otp", json={"phone": "9000000006", "purpose": "login", "channel": "mobile"})
    assert sent.status_code == 403


@pytest.mark.asyncio
async def test_refresh_rotation_and_reuse_revokes_family(api_client, login_helper):
    auth = await login_helper("9000000004")
    old_refresh = auth["refresh_token"]

    rotated = await api_client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert rotated.status_code == 200, rotated.text
    new_token = rotated.json()["token"]

    # Reusing old refresh should fail and revoke family
    reused = await api_client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert reused.status_code == 401

    # Access token from revoked family must fail
    me = await api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_enrollment_grant_flow_and_staff_impersonation_block(api_client, isolated_db, seeded_users, monkeypatch):
    monkeypatch.setenv("ENROLLMENT_INTEGRATION_KEY", "integration-key-1234567890-abcdef")

    # Enrollment OTP for a new customer number, grant issuance
    sent = await api_client.post(
        "/api/auth/send-otp",
        json={"phone": "9000000010", "purpose": "enrollment", "channel": "mobile"},
        headers=_integration_headers(),
    )
    assert sent.status_code == 200, sent.text
    otp = isolated_db["sent_otps"][("9000000010", "enrollment")]
    grant_resp = await api_client.post(
        "/api/auth/verify-otp",
        json={"phone": "9000000010", "purpose": "enrollment", "channel": "mobile", "otp": otp, "challenge_id": sent.json()["challenge_id"]},
        headers=_integration_headers(),
    )
    assert grant_resp.status_code == 200, grant_resp.text
    grant = grant_resp.json()["verification_grant"]

    enroll = await api_client.post(
        "/api/integrations/enrollments",
        headers=_integration_headers(),
        json={
            "phone": "9000000010",
            "name": "TEST New",
            "shop_name": "TEST Shop",
            "location": "Pune",
            "city": "Pune",
            "verification_grant": grant,
            "idempotency_key": "idem-12345678",
            "consent_version": "v1",
            "consent_terms": True,
            "consent_privacy": True,
        },
    )
    assert enroll.status_code == 200, enroll.text
    customer = enroll.json()["customer"]
    assert customer["phone"] == "9000000010"
    assert customer["has_logged_in"] is False

    # Enrollment grant must not impersonate staff identity
    staff_send = await api_client.post(
        "/api/auth/send-otp",
        json={"phone": "9000000001", "purpose": "enrollment", "channel": "mobile"},
        headers=_integration_headers(),
    )
    assert staff_send.status_code == 200
    staff_otp = isolated_db["sent_otps"][("9000000001", "enrollment")]
    staff_grant = await api_client.post(
        "/api/auth/verify-otp",
        json={"phone": "9000000001", "purpose": "enrollment", "channel": "mobile", "otp": staff_otp, "challenge_id": staff_send.json()["challenge_id"]},
        headers=_integration_headers(),
    )
    assert staff_grant.status_code == 200

    blocked = await api_client.post(
        "/api/integrations/enrollments",
        headers=_integration_headers(),
        json={
            "phone": "9000000001",
            "name": "Should Fail",
            "shop_name": "X",
            "location": "X",
            "city": "X",
            "verification_grant": staff_grant.json()["verification_grant"],
            "idempotency_key": "idem-87654321",
            "consent_version": "v1",
            "consent_terms": True,
            "consent_privacy": True,
        },
    )
    assert blocked.status_code == 409
