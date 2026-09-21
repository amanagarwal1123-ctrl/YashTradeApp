"""Deployment policy: startup never mutates or deletes records. The one-off migrations (SMS-log retention, deletion-ledger
convergence) are explicit admin maintenance actions with a status report first."""
from datetime import datetime, timedelta, timezone

from shared import core as c
from shared import provider_erasure as pe


def bearer(session):
    return {"Authorization": "Bearer " + session["token"]}


async def test_startup_leaves_older_rows_untouched_and_reports_them(api_client, isolated_db, seeded_users, login_helper):
    from server import app
    db = isolated_db["db"]
    # Older-build shapes: an sms_log row without expiry, a legacy deletion row with retained PII + a duplicate, an
    # erasure event that still awaits providers, a request row without a provider snapshot.
    await db.sms_log.insert_one({"phone": "9100009905", "status": "sent", "sent_ts": 1_700_000_000})
    await db.sms_log.insert_one({"phone": "9100009906", "status": "sent", "sent_ts": "not-a-date"})
    await db.users.insert_one({"id": "legacy-x", "phone": "deleted:legacy-x", "role": "customer", "account_status": "deleted", "status": "deleted", "session_version": 3})
    await db.deletion_requests.insert_many([
        {"id": "lx1", "reference": "DEL-20260901-ABCDEF", "user_id": "legacy-x", "status": "completed", "requested_at": "2026-09-01T00:00:00+00:00", "phone": "9100009905", "name": "Legacy"},
        {"id": "lx2", "reference": "DEL-20260901-ABCDEF", "user_id": "legacy-x", "status": "completed", "requested_at": "2026-09-01T00:00:01+00:00", "phone": "9100009905"},
        {"id": "orphan", "reference": "DEL-20260901-000000", "status": "completed", "requested_at": "2026-09-01T00:00:02+00:00"},  # no user_id: never guessed at
    ])
    await db.integration_outbox.insert_one({"id": "DEL-20260901-ABCDEF", "type": "account_erased", "status": "pending",
                                            "required_acknowledgements": ["website", "sms_provider"], "acknowledged": ""})
    # Startup hooks ran when the app started for this test session: nothing above was changed by them.
    assert not hasattr(app.state, "deletion_worker")
    assert await db.deletion_requests.count_documents({"reference": "DEL-20260901-ABCDEF"}) == 2
    assert (await db.sms_log.find_one({"phone": "9100009905"})).get("expires_at") is None
    info = await db.sms_log.index_information()
    assert not any("expireAfterSeconds" in spec for spec in info.values())

    admin = await login_helper("9000000000")
    report = (await api_client.get("/api/admin/maintenance", headers=bearer(admin))).json()
    assert report["pending"] is True
    assert report["sms_log_retention"]["ttl_index"] is False and report["sms_log_retention"]["rows_without_expiry"] == 2
    assert report["deletion_ledger"]["legacy_rows"] == 3 and report["deletion_ledger"]["rows_with_old_status"] == 3
    assert report["deletion_ledger"]["outbox_events_to_correct"] == 1

    # Explicit action 1: retention. TTL index created, expiry back-filled (numeric epoch and unparseable string alike).
    applied = await api_client.post("/api/admin/maintenance/retention", headers=bearer(admin))
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] is True and applied.json()["backfilled"] == 2 and applied.json()["ttl_index"] is True
    numeric = await db.sms_log.find_one({"phone": "9100009905"})
    assert numeric["expires_at"] == datetime.fromtimestamp(1_700_000_000, tz=timezone.utc).replace(tzinfo=None) + timedelta(days=c.SMS_LOG_RETENTION_DAYS)
    unparseable = await db.sms_log.find_one({"phone": "9100009906"})
    assert (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=c.SMS_LOG_RETENTION_DAYS)) - unparseable["expires_at"] < timedelta(minutes=5)
    assert await db.sms_log.count_documents({"expires_at": {"$exists": False}}) == 0

    # Explicit action 2: deletion-ledger convergence. Duplicate merged, PII stripped, outstanding never marked erased,
    # the orphan row (no user_id) is skipped and reported, the outbox event only awaits the website.
    converged = await api_client.post("/api/admin/maintenance/deletions/reconcile", headers=bearer(admin))
    assert converged.status_code == 200, converged.text
    body = converged.json()
    assert body["legacy_handled"] == 1 and body["legacy_duplicates_merged"] == 1 and body["legacy_skipped"] == 1 and body["requirements_corrected"] == 1
    assert await db.deletion_requests.count_documents({"reference": "DEL-20260901-ABCDEF"}) == 1
    row = await db.deletion_requests.find_one({"reference": "DEL-20260901-ABCDEF"}, {"_id": 0})
    assert row["status"] == "local_cleanup_pending" and "phone" not in row and row["providers"]["ai_provider"]["state"] == "not_requested"
    assert (await db.integration_outbox.find_one({"id": "DEL-20260901-ABCDEF"}))["required_acknowledgements"] == ["website"]
    assert body["legacy_rows"] == 1  # only the orphan remains, visible in the report for manual review
    # Idempotent and access-controlled.
    again = (await api_client.post("/api/admin/maintenance/deletions/reconcile", headers=bearer(admin))).json()
    assert again["legacy_handled"] == 0 and again["legacy_duplicates_merged"] == 0
    customer = await login_helper("9000000004")
    assert (await api_client.get("/api/admin/maintenance", headers=bearer(customer))).status_code == 403
    assert (await api_client.post("/api/admin/maintenance/retention", headers=bearer(customer))).status_code == 403
    assert (await api_client.get("/health")).status_code == 200 and (await api_client.get("/health")).json()["status"] == "alive"
    assert pe.describe(row)["cleanup"]["app"] == "pending"
