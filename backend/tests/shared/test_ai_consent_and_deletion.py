"""AI consent (explicit, recorded, withdrawable; quick prompts included; in-flight guard) and complete local
account deletion (analytics_events fix, AI history, consent record, media detachment, truthful erasure report).
Isolated synthetic database, intercepted SMS, fake AI provider - nothing external is called."""
import pytest

from shared import core as c

pytestmark = pytest.mark.asyncio


def bearer(session):
    return {"Authorization": f"Bearer {session['token']}"}


@pytest.fixture
def fake_provider(monkeypatch):
    import emergentintegrations.llm.chat as chat_module

    calls = {"sent": [], "hook": None}

    class FakeChat:
        def __init__(self, api_key, session_id, system_message):
            self._messages, self.session_id = [], session_id

        def with_model(self, provider, model):
            calls["sent"].append(("model", provider, model))
            return self

        async def send_message(self, message):
            calls["sent"].append(("message", self.session_id, message.text))
            if calls["hook"]:
                hook, calls["hook"] = calls["hook"], None
                await hook()
            return "Fake assistant reply"

    monkeypatch.setattr(chat_module, "LlmChat", FakeChat)
    return calls


async def test_no_text_reaches_the_provider_without_current_consent_and_withdrawal_purges_history(api_client, isolated_db, seeded_users, login_helper, fake_provider):
    customer = await login_helper("9000000004")
    uid = customer["user"]["id"]
    info = await api_client.get("/api/ai/consent", headers=bearer(customer))
    assert info.status_code == 200 and info.json()["granted"] is False and info.json()["current_version"]
    recipient = info.json()["recipients"][0]
    assert recipient["name"] == "Anthropic PBC" and "Emergent" in recipient["via"] and recipient["data_not_sent"]
    assert "AI assistant quick prompts" in info.json()["required_for"]
    # A quick prompt is an ordinary chat message: it is refused too, and the provider is never constructed.
    for text in ("How to pitch silver anklets?", "my own question"):
        gated = await api_client.post("/api/ai/chat", json={"message": text}, headers=bearer(customer))
        assert gated.status_code == 403 and gated.json()["code"] == "AI_CONSENT_REQUIRED"
    assert fake_provider["sent"] == []
    # Everything else keeps working without consent.
    assert (await api_client.get("/api/products?limit=5", headers=bearer(customer))).status_code == 200
    assert (await api_client.get("/api/rewards/history", headers=bearer(customer))).status_code == 200
    # Grant: recorded with version, timestamp, recipients and an audit event; the chat now works.
    granted = await api_client.post("/api/ai/consent", json={"granted": True, "source": "quick_prompt"}, headers=bearer(customer))
    assert granted.status_code == 200 and granted.json()["granted"] is True and granted.json()["version"] == granted.json()["current_version"]
    record = await isolated_db["db"].users.find_one({"id": uid}, {"_id": 0, "ai_consent": 1, "ai_consent_events": 1})
    assert record["ai_consent"]["granted"] is True and record["ai_consent"]["recipients"] == ["Anthropic PBC"] and record["ai_consent"]["granted_at"]
    assert record["ai_consent_events"][-1]["source"] == "quick_prompt" and record["ai_consent_events"][-1]["granted"] is True
    reply = await api_client.post("/api/ai/chat", json={"message": "How to pitch silver anklets?"}, headers=bearer(customer))
    assert reply.status_code == 200 and reply.json()["stored"] is True and reply.json()["message_id"]
    model, session, text = fake_provider["sent"][0][2], fake_provider["sent"][1][1], fake_provider["sent"][1][2]
    assert model == "claude-sonnet-4-5-20250929" and text == "How to pitch silver anklets?"
    assert uid not in session and "9000000004" not in session and session.startswith("yt-")  # keyed pseudonym only
    assert await isolated_db["db"].ai_chat_history.count_documents({"user_id": uid}) == 2
    # Withdraw: epoch bumps, history and reports are deleted, further transfers stop, everything else still works.
    await api_client.post("/api/ai/reports", json={"message_id": reply.json()["message_id"], "reason": "test"}, headers=bearer(customer))
    withdrawn = await api_client.post("/api/ai/consent", json={"granted": False, "source": "profile"}, headers=bearer(customer))
    assert withdrawn.status_code == 200 and withdrawn.json()["granted"] is False and withdrawn.json()["history_deleted"] == 2
    assert "not erased" in withdrawn.json()["provider_copy"]
    assert await isolated_db["db"].ai_chat_history.count_documents({"user_id": uid}) == 0
    assert await isolated_db["db"].ai_reports.count_documents({"user_id": uid}) == 0
    record = await isolated_db["db"].users.find_one({"id": uid}, {"_id": 0, "ai_consent": 1})
    assert record["ai_consent"]["granted"] is False and record["ai_consent"]["epoch"] == 1 and record["ai_consent"]["withdrawn_at"]
    calls = len(fake_provider["sent"])
    assert (await api_client.post("/api/ai/chat", json={"message": "again"}, headers=bearer(customer))).status_code == 403
    assert len(fake_provider["sent"]) == calls
    assert (await api_client.get("/api/wishlist", headers=bearer(customer))).status_code in (200, 404)
    assert (await api_client.get("/api/auth/me", headers=bearer(customer))).status_code == 200


async def test_in_flight_reply_after_withdrawal_is_not_stored(api_client, isolated_db, seeded_users, login_helper, fake_provider):
    customer = await login_helper("9000000005")
    uid = customer["user"]["id"]
    await api_client.post("/api/ai/consent", json={"granted": True}, headers=bearer(customer))

    async def withdraw_mid_flight():
        res = await api_client.post("/api/ai/consent", json={"granted": False}, headers=bearer(customer))
        assert res.status_code == 200

    fake_provider["hook"] = withdraw_mid_flight
    reply = await api_client.post("/api/ai/chat", json={"message": "question while withdrawing"}, headers=bearer(customer))
    assert reply.status_code == 200 and reply.json()["stored"] is False and reply.json()["message_id"] is None
    assert "withdrawn" in reply.json()["notice"]
    assert await isolated_db["db"].ai_chat_history.count_documents({"user_id": uid}) == 0
    assert (await api_client.post("/api/ai/chat", json={"message": "next"}, headers=bearer(customer))).status_code == 403


async def test_account_deletion_removes_analytics_ai_history_consent_and_reports_truthfully(api_client, isolated_db, seeded_users, login_helper, fake_provider):
    db = isolated_db["db"]
    customer = await login_helper("9000000004")
    uid, phone = customer["user"]["id"], "9000000004"
    # Data in every personal location, including the legacy `analytics` collection the old code wrote to.
    for n in range(3):
        assert (await api_client.post("/api/analytics/event", json={"event_type": "product_view", "data": {"n": n}}, headers=bearer(customer))).status_code == 200
    assert await db.analytics_events.count_documents({"user_id": uid}) == 3  # the mismatch is fixed: events land where deletion looks
    await db.analytics.insert_one({"id": "legacy-1", "user_id": uid, "event_type": "legacy", "created_at": c.stamp()})
    await api_client.post("/api/ai/consent", json={"granted": True}, headers=bearer(customer))
    assert (await api_client.post("/api/ai/chat", json={"message": "hello"}, headers=bearer(customer))).json()["stored"] is True
    await db.media_assets.insert_one({"path": "yash-trade/test/personal.jpg", "owner_id": uid, "purpose": "test", "size_bytes": 10, "created_at": c.stamp()})
    await db.wishlists.insert_one({"user_id": uid, "product_id": "p1"})
    await db.reward_transactions.insert_one({"id": "rt1", "user_id": uid, "points": 5, "type": "credit", "created_at": c.stamp()})
    created = await api_client.post("/api/requests", json={"request_type": "callback", "notes": "call me at my shop"},
                                    headers={**bearer(customer), "Idempotency-Key": "del-1"})
    assert created.status_code == 200
    # OTP-confirmed deletion (intercepted transport; the login challenge row is cleared so the 60 s cooldown does not apply in the test).
    await db.otp_challenges.delete_many({"phone": phone})
    started = await api_client.post("/api/auth/delete-account/request", headers=bearer(customer))
    assert started.status_code == 200, started.text
    otp = isolated_db["sent_otps"][(phone, "account_deletion")]
    done = await api_client.post("/api/auth/delete-account/confirm", json={"otp": otp, "challenge_id": started.json()["challenge_id"]}, headers=bearer(customer))
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["deleted"] is True and body["status"] == "external_erasure_pending"
    report = body["erasure"]
    assert report["local_personal_records_remaining"] == 0 and report["by_collection"]["analytics_events"] == 0 and report["by_collection"]["analytics"] == 0
    assert report["by_collection"]["ai_chat_history"] == 0 and report["requests_anonymized"] == 1 and report["personal_media_objects"] == 0
    assert report["external"]["object_storage"]["delete_api"] is False and report["external"]["ai_provider"]["delete_api"] is False
    assert "not proven erased" in report["external"]["ai_provider"]["detail"]
    # Database truth matches the report.
    assert await db.analytics_events.count_documents({"user_id": uid}) == 0 and await db.analytics.count_documents({"user_id": uid}) == 0
    assert await db.ai_chat_history.count_documents({"user_id": uid}) == 0 and await db.wishlists.count_documents({"user_id": uid}) == 0
    assert await db.reward_transactions.count_documents({"user_id": uid}) == 0
    asset = await db.media_assets.find_one({"path": "yash-trade/test/personal.jpg"}, {"_id": 0})
    assert asset["owner_id"] == f"deleted:{uid}" and asset["access_revoked"] is True
    person = await db.users.find_one({"id": uid}, {"_id": 0})
    assert "ai_consent" not in person and person["phone"] == f"deleted:{uid}" and person["name"] == "Deleted customer"
    request = await db.requests.find_one({"id": created.json()["id"]}, {"_id": 0})
    assert request["anonymized"] is True and request["notes"] == "" and request["user_phone"] == "" and request["user_name"] == "Deleted customer"
    # Access is gone; the number cannot log in or re-enrol silently.
    assert (await api_client.get("/api/auth/me", headers=bearer(customer))).status_code in (401, 403)
    assert (await api_client.post("/api/auth/send-otp", json={"phone": phone, "channel": "mobile"})).status_code in (403, 404)
    outbox = await api_client.get("/api/integrations/deletions", headers={"X-Integration-Key": "integration-key-1234567890-abcdef"})
    assert outbox.status_code == 200 and outbox.json()["events"][0]["user_id"] == uid
    assert set(outbox.json()["events"][0]["required_acknowledgements"]) == {"website", "sms_provider", "ai_provider"}
