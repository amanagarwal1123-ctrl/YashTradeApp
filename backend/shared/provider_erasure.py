"""Provider-erasure ledger: personal data that third-party providers still hold after an account deletion.

Every deletion request tracks TWO independent outcomes that are never merged into one "completed" flag:

* ``cleanup``   - the app's own records (immediate) and the enrolment website's copy (acknowledged through the outbox).
                  ``status`` = local_cleanup_pending -> external_erasure_pending -> cleanup_completed.
* ``providers`` - copies held by service providers that expose NO per-user deletion API. For them the only path is a
                  manual request to the provider's support desk; the ledger records whether that request was made, when,
                  under which reference, the outcome, and any justified retention exception the provider or the business
                  relies on. ``not_requested`` means exactly that - nothing has been done yet - and is an OUTSTANDING state.
                  A website acknowledgement never changes a provider state.

``provider_erasure`` (derived): not_applicable | outstanding | completed | retained_with_exception.
"""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from . import core as c

router = APIRouter(prefix="/api", tags=["Account deletion ledger"])

PROVIDER_META = {
    "sms_provider": {
        "provider": "MSG91",
        "holds": "Delivery logs of the one-time codes sent to the number (number, template, timestamps, delivery status)",
        "delete_api": False,
        "procedure": "Open a support ticket with MSG91 (dashboard Help / support@msg91.com) asking for deletion of the delivery logs "
                     "for the number during the account's active period; quote the DEL- reference; record the ticket ID here as the "
                     "request reference, then record MSG91's written answer as the outcome (or a retention exception if they refuse).",
    },
    "ai_provider": {
        "provider": "Anthropic (Claude) via Emergent LLM gateway",
        "holds": "AI-assistant message text and conversation context relayed under the business's gateway credential",
        "delete_api": False,
        "procedure": "Email support@emergent.sh (the business holds no direct Anthropic account - the gateway credential is Emergent's) "
                     "asking Emergent to delete its gateway logs for the account's usage window and to forward a per-conversation deletion "
                     "request to Anthropic; quote the DEL- reference; record the ticket ID, then the written answer as the outcome.",
    },
    "object_storage": {
        "provider": "Emergent Managed Object Storage",
        "holds": "Stored objects whose owner was the account (access already revoked in the app; bytes remain)",
        "delete_api": False,
        "procedure": "Email support@emergent.sh with the object paths listed in media_assets (owner_id = deleted:<canonical id>) asking for "
                     "their deletion; record the ticket ID, then the written answer as the outcome.",
    },
}
OUTSTANDING = ("not_requested", "requested", "no_procedure")
STATE_DOC = {
    "not_applicable": "No personal data of this account was ever transferred to the provider - nothing to erase.",
    "not_requested": "Data was transferred and NO erasure request has been made yet. Outstanding.",
    "requested": "A manual erasure request was submitted (date + reference recorded); the provider has not answered. Outstanding.",
    "no_procedure": "The provider offers no request path at all (recorded reason). Outstanding; re-check periodically.",
    "confirmed": "The provider confirmed erasure in writing (outcome + date recorded). Completed for this provider.",
    "refused": "The provider declined; the justified retention exception (reason, basis, review date) is recorded. Retained.",
}


def entry(key, data_present, note=None):
    state = "not_applicable" if data_present is False else "not_requested"
    doc = {"provider": PROVIDER_META[key]["provider"], "state": state, "data_present": data_present,
           "requested_at": None, "request_reference": None, "channel": None, "outcome": None, "outcome_at": None,
           "retention_exception": None, "history": []}
    if note:
        doc["note"] = note
    return doc


async def snapshot(user, uid, number):
    """Which providers hold personal data of this account. Computed BEFORE the local cleanup deletes the evidence."""
    real_sms = (not c.in_review()) and bool(number)
    consent_events = user.get("ai_consent_events") or []
    ai_used = any(e.get("granted") for e in consent_events) or \
        await c.db.ai_chat_history.count_documents({"$or": [{"user_id": uid}, {"session_id": f"jeweller-{uid}"}]}) > 0
    objects = await c.db.media_assets.count_documents({"owner_id": uid})
    return {"sms_provider": entry("sms_provider", real_sms),
            "ai_provider": entry("ai_provider", bool(ai_used)),
            "object_storage": entry("object_storage", objects > 0)}


async def historical_snapshot(uid):
    """Ledger for a deletion recorded before the ledger existed: the evidence is gone, so unknown presence is treated
    as OUTSTANDING (never as erased)."""
    objects = await c.db.media_assets.count_documents({"owner_id": f"deleted:{uid}"})
    return {"sms_provider": entry("sms_provider", not c.in_review(),
                                  note="historical request: presence inferred from scope (real one-time codes were sent to sign in)"),
            "ai_provider": entry("ai_provider", "unknown", note="historical request: AI usage unknown after cleanup; treated as outstanding"),
            "object_storage": entry("object_storage", objects > 0)}


def summary(providers):
    states = {p["state"] for p in (providers or {}).values()} or {"not_requested"}
    if states <= {"not_applicable"}:
        return "not_applicable"
    if states & set(OUTSTANDING):
        return "outstanding"
    if states <= {"confirmed", "not_applicable"}:
        return "completed"
    return "retained_with_exception"


SUPERSEDED = "superseded_reactivated"


def cleanup_of(deletion):
    status = deletion.get("status")
    stored = deletion.get("cleanup") or {}
    if status == SUPERSEDED:
        return {"app": "superseded", "website": "superseded", "website_acknowledged_at": None, "completed_at": None,
                "note": "legacy deletion request; the account is active again, so no cleanup is owed"}
    return {"app": "pending" if status == "local_cleanup_pending" else "completed",
            "website": "acknowledged" if status == "cleanup_completed" else "pending",
            "website_acknowledged_at": stored.get("website_acknowledged_at"),
            "completed_at": stored.get("completed_at")}


def describe(deletion):
    providers = {k: {**PROVIDER_META[k], **v} for k, v in (deletion.get("providers") or {}).items() if k in PROVIDER_META}
    return {**deletion, "providers": providers, "cleanup": cleanup_of(deletion),
            "provider_erasure": "superseded" if deletion.get("status") == SUPERSEDED else summary(providers),
            "meaning": {"status": "app + website cleanup only", "provider_erasure": "separate; a website acknowledgement never implies provider erasure"}}


def is_legacy(deletion):
    """Rows written by the pre-shared deletion flow: reference is not DEL-<canonical id>, they kept phone/name/shop_name
    as a 'business record', and no website erasure event was ever produced for them."""
    return deletion.get("reference") != "DEL-" + str(deletion.get("user_id", ""))


async def reconcile_legacy():
    """Legacy deletion requests: strip the personal fields they retained, merge duplicate rows, and finish what the
    user asked for. If the account is still deleted (or gone) the row re-enters local_cleanup_pending so the ordinary
    retry loop completes the tombstone/anonymization and emits the website erasure event. If the account is active
    again (re-enrolled), the request is marked superseded - no cleanup is owed and nothing is deleted."""
    rows = [r async for r in c.db.deletion_requests.find({"$expr": {"$ne": ["$reference", {"$concat": ["DEL-", {"$ifNull": ["$user_id", ""]}]}]},
                                                             "legacy": {"$exists": False}}, {"_id": 0})]
    handled = merged = 0
    by_ref = {}
    for row in sorted(rows, key=lambda r: r.get("requested_at", "")):
        by_ref.setdefault(row["reference"], []).append(row)
    for reference, group in by_ref.items():
        keep, dupes = group[0], group[1:]
        if dupes:
            res = await c.db.deletion_requests.delete_many({"reference": reference, "id": {"$in": [d["id"] for d in dupes if d.get("id")]}})
            merged += res.deleted_count
        user = await c.db.users.find_one({"id": keep["user_id"]}, {"_id": 0, "account_status": 1, "status": 1})
        active = bool(user) and user.get("account_status") != "deleted" and user.get("status") != "deleted"
        update = {"$set": {"legacy": True, "legacy_status": keep.get("status"), "legacy_reconciled_at": c.stamp(),
                           "merged_duplicates": len(dupes), "status": SUPERSEDED if active else "local_cleanup_pending"},
                  "$unset": {"phone": "", "name": "", "shop_name": "", "completed_at": "", "cleanup": ""}}
        await c.db.deletion_requests.update_one({"reference": reference}, update)
        handled += 1
    return {"legacy_handled": handled, "legacy_duplicates_merged": merged}


async def reconcile():
    """Idempotent migration of historical deletion requests to the two-outcome model. Preserves every outstanding
    provider state; never marks a provider erased."""
    legacy = await reconcile_legacy()
    renamed = (await c.db.deletion_requests.update_many({"status": "completed"},
        [{"$set": {"status": "cleanup_completed", "cleanup.website_acknowledged_at": {"$ifNull": ["$cleanup.website_acknowledged_at", "$completed_at"]},
                   "cleanup.completed_at": {"$ifNull": ["$cleanup.completed_at", "$completed_at"]}}}, {"$unset": "completed_at"}])).modified_count
    backfilled = 0
    async for deletion in c.db.deletion_requests.find({"providers": {"$exists": False}}, {"_id": 0, "reference": 1, "user_id": 1}):
        providers = await historical_snapshot(deletion["user_id"])
        res = await c.db.deletion_requests.update_one({"reference": deletion["reference"], "providers": {"$exists": False}},
                                                      {"$set": {"providers": providers}})
        backfilled += res.modified_count
    return {"status_renamed": renamed, "providers_backfilled": backfilled, **legacy}


class RetentionException(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=1000)
    basis: str = Field("", max_length=300)
    review_at: str | None = Field(None, max_length=40)


class ProviderAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["requested", "confirmed", "refused", "no_procedure", "reopen"]
    requested_at: str | None = Field(None, max_length=40)
    request_reference: str = Field("", max_length=200)
    channel: str = Field("", max_length=120)
    outcome: str = Field("", max_length=2000)
    retention_exception: RetentionException | None = None


@router.get("/admin/deletion-requests")
async def list_deletion_requests(user=Depends(c.admin)):
    rows = await c.db.deletion_requests.find({}, {"_id": 0}).sort("requested_at", -1).limit(200).to_list(200)
    return {"requests": [describe(r) for r in rows], "total": await c.db.deletion_requests.count_documents({}),
            "provider_procedures": PROVIDER_META, "states": STATE_DOC}


@router.post("/admin/deletion-requests/{reference}/providers/{provider}")
async def record_provider_action(reference: str, provider: str, req: ProviderAction, user=Depends(c.admin)):
    if provider not in PROVIDER_META:
        c.fail(404, "PROVIDER_UNKNOWN", "Use sms_provider, ai_provider or object_storage")
    deletion = await c.db.deletion_requests.find_one({"reference": reference}, {"_id": 0})
    if not deletion:
        c.fail(404, "DELETION_NOT_FOUND", "Unknown deletion reference")
    if deletion.get("status") == SUPERSEDED:
        c.fail(409, "DELETION_SUPERSEDED", "The account was re-activated after this legacy request; no provider erasure is owed for it")
    current = (deletion.get("providers") or {}).get(provider) or entry(provider, "unknown")
    state, ts = current["state"], c.stamp()
    if state == "not_applicable":
        c.fail(409, "PROVIDER_NOT_APPLICABLE", "No data of this account was transferred to this provider; nothing to request")
    fields = {}
    if req.action == "requested":
        if state in ("confirmed", "refused"):
            c.fail(409, "PROVIDER_STATE", "Already answered by the provider; use reopen first")
        fields = {"state": "requested", "requested_at": req.requested_at or ts, "request_reference": req.request_reference or None,
                  "channel": req.channel or None}
    elif req.action == "confirmed":
        if state != "requested":
            c.fail(409, "PROVIDER_STATE", "Record the request (date + reference) before recording the provider's confirmation")
        if len(req.outcome.strip()) < 5:
            c.fail(422, "OUTCOME_REQUIRED", "Record what the provider confirmed, in writing")
        fields = {"state": "confirmed", "outcome": req.outcome.strip(), "outcome_at": ts}
    elif req.action == "refused":
        if state != "requested":
            c.fail(409, "PROVIDER_STATE", "Record the request before recording a refusal")
        if not req.retention_exception:
            c.fail(422, "RETENTION_EXCEPTION_REQUIRED", "A refusal must record the justified retention exception (reason, basis, review date)")
        fields = {"state": "refused", "outcome": req.outcome.strip() or None, "outcome_at": ts,
                  "retention_exception": {**req.retention_exception.model_dump(), "recorded_at": ts}}
    elif req.action == "no_procedure":
        if state != "not_requested":
            c.fail(409, "PROVIDER_STATE", "no_procedure can only replace not_requested")
        if len(req.outcome.strip()) < 10:
            c.fail(422, "OUTCOME_REQUIRED", "Record why no request procedure exists at this provider")
        fields = {"state": "no_procedure", "outcome": req.outcome.strip(), "outcome_at": ts}
    else:  # reopen
        if state not in ("confirmed", "refused", "no_procedure"):
            c.fail(409, "PROVIDER_STATE", "Only an answered or no-procedure entry can be reopened")
        fields = {"state": "requested" if current.get("requested_at") else "not_requested", "outcome": None, "outcome_at": None,
                  "retention_exception": None}
    event = {"action": req.action, "at": ts, "actor_id": user["id"], **{k: v for k, v in fields.items() if k != "history"}}
    await c.db.deletion_requests.update_one({"reference": reference},
        {"$set": {f"providers.{provider}.{k}": v for k, v in {**current, **fields}.items() if k != "history"},
         "$push": {f"providers.{provider}.history": event}})
    fresh = await c.db.deletion_requests.find_one({"reference": reference}, {"_id": 0})
    return describe(fresh)
