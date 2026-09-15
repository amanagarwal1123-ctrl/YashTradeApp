"""Explicit, administrator-run maintenance. Nothing here runs at startup: deployments must never mutate or delete
records on their own (deployment policy), so the two one-off migrations of the store-submission builds are exposed as
reviewed admin actions with a status report the panel shows first.

  GET  /api/admin/maintenance                     what is pending (per data scope)
  POST /api/admin/maintenance/retention           apply the bounded SMS-log retention (TTL index + expiry back-fill)
  POST /api/admin/maintenance/deletions/reconcile converge older deletion requests to the two-outcome ledger
"""
from fastapi import APIRouter, Depends

from . import core as c
from . import provider_erasure as pe

router = APIRouter(prefix="/api", tags=["Maintenance"])


async def sms_log_ttl_present():
    info = await c.db.sms_log.index_information()
    return any(spec.get("key") == [("expires_at", 1)] and "expireAfterSeconds" in spec for spec in info.values())


async def status():
    legacy_filter = {"$expr": {"$ne": ["$reference", {"$concat": ["DEL-", {"$ifNull": ["$user_id", ""]}]}]}, "legacy": {"$exists": False}}
    return {
        "sms_log_retention": {
            "retention_days": c.SMS_LOG_RETENTION_DAYS,
            "ttl_index": await sms_log_ttl_present(),
            "rows_without_expiry": await c.db.sms_log.count_documents({"expires_at": {"$exists": False}}),
            "action": "POST /api/admin/maintenance/retention",
        },
        "deletion_ledger": {
            "legacy_rows": await c.db.deletion_requests.count_documents(legacy_filter),
            "rows_without_providers": await c.db.deletion_requests.count_documents({"providers": {"$exists": False}}),
            "rows_with_old_status": await c.db.deletion_requests.count_documents({"status": "completed"}),
            "outbox_events_to_correct": await c.db.integration_outbox.count_documents(
                {"type": "account_erased", "required_acknowledgements": {"$ne": ["website"]}}),
            "action": "POST /api/admin/maintenance/deletions/reconcile",
        },
    }


def pending(report):
    r, d = report["sms_log_retention"], report["deletion_ledger"]
    return (not r["ttl_index"] or r["rows_without_expiry"] > 0 or d["legacy_rows"] > 0 or d["rows_without_providers"] > 0
            or d["rows_with_old_status"] > 0 or d["outbox_events_to_correct"] > 0)


@router.get("/admin/maintenance")
async def maintenance_status(user=Depends(c.admin)):
    report = await status()
    return {**report, "pending": pending(report)}


@router.post("/admin/maintenance/retention")
async def apply_retention(user=Depends(c.admin)):
    """SMS delivery logs carry a phone number and exist only for OTP-delivery diagnostics. New rows are written with
    `expires_at`; this action creates the TTL index that enforces the window and gives rows from before the window an
    expiry derived from their send timestamp (numeric epoch or ISO string; unparseable stamps expire at the end of the
    window counted from now, so no row is retained indefinitely)."""
    await c.db.sms_log.create_index("expires_at", expireAfterSeconds=0)
    ttl_ms = c.SMS_LOG_RETENTION_DAYS * 86400 * 1000
    sent = {"$convert": {"input": {"$cond": [{"$isNumber": "$sent_ts"}, {"$multiply": ["$sent_ts", 1000]}, "$sent_ts"]},
                         "to": "date", "onError": "$$NOW", "onNull": "$$NOW"}}
    res = await c.db.sms_log.update_many({"expires_at": {"$exists": False}},
                                         [{"$set": {"expires_at": {"$add": [sent, ttl_ms]}}}])
    await c.db.maintenance_log.insert_one({"type": "retention", "actor_id": user["id"], "at": c.stamp(), "backfilled": res.modified_count})
    return {"applied": True, "backfilled": res.modified_count, **(await status())["sms_log_retention"]}


@router.post("/admin/maintenance/deletions/reconcile")
async def reconcile_deletions(user=Depends(c.admin)):
    """Converge deletion requests written by older builds to the two-outcome model (idempotent; never marks a
    provider erased; legacy duplicates are merged and their retained personal fields removed). Interrupted cleanups
    it surfaces are then resumed one by one from the ledger."""
    from .people import reconcile_outbox_acknowledgements
    counters = await reconcile_outbox_acknowledgements()
    await c.db.maintenance_log.insert_one({"type": "deletions_reconcile", "actor_id": user["id"], "at": c.stamp(), **counters})
    return {**counters, **(await status())["deletion_ledger"]}
