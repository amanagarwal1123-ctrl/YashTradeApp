"""Provider-erasure ledger: app/website cleanup and provider erasure are two separate outcomes.

Isolated synthetic database, intercepted SMS (test transport only), fake AI provider. The synthetic owner-admin
session belongs to the seeded fixture record 9999813334 in the ISOLATED database; no real SMS is dispatched."""
import pytest

from shared import core as c
from shared import provider_erasure as pe

pytestmark = pytest.mark.asyncio
INTEGRATION = {"X-Integration-Key": "integration-key-1234567890-abcdef"}


def bearer(session):
    return {"Authorization": f"Bearer {session['token']}"}


@pytest.fixture
def fake_provider(monkeypatch):
    import emergentintegrations.llm.chat as chat_module

    class FakeChat:
        def __init__(self, api_key, session_id, system_message):
            self._messages = []

        def with_model(self, provider, model):
            return self

        async def send_message(self, message):
            return "Fake reply"

    monkeypatch.setattr(chat_module, "LlmChat", FakeChat)


async def delete_customer(api_client, isolated_db, login_helper, phone, use_ai):
    customer = await login_helper(phone)
    if use_ai:
        await api_client.post("/api/ai/consent", json={"granted": True}, headers=bearer(customer))
        assert (await api_client.post("/api/ai/chat", json={"message": "hello"}, headers=bearer(customer))).json()["stored"] is True
        # Withdrawal deletes the app copy - the provider copy is still outstanding and the ledger must remember that.
        await api_client.post("/api/ai/consent", json={"granted": False}, headers=bearer(customer))
    await isolated_db["db"].otp_challenges.delete_many({"phone": phone})
    started = await api_client.post("/api/auth/delete-account/request", headers=bearer(customer))
    otp = isolated_db["sent_otps"][(phone, "account_deletion")]
    done = await api_client.post("/api/auth/delete-account/confirm", json={"otp": otp, "challenge_id": started.json()["challenge_id"]}, headers=bearer(customer))
    assert done.status_code == 200, done.text
    return customer["user"]["id"], done.json()


async def test_cleanup_and_provider_erasure_are_separate_outcomes(api_client, isolated_db, seeded_users, login_helper, fake_provider):
    db = isolated_db["db"]
    uid, body = await delete_customer(api_client, isolated_db, login_helper, "9000000004", use_ai=True)
    ref = body["reference"]
    # Snapshot taken before cleanup: real one-time codes were sent, the assistant was used (even though its app history
    # was already purged by the withdrawal), nothing was uploaded.
    ledger = (await db.deletion_requests.find_one({"reference": ref}, {"_id": 0}))["providers"]
    assert ledger["sms_provider"]["state"] == "not_requested" and ledger["sms_provider"]["data_present"] is True
    assert ledger["ai_provider"]["state"] == "not_requested" and ledger["ai_provider"]["data_present"] is True
    assert ledger["object_storage"]["state"] == "not_applicable" and ledger["object_storage"]["data_present"] is False
    assert body["status"] == "external_erasure_pending" and body["cleanup"]["app"] == "completed" and body["cleanup"]["website"] == "pending"
    assert body["provider_erasure"] == "outstanding"
    for key in ("sms_provider", "ai_provider"):
        ext = body["erasure"]["external"][key]
        assert ext["erasure"] == "not_requested" and ext["erasure_completed"] is False and "support" in ext["procedure"].lower()
    # Website acknowledgement -> cleanup_completed; provider states untouched, still outstanding.
    ack = await api_client.post(f"/api/integrations/deletions/{ref}/ack", headers=INTEGRATION)
    assert ack.status_code == 200 and ack.json()["all_acknowledged"] is True
    after = await db.deletion_requests.find_one({"reference": ref}, {"_id": 0})
    assert after["status"] == "cleanup_completed" and after["cleanup"]["website_acknowledged_at"]
    assert after["providers"] == ledger
    assert pe.summary(after["providers"]) == "outstanding"
    # Admin view separates the two outcomes explicitly.
    admin = await login_helper("9999813334")
    listing = await api_client.get("/api/admin/deletion-requests", headers=bearer(admin))
    assert listing.status_code == 200
    row = next(r for r in listing.json()["requests"] if r["reference"] == ref)
    assert row["status"] == "cleanup_completed" and row["cleanup"]["website"] == "acknowledged" and row["provider_erasure"] == "outstanding"
    assert row["meaning"]["provider_erasure"].startswith("separate")
    assert "phone" not in row and "name" not in row
    assert set(listing.json()["provider_procedures"]) == {"sms_provider", "ai_provider", "object_storage"} and "not_requested" in listing.json()["states"]


async def test_manual_provider_request_lifecycle_is_recorded_with_dates_outcomes_and_exceptions(api_client, isolated_db, seeded_users, login_helper, fake_provider):
    db = isolated_db["db"]
    uid, body = await delete_customer(api_client, isolated_db, login_helper, "9000000005", use_ai=True)
    ref = body["reference"]
    admin = await login_helper("9999813334")
    url = f"/api/admin/deletion-requests/{ref}/providers"
    # A confirmation cannot be recorded before the request itself; a not-applicable provider cannot be requested at all.
    early = await api_client.post(f"{url}/sms_provider", json={"action": "confirmed", "outcome": "deleted everything"}, headers=bearer(admin))
    assert early.status_code == 409 and early.json()["code"] == "PROVIDER_STATE"
    na = await api_client.post(f"{url}/object_storage", json={"action": "requested", "request_reference": "T-1"}, headers=bearer(admin))
    assert na.status_code == 409 and na.json()["code"] == "PROVIDER_NOT_APPLICABLE"
    assert (await api_client.post(f"{url}/unknown_provider", json={"action": "requested"}, headers=bearer(admin))).status_code == 404
    # SMS provider: request recorded with date + ticket reference -> still outstanding.
    requested = await api_client.post(f"{url}/sms_provider", json={"action": "requested", "requested_at": "2026-09-14T15:00:00+00:00",
                                                                    "request_reference": "MSG91-TCK-4471", "channel": "support ticket"}, headers=bearer(admin))
    assert requested.status_code == 200
    sms = requested.json()["providers"]["sms_provider"]
    assert sms["state"] == "requested" and sms["requested_at"] == "2026-09-14T15:00:00+00:00" and sms["request_reference"] == "MSG91-TCK-4471"
    assert requested.json()["provider_erasure"] == "outstanding" and sms["history"][-1]["action"] == "requested" and sms["history"][-1]["actor_id"] == admin["user"]["id"]
    # Confirmation needs a written outcome; then this provider is completed - but the ledger overall is still outstanding (AI).
    assert (await api_client.post(f"{url}/sms_provider", json={"action": "confirmed", "outcome": "ok"}, headers=bearer(admin))).status_code == 422
    confirmed = await api_client.post(f"{url}/sms_provider", json={"action": "confirmed", "outcome": "MSG91 support confirmed deletion of delivery logs for the number on 2026-09-16"}, headers=bearer(admin))
    assert confirmed.status_code == 200
    assert confirmed.json()["providers"]["sms_provider"]["state"] == "confirmed" and confirmed.json()["providers"]["sms_provider"]["outcome_at"]
    assert confirmed.json()["provider_erasure"] == "outstanding"
    # AI provider: request, then refusal - a refusal MUST carry the justified retention exception.
    await api_client.post(f"{url}/ai_provider", json={"action": "requested", "request_reference": "EMG-SUP-88", "channel": "email support@emergent.sh"}, headers=bearer(admin))
    bare = await api_client.post(f"{url}/ai_provider", json={"action": "refused", "outcome": "declined"}, headers=bearer(admin))
    assert bare.status_code == 422 and bare.json()["code"] == "RETENTION_EXCEPTION_REQUIRED"
    refused = await api_client.post(f"{url}/ai_provider", json={"action": "refused", "outcome": "Emergent: gateway logs retained for abuse monitoring",
        "retention_exception": {"reason": "Provider retains request logs for abuse monitoring under its terms", "basis": "provider terms s.4", "review_at": "2027-03-14"}}, headers=bearer(admin))
    assert refused.status_code == 200
    ai = refused.json()["providers"]["ai_provider"]
    assert ai["state"] == "refused" and ai["retention_exception"]["reason"].startswith("Provider retains") and ai["retention_exception"]["recorded_at"]
    assert refused.json()["provider_erasure"] == "retained_with_exception"
    # Reopen returns to requested (a request already exists) and the ledger is outstanding again; history keeps everything.
    reopened = await api_client.post(f"{url}/ai_provider", json={"action": "reopen"}, headers=bearer(admin))
    assert reopened.json()["providers"]["ai_provider"]["state"] == "requested" and reopened.json()["provider_erasure"] == "outstanding"
    assert [h["action"] for h in reopened.json()["providers"]["ai_provider"]["history"]] == ["requested", "refused", "reopen"]
    # The erasure report tells the same story: website ack pending, sms confirmed, ai outstanding - never a blanket "completed".
    from shared.people import erasure_report
    report = await erasure_report(uid)
    assert report["external"]["sms_provider"]["erasure_completed"] is True and report["external"]["ai_provider"]["erasure_completed"] is False
    assert report["provider_erasure"] == "outstanding"
    # Nothing here changed the cleanup outcome.
    assert (await db.deletion_requests.find_one({"reference": ref}, {"_id": 0}))["status"] == "external_erasure_pending"


async def test_ledger_endpoints_are_admin_only_and_no_procedure_stays_outstanding(api_client, isolated_db, seeded_users, login_helper, fake_provider):
    uid, body = await delete_customer(api_client, isolated_db, login_helper, "9000000004", use_ai=False)
    ref = body["reference"]
    ledger = body["erasure"]["external"]
    assert ledger["ai_provider"]["erasure"] == "not_applicable" and ledger["sms_provider"]["erasure"] == "not_requested"
    telecaller = await login_helper("9000000001")
    assert (await api_client.get("/api/admin/deletion-requests", headers=bearer(telecaller))).status_code == 403
    assert (await api_client.post(f"/api/admin/deletion-requests/{ref}/providers/sms_provider", json={"action": "requested"}, headers=bearer(telecaller))).status_code == 403
    assert (await api_client.get("/api/admin/deletion-requests")).status_code == 401
    admin = await login_helper("9999813334")
    short = await api_client.post(f"/api/admin/deletion-requests/{ref}/providers/sms_provider", json={"action": "no_procedure", "outcome": "none"}, headers=bearer(admin))
    assert short.status_code == 422
    res = await api_client.post(f"/api/admin/deletion-requests/{ref}/providers/sms_provider",
                                json={"action": "no_procedure", "outcome": "MSG91 support states delivery logs cannot be deleted per number; re-check quarterly"}, headers=bearer(admin))
    assert res.status_code == 200 and res.json()["providers"]["sms_provider"]["state"] == "no_procedure" and res.json()["provider_erasure"] == "outstanding"
    assert (await api_client.post(f"/api/admin/deletion-requests/DEL-missing/providers/sms_provider", json={"action": "requested"}, headers=bearer(admin))).status_code == 404


async def test_legacy_pre_shared_deletion_rows_are_stripped_merged_and_never_marked_erased(api_client, isolated_db, seeded_users, login_helper, fake_provider):
    """Rows written by the pre-shared deletion flow (reference DEL-<date>-<hex>, personal fields kept as a 'business
    record', duplicates) are converged once: personal fields removed, duplicates merged, provider states OUTSTANDING.
    A still-deleted account re-enters local cleanup; a re-activated account is marked superseded, nothing deleted."""
    db = isolated_db["db"]
    ts = c.stamp()
    await db.users.insert_many([
        {"id": "legacy-gone", "phone": "9100009901", "name": "Gone", "role": "customer", "account_status": "deleted", "status": "deleted", "session_version": 3},
        {"id": "legacy-back", "phone": "9100009902", "name": "Back", "role": "customer", "account_status": "active", "status": "active", "session_version": 1},
    ])
    await db.deletion_requests.insert_many([
        {"id": "l1", "reference": "DEL-20260909-AAAAAA", "user_id": "legacy-gone", "source": "app", "requested_at": ts, "status": "completed",
         "completed_at": ts, "phone": "9100009901", "name": "Gone", "shop_name": "Gone Traders"},
        {"id": "l1-dup", "reference": "DEL-20260909-AAAAAA", "user_id": "legacy-gone", "source": "app", "requested_at": ts, "status": "completed", "phone": "9100009901"},
        {"id": "l2", "reference": "DEL-20260909-BBBBBB", "user_id": "legacy-back", "source": "website", "requested_at": ts, "status": "completed",
         "phone": "9100009902", "name": "Back", "shop_name": "Back & Co"},
    ])
    first = await pe.reconcile()
    assert first["legacy_handled"] == 2 and first["legacy_duplicates_merged"] == 1 and first["providers_backfilled"] == 2
    assert await db.deletion_requests.count_documents({"reference": "DEL-20260909-AAAAAA"}) == 1
    gone = await db.deletion_requests.find_one({"reference": "DEL-20260909-AAAAAA"}, {"_id": 0})
    assert gone["status"] == "local_cleanup_pending" and gone["legacy"] is True and gone["legacy_status"] == "completed"
    assert not any(k in gone for k in ("phone", "name", "shop_name", "completed_at"))
    assert gone["providers"]["sms_provider"]["state"] == "not_requested" and gone["providers"]["ai_provider"]["data_present"] == "unknown"
    back = await db.deletion_requests.find_one({"reference": "DEL-20260909-BBBBBB"}, {"_id": 0})
    assert back["status"] == pe.SUPERSEDED and "phone" not in back
    assert (await db.users.find_one({"id": "legacy-back"}, {"_id": 0}))["account_status"] == "active"
    described = pe.describe(back)
    assert described["provider_erasure"] == "superseded" and described["cleanup"]["app"] == "superseded"
    # Idempotent: a second pass finds nothing legacy or unbackfilled.
    again = await pe.reconcile()
    assert again["legacy_handled"] == 0 and again["legacy_duplicates_merged"] == 0 and again["providers_backfilled"] == 0
    # The admin view lists both rows with the two outcomes and never as erased.
    admin = await login_helper("9999813334")
    listed = {r["reference"]: r for r in (await api_client.get("/api/admin/deletion-requests", headers=bearer(admin))).json()["requests"]}
    assert listed["DEL-20260909-AAAAAA"]["provider_erasure"] == "outstanding"
    assert listed["DEL-20260909-BBBBBB"]["provider_erasure"] == "superseded"
    blocked = await api_client.post("/api/admin/deletion-requests/DEL-20260909-BBBBBB/providers/sms_provider", json={"action": "requested"}, headers=bearer(admin))
    assert blocked.status_code == 409 and blocked.json()["code"] == "DELETION_SUPERSEDED"


async def test_interrupted_app_cleanup_is_resumed_only_by_an_explicit_admin_action(api_client, isolated_db, seeded_users, login_helper, fake_provider):
    """No background worker deletes records on its own (deployment policy: nothing destructive runs at startup).
    A deletion the customer confirmed but whose cleanup was interrupted stays visible as interrupted until an
    administrator explicitly resumes it; the resume is recorded, completes the tombstone and emits the website event."""
    from server import app
    db = isolated_db["db"]
    assert not hasattr(app.state, "deletion_worker")  # the startup hook registers no deletion worker any more
    admin = await login_helper("9999813334")
    ts = c.stamp()
    await db.users.insert_one({"id": "cust-int", "phone": "9100009903", "name": "Interrupted", "role": "customer", "account_status": "deleted",
                               "status": "deleted", "session_version": 2})
    await db.wishlists.insert_one({"user_id": "cust-int", "product_id": "p9"})
    await db.deletion_requests.insert_one({"id": "DEL-cust-int", "reference": "DEL-cust-int", "user_id": "cust-int", "source": "app",
                                           "requested_at": ts, "status": "local_cleanup_pending", "providers": {
                                               "sms_provider": pe.entry("sms_provider", True), "ai_provider": pe.entry("ai_provider", False),
                                               "object_storage": pe.entry("object_storage", False)}})
    listed = (await api_client.get("/api/admin/deletion-requests", headers=bearer(admin))).json()["requests"][0]
    assert listed["status"] == "local_cleanup_pending" and listed["cleanup"]["app"] == "pending" and "interrupted" in listed["cleanup"]["note"]
    assert await db.wishlists.count_documents({"user_id": "cust-int"}) == 1  # nothing was deleted by listing or by startup
    resumed = await api_client.post("/api/admin/deletion-requests/DEL-cust-int/cleanup", headers=bearer(admin))
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body["status"] == "external_erasure_pending" and body["cleanup"]["app"] == "completed" and body["provider_erasure"] == "outstanding"
    assert body["cleanup"]["resumed"][0]["actor_id"] == admin["user"]["id"]  # the audit entry is surfaced, not only persisted
    assert await db.wishlists.count_documents({"user_id": "cust-int"}) == 0
    tomb = await db.users.find_one({"id": "cust-int"}, {"_id": 0})
    assert tomb["phone"] == "deleted:cust-int" and tomb["session_version"] == 3
    row = await db.deletion_requests.find_one({"reference": "DEL-cust-int"}, {"_id": 0})
    assert row["cleanup"]["resumed"][0]["actor_id"] == admin["user"]["id"]
    assert (await db.integration_outbox.find_one({"id": "DEL-cust-int"}, {"_id": 0}))["required_acknowledgements"] == ["website"]
    # Guards: already completed -> 409; unknown -> 404; customers -> 403.
    again = await api_client.post("/api/admin/deletion-requests/DEL-cust-int/cleanup", headers=bearer(admin))
    assert again.status_code == 409 and again.json()["code"] == "CLEANUP_NOT_PENDING"
    assert (await api_client.post("/api/admin/deletion-requests/DEL-nope/cleanup", headers=bearer(admin))).status_code == 404
    customer = await login_helper("9000000004")
    assert (await api_client.post("/api/admin/deletion-requests/DEL-cust-int/cleanup", headers=bearer(customer))).status_code == 403
