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
async def test_refresh_rotation_race_grace_replay_revocation_and_idle_expiry(api_client, login_helper, monkeypatch):
    """Intended security behaviour of refresh rotation (R01-B):
    1. two CONCURRENT presentations of the same refresh token (duplicate call from one device) -> exactly one rotation
       succeeds, the other gets 409 REFRESH_IN_PROGRESS and NOTHING is revoked (a race is not theft);
    2. presenting an already-rotated token again AFTER the 30 s grace window is replay/theft -> 401 REFRESH_INVALID
       and the whole family (including the freshly issued credentials) is revoked;
    3. a family that is not refreshed for SESSION_IDLE_DAYS expires (documented idle/security expiry), while active
       use keeps sliding it past the old fixed 30-day boundary;
    4. explicit logout revokes the family."""
    import asyncio
    from shared import auth as a
    from shared import core as c

    clock = {"now": datetime.now(timezone.utc)}
    monkeypatch.setattr(c, "now", lambda: clock["now"])
    refresh = lambda token: api_client.post("/api/auth/refresh", json={"refresh_token": token})
    me = lambda token: api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    auth = await login_helper("9000000004")
    original = auth["refresh_token"]

    # 1. legitimate concurrent refresh: one winner, one 409, family alive
    first, second = await asyncio.gather(refresh(original), refresh(original))
    assert sorted([first.status_code, second.status_code]) == [200, 409], (first.text, second.text)
    winner, loser = (first, second) if first.status_code == 200 else (second, first)
    assert loser.json()["code"] == "REFRESH_IN_PROGRESS"
    fresh_token, fresh_refresh = winner.json()["token"], winner.json()["refresh_token"]
    assert (await me(fresh_token)).status_code == 200
    assert winner.json()["session"]["idle_expiry_days"] == a.SESSION_IDLE_DAYS

    # 2. replay of the rotated token outside the grace window is theft: 401 + family revoked
    clock["now"] += timedelta(seconds=a.REFRESH_RACE_SECONDS + 1)
    replay = await refresh(original)
    assert replay.status_code == 401 and replay.json()["code"] == "REFRESH_INVALID", replay.text
    assert (await me(fresh_token)).status_code == 401                      # access token of the revoked family
    revoked = await refresh(fresh_refresh)                                 # even the unused fresh refresh credential
    assert revoked.status_code == 401 and revoked.json()["code"] == "SESSION_REVOKED", revoked.text

    # 3a. idle expiry: no refresh for SESSION_IDLE_DAYS -> the family is gone (401), nothing else is touched
    idle = await login_helper("9000000004")
    clock["now"] += timedelta(days=a.SESSION_IDLE_DAYS, seconds=1)
    expired = await refresh(idle["refresh_token"])
    assert expired.status_code == 401 and expired.json()["code"] == "REFRESH_INVALID", expired.text

    # 3b. active use slides the expiry: three refreshes 20 days apart (60 days total) keep the device signed in
    active = await login_helper("9000000004")
    token, previous_family_expiry = active["refresh_token"], active["session"]["family_expires_at"]
    for _ in range(3):
        clock["now"] += timedelta(days=20)
        rotated = await refresh(token)
        assert rotated.status_code == 200, rotated.text
        assert rotated.json()["session"]["family_expires_at"] > previous_family_expiry      # slid forward, not fixed
        token, previous_family_expiry = rotated.json()["refresh_token"], rotated.json()["session"]["family_expires_at"]
    # (access tokens minted under the fake future clock cannot be presented to /auth/me here: PyJWT rejects a future
    # `iat` against the real wall clock - a test-harness limit, not product behaviour.)

    # 4. explicit logout revokes the family: the refresh credential and the access token stop working
    clock["now"] = datetime.now(timezone.utc)                        # wall-clock again so the access token's iat is valid
    fresh = await login_helper("9000000004")
    out = await api_client.post("/api/auth/logout", headers={"Authorization": f"Bearer {fresh['token']}"})
    assert out.status_code == 200 and out.json()["logged_out"] is True
    assert (await refresh(fresh["refresh_token"])).status_code == 401
    assert (await me(fresh["token"])).status_code == 401


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
