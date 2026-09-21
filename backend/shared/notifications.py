"""Push notifications: device registration, preferences, per-user inbox, admin campaigns and the durable outbox worker.

Delivery goes through the Expo Push Service (the tokens the app registers are Expo push tokens). Provider ACCEPTANCE
(a ticket) is recorded as `accepted`; a receipt is recorded when fetched; neither is proof the person saw the alert.
Nothing here is sent inline with a request: every send is an outbox job with an idempotent key, bounded batches,
retries with backoff, receipt handling and invalid-token cleanup.
"""
import asyncio
import logging
import re
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError, DuplicateKeyError

from . import core as c

router = APIRouter(prefix="/api", tags=["Notifications"])
log = logging.getLogger("shared.notifications")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
TOKEN_PATTERN = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]{8,120}\]$")
BATCH = 100                     # Expo accepts at most 100 messages per request
MAX_ATTEMPTS = 5
RECEIPT_DELAY_MINUTES = 15      # Expo asks senders to wait before fetching receipts
INBOX_RETENTION_DAYS = 180
CHANNELS = {"operational": "operational", "marketing": "marketing"}
# Internal in-app destinations a notification may open. Never an external URL; the app re-checks the role on arrival.
DESTINATION = re.compile(r"^/(\(tabs\)|notifications|staff-requests(\?request=[A-Za-z0-9_-]{1,64})?|product/[A-Za-z0-9_-]{1,64}"
                         r"|rate-list|schemes|brands|exhibition|showroom|wishlist|cart|my-requests|my-orders|rewards|knowledge)$")


# ---- transport -----------------------------------------------------------------------------------------------------

async def expo_send(messages):
    import httpx
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = c.setting("EXPO_PUSH_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(EXPO_PUSH_URL, json=messages, headers=headers)
    response.raise_for_status()
    return response.json().get("data", [])


async def expo_receipts(ticket_ids):
    import httpx
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = c.setting("EXPO_PUSH_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(EXPO_RECEIPTS_URL, json={"ids": ticket_ids}, headers=headers)
    response.raise_for_status()
    return response.json().get("data", {})


# Tests and the store-review scope replace these with recording doubles; production uses the Expo service.
transport = expo_send
receipts_transport = expo_receipts


def provider_status():
    return {"provider": "expo_push_service", "endpoint": EXPO_PUSH_URL,
            "access_token_configured": bool(c.setting("EXPO_PUSH_ACCESS_TOKEN")),
            "ios_image_attachments": "require a Notification Service Extension in the native iOS build (config plugin declared in app.json; not verifiable in Expo Go)"}


# ---- devices, preferences, inbox --------------------------------------------------------------------------------

class Device(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=10, max_length=200)
    platform: Literal["android", "ios", "web"]
    app_version: str = Field("", max_length=40)
    device_name: str = Field("", max_length=80)


@router.post("/notifications/devices")
async def register_device(req: Device, user=Depends(c.current_user)):
    if not TOKEN_PATTERN.match(req.token):
        c.fail(422, "INVALID_PUSH_TOKEN", "Register an Expo push token")
    ts = c.stamp()
    # One token belongs to exactly one account: registering after an account switch re-links the device.
    doc = await c.db.push_devices.find_one_and_update({"token": req.token},
        {"$set": {"user_id": user["id"], "role": user["role"], "platform": req.platform, "app_version": req.app_version,
                  "device_name": req.device_name, "enabled": True, "last_seen_at": ts, "updated_at": ts},
         "$unset": {"unlinked_at": "", "unlink_reason": "", "invalid_at": ""},
         "$setOnInsert": {"id": secrets.token_hex(12), "created_at": ts}},
        upsert=True, projection={"_id": 0, "token": 0}, return_document=ReturnDocument.AFTER)
    return {"device": doc, "preferences": await preferences_of(user)}


class Unlink(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/notifications/devices/unlink")
async def unlink_device(req: Unlink, user=Depends(c.current_user)):
    result = await c.db.push_devices.update_one({"token": req.token, "user_id": user["id"]},
        {"$set": {"enabled": False, "unlinked_at": c.stamp(), "unlink_reason": "logout"}})
    return {"unlinked": bool(result.modified_count)}


async def detach_devices(uid, reason):
    """Disable every device of an account (disable / delete / role change): the next person on that phone never
    receives this account's alerts."""
    await c.db.push_devices.update_many({"user_id": uid}, {"$set": {"enabled": False, "unlinked_at": c.stamp(), "unlink_reason": reason}})


async def preferences_of(user):
    prefs = user.get("notification_prefs") or {}
    return {"marketing": prefs.get("marketing", True), "operational": True,
            "operational_note": "Query and account alerts follow your role; promotional alerts can be switched off here."}


@router.get("/notifications/preferences")
async def get_preferences(user=Depends(c.current_user)):
    return await preferences_of(user)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    marketing: bool


@router.put("/notifications/preferences")
async def set_preferences(req: Preferences, user=Depends(c.current_user)):
    await c.db.users.update_one({"id": user["id"]}, {"$set": {"notification_prefs.marketing": req.marketing,
        "notification_prefs.updated_at": c.stamp()}})
    return await preferences_of({**user, "notification_prefs": {"marketing": req.marketing}})


@router.get("/notifications/inbox")
async def inbox(page: int = Query(1, ge=1), limit: int = Query(30, ge=1, le=100), user=Depends(c.current_user)):
    query = {"user_id": user["id"]}
    rows = await c.db.notifications.find(query, {"_id": 0, "user_id": 0, "expires_at": 0}).sort([("created_at", -1), ("id", 1)]).skip((page-1)*limit).limit(limit).to_list(limit)
    total = await c.db.notifications.count_documents(query)
    unread = await c.db.notifications.count_documents({**query, "read_at": None})
    return {"notifications": rows, "total": total, "unread": unread, "page": page, "limit": limit, "pages": (total+limit-1)//limit}


@router.post("/notifications/inbox/{nid}/read")
async def mark_read(nid: str, user=Depends(c.current_user)):
    doc = await c.db.notifications.find_one_and_update({"id": nid, "user_id": user["id"]},
        {"$set": {"read_at": c.stamp()}}, projection={"_id": 0, "user_id": 0}, return_document=ReturnDocument.AFTER)
    if not doc:
        c.fail(404, "NOTIFICATION_NOT_FOUND", "Notification not found")
    return doc


@router.post("/notifications/inbox/read-all")
async def mark_all_read(user=Depends(c.current_user)):
    result = await c.db.notifications.update_many({"user_id": user["id"], "read_at": None}, {"$set": {"read_at": c.stamp()}})
    return {"marked": result.modified_count}


# ---- building and queueing ----------------------------------------------------------------------------------------

def inbox_row(user_id, title, body, kind, destination, image_url="", campaign_id="", request_id="", key_prefix=""):
    # Deterministic id per (event, user): a retried fan-out of the same event never duplicates the inbox row.
    row_id = c.digest(f"{key_prefix}:{user_id}")[:24] if key_prefix else secrets.token_hex(12)
    return {"id": row_id, "user_id": user_id, "title": title, "body": body, "kind": kind,
            "destination": destination, "image_url": image_url, "campaign_id": campaign_id, "request_id": request_id,
            "created_at": c.stamp(), "read_at": None, "expires_at": c.now() + timedelta(days=INBOX_RETENTION_DAYS)}


def message_for(device, row):
    msg = {"to": device["token"], "title": row["title"], "body": row["body"], "sound": "default",
           "channelId": CHANNELS["marketing" if row["kind"] == "marketing" else "operational"],
           "data": {"destination": row["destination"], "notification_id": row["id"], "kind": row["kind"],
                    "request_id": row.get("request_id", ""), "campaign_id": row.get("campaign_id", "")},
           "_user_id": device["user_id"], "_notification_id": row["id"]}
    if row.get("image_url"):
        # Android shows the image through richContent; iOS needs the native service extension (mutableContent) and
        # falls back to the text alert when the attachment cannot be fetched within the OS limits.
        msg["richContent"] = {"image": row["image_url"]}
        msg["data"]["image"] = row["image_url"]  # also readable by the iOS service extension (body.image)
        msg["mutableContent"] = True
    return msg


async def enqueue(key, kind, messages, campaign_id="", request_id=""):
    """Idempotent: the same key (creation retry, double tap) never produces a second batch."""
    if not messages:
        return False
    try:
        await c.db.notification_outbox.insert_one({"id": secrets.token_hex(12), "key": key, "kind": kind, "campaign_id": campaign_id,
            "request_id": request_id, "messages": messages, "status": "pending", "attempts": 0,
            "next_attempt_at": c.stamp(), "created_at": c.stamp(), "tickets": [], "errors": []})
        return True
    except DuplicateKeyError:
        return False


async def devices_for(user_ids):
    return await c.db.push_devices.find({"user_id": {"$in": list(user_ids)}, "enabled": True}, {"_id": 0}).to_list(None)


async def insert_inbox(rows):
    """Deterministic ids: rows already written by an earlier attempt of the same event are skipped, never duplicated."""
    rows = list(rows)
    if not rows:
        return
    try:
        await c.db.notifications.insert_many(rows, ordered=False)
    except BulkWriteError as exc:   # duplicates from a previous attempt of the same event are expected
        if any(e.get("code") != 11000 for e in exc.details.get("writeErrors", [])):
            raise


USERS_PER_BATCH = 25   # frozen-audience chunk -> one outbox job with a STABLE key `<event>:<chunk index>`


async def fan_out(key_prefix, kind, recipients, title, body, destination, image_url="", campaign_id="", request_id=""):
    """recipients: iterable of user ids. Writes one inbox row per user (revisitable history) and queues push messages
    for every enabled device in bounded batches.

    Durable and idempotent per `key_prefix` (G04): the FIRST call freezes the audience snapshot in
    `notification_events` (state `pending`); every call - the first, a retry after a crash midway, a worker resume -
    walks that frozen snapshot in fixed chunks with stable outbox keys and deterministic inbox ids, so every intended
    recipient, device and inbox row is reached exactly once, and only the LAST step marks the event `complete`. A
    complete event answers `duplicate=True` without work; a pending one is never mistaken for a finished fan-out
    because one batch or one inbox row happens to exist. Returns counts of users, devices and NEWLY queued batches."""
    ts = c.stamp()
    recipients = list(dict.fromkeys(recipients))
    event = await c.db.notification_events.find_one_and_update({"id": key_prefix},
        {"$setOnInsert": {"id": key_prefix, "kind": kind, "recipients": recipients, "title": title, "body": body, "destination": destination,
                          "image_url": image_url, "campaign_id": campaign_id, "request_id": request_id, "state": "pending", "created_at": ts},
         "$set": {"updated_at": ts}, "$inc": {"attempts": 1}},
        upsert=True, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if event["state"] == "complete":
        return {"users": len(event["recipients"]), "devices": event.get("stats", {}).get("devices", 0), "batches": 0, "existing_batches": event.get("stats", {}).get("batches", 0), "duplicate": True}
    recipients = event["recipients"]   # frozen snapshot: a retry serves the SAME audience, whatever changed since
    users, devices, batches, existing = len(recipients), 0, 0, 0
    for index, start in enumerate(range(0, len(recipients), USERS_PER_BATCH)):
        chunk = recipients[start:start + USERS_PER_BATCH]
        rows = {uid: inbox_row(uid, event["title"], event["body"], event["kind"], event["destination"], event.get("image_url", ""),
                               event.get("campaign_id", ""), event.get("request_id", ""), key_prefix) for uid in chunk}
        await insert_inbox(rows.values())
        messages = [message_for(device, rows[device["user_id"]]) for device in await devices_for(chunk)]
        devices += len(messages)
        if messages:
            if await enqueue(f"{key_prefix}:{index}", event["kind"], messages, event.get("campaign_id", ""), event.get("request_id", "")):
                batches += 1
            else:
                existing += 1
    await c.db.notification_events.update_one({"id": key_prefix}, {"$set": {"state": "complete", "completed_at": c.stamp(),
        "stats": {"users": users, "devices": devices, "batches": batches + existing}}})
    return {"users": users, "devices": devices, "batches": batches, "existing_batches": existing}


REQUEST_LABELS = {"video_call": "Video call request", "ask_price": "Price enquiry", "callback": "Call-back request",
                  "similar_products": "Similar products request", "hold_item": "Hold-item request",
                  "quick_reorder": "Quick re-order", "cart_selection": "Cart selection"}


async def query_created(doc):
    """One operational event per successfully created customer query, for every active telecaller (their inbox and
    every enabled device). Idempotent on the request id: a retried creation never notifies twice, while a retry after
    a PARTIAL fan-out (G04) completes the remaining recipients and inbox rows from the frozen audience. Lock-screen
    text carries the shop / first name only - never the phone number or the free-text notes."""
    event = await c.db.notification_events.find_one({"id": f"query:{doc['id']}"}, {"_id": 0, "state": 1, "recipients": 1})
    if event and event["state"] == "complete":
        return {"users": 0, "devices": 0, "batches": 0, "duplicate": True}
    telecallers = event["recipients"] if event else [u["id"] async for u in c.db.users.find({"role": {"$in": ["telecaller", "executive"]},
        "account_status": {"$nin": ["inactive", "deleted", "disabled"]}, "status": {"$nin": ["inactive", "deleted", "disabled"]}}, {"_id": 0, "id": 1})]
    if not telecallers:
        return {"users": 0, "devices": 0, "batches": 0}
    who = doc.get("shop_name") or doc.get("customer_shop_name") or (doc.get("user_name") or doc.get("customer_name") or "a customer").split(" ")[0]
    label = REQUEST_LABELS.get(doc.get("request_type"), "Customer query")
    count = len(doc.get("product_ids") or []) or (doc.get("cart_count") or 0)
    body = f"{label} from {who}" + (f" · {count} item{'s' if count != 1 else ''}" if count else "") + " · tap to take the query"
    return await fan_out(f"query:{doc['id']}", "operational", telecallers, "New customer query", body,
                         f"/staff-requests?request={doc['id']}", request_id=doc["id"])


# ---- admin campaigns ----------------------------------------------------------------------------------------------

class Audience(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["all_users", "customers", "selected"] = "customers"
    customer_ids: list[str] = Field(default_factory=list, max_length=500)
    cities: list[str] = Field(default_factory=list, max_length=50)
    customer_types: list[str] = Field(default_factory=list, max_length=20)
    assigned_telecaller: str = Field("", max_length=64)
    lead_statuses: list[str] = Field(default_factory=list, max_length=10)
    match: Literal["all", "any"] = "all"


def audience_query(spec: Audience):
    base = {"account_status": {"$nin": ["inactive", "deleted", "disabled"]}, "status": {"$nin": ["inactive", "deleted", "disabled"]},
            "notification_prefs.marketing": {"$ne": False}}
    if spec.target == "all_users":
        base["role"] = {"$in": sorted(c.ROLES | {"executive"})}
    else:
        base["role"] = "customer"
    if spec.target == "selected":
        if not spec.customer_ids:
            c.fail(422, "AUDIENCE_EMPTY", "Select at least one customer")
        return {**base, "id": {"$in": spec.customer_ids}}
    clauses = []
    if spec.cities:
        pattern = {"$in": [re.compile("^" + re.escape(city.strip()) + "$", re.I) for city in spec.cities if city.strip()]}
        clauses.append({"$or": [{"city": pattern}, {"location": pattern}]})
    if spec.customer_types:
        clauses.append({"customer_type": {"$in": spec.customer_types}})
    if spec.assigned_telecaller:
        clauses.append({"assigned_salesperson": spec.assigned_telecaller})
    if spec.lead_statuses:
        clauses.append({"lead_status": {"$in": spec.lead_statuses}})
    if clauses:
        base["$and" if spec.match == "all" else "$or"] = clauses
    return base


async def resolve_audience(spec: Audience):
    query = audience_query(spec)
    users = await c.db.users.count_documents(query)
    devices = 0
    reachable = 0
    async for group in c.db.users.aggregate([{"$match": query}, {"$project": {"_id": 0, "id": 1}},
            {"$lookup": {"from": c.collection_name("push_devices"), "localField": "id", "foreignField": "user_id", "as": "d",
                         "pipeline": [{"$match": {"enabled": True}}, {"$project": {"_id": 0, "id": 1}}]}},
            {"$project": {"n": {"$size": "$d"}}},
            {"$group": {"_id": None, "devices": {"$sum": "$n"}, "reachable": {"$sum": {"$cond": [{"$gt": ["$n", 0]}, 1, 0]}}}}]):
        devices, reachable = group["devices"], group["reachable"]
    return {"users": users, "reachable_users": reachable, "devices": devices, "semantics": {
        "match": spec.match, "target": spec.target,
        "excluded": "disabled/deleted accounts, marketing opt-outs, unlinked or invalid device tokens",
        "counts": "users and devices are counted separately; a person with two phones is one user, two devices"}}


@router.get("/admin/notifications/filters")
async def filters(user=Depends(c.admin)):
    """Audience filter values that exist in the data (nothing is fabricated): places, customer types, telecallers, lead heads."""
    active = {"role": "customer", "account_status": {"$nin": ["deleted"]}}
    cities = sorted({(v or "").strip() for v in await c.db.users.distinct("city", active)} | {(v or "").strip() for v in await c.db.users.distinct("location", active)} - {""}, key=str.lower)
    types = sorted({(v or "").strip() for v in await c.db.users.distinct("customer_type", active)} - {""})
    leads = sorted({(v or "").strip() for v in await c.db.users.distinct("lead_status", active)} - {""})
    telecallers = await c.db.users.find({"role": {"$in": ["telecaller", "executive"]}, "account_status": {"$ne": "deleted"}},
                                        {"_id": 0, "id": 1, "name": 1}).sort([("name", 1), ("id", 1)]).limit(500).to_list(500)
    return {"cities": cities[:500], "customer_types": types, "lead_statuses": leads, "telecallers": telecallers,
            "targets": ["all_users", "customers", "selected"], "match": ["all", "any"]}


@router.post("/admin/notifications/audience")
async def audience(spec: Audience, user=Depends(c.admin)):
    return await resolve_audience(spec)


class Campaign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=240)
    image_url: str = Field("", max_length=500)
    destination: str = Field("/notifications", max_length=200)
    audience: Audience = Field(default_factory=Audience)


def validate_campaign(req: Campaign):
    if req.image_url and not re.match(r"^https://[^\s]+$", req.image_url):
        c.fail(422, "INVALID_IMAGE_URL", "Notification images must be public https URLs")
    if not DESTINATION.match(req.destination):
        c.fail(422, "INVALID_DESTINATION", "Choose an in-app destination")


def campaign_view(doc):
    doc.pop("_id", None)
    return doc


@router.post("/admin/notifications/campaigns")
async def create_campaign(req: Campaign, user=Depends(c.admin)):
    validate_campaign(req)
    doc = {"id": secrets.token_hex(12), **req.model_dump(), "status": "draft", "created_by": user["id"], "created_by_name": user.get("name", ""),
           "created_at": c.stamp(), "updated_at": c.stamp(), "stats": {"users": 0, "devices": 0, "batches": 0, "accepted": 0, "errors": 0, "invalid_tokens": 0}}
    await c.db.notification_campaigns.insert_one(dict(doc))
    return campaign_view(doc)


@router.put("/admin/notifications/campaigns/{cid}")
async def update_campaign(cid: str, req: Campaign, user=Depends(c.admin)):
    validate_campaign(req)
    doc = await c.db.notification_campaigns.find_one_and_update({"id": cid, "status": "draft"},
        {"$set": {**req.model_dump(), "updated_at": c.stamp()}}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not doc:
        c.fail(409, "CAMPAIGN_NOT_EDITABLE", "Only drafts can be edited")
    return doc


@router.get("/admin/notifications/campaigns")
async def list_campaigns(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), user=Depends(c.admin)):
    rows = await c.db.notification_campaigns.find({}, {"_id": 0}).sort([("created_at", -1), ("id", 1)]).skip((page-1)*limit).limit(limit).to_list(limit)
    total = await c.db.notification_campaigns.count_documents({})
    return {"campaigns": rows, "total": total, "page": page, "limit": limit, "pages": (total+limit-1)//limit, "provider": provider_status()}


@router.get("/admin/notifications/campaigns/{cid}")
async def get_campaign(cid: str, user=Depends(c.admin)):
    doc = await c.db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    if not doc:
        c.fail(404, "CAMPAIGN_NOT_FOUND", "Campaign not found")
    jobs = await c.db.notification_outbox.find({"campaign_id": cid}, {"_id": 0, "messages": 0, "tickets": 0}).to_list(1000)
    return {**doc, "outbox": jobs, "audience_now": await resolve_audience(Audience(**doc["audience"]))}


@router.post("/admin/notifications/campaigns/{cid}/test")
async def test_send(cid: str, user=Depends(c.admin)):
    """Sends the draft to the administrator's OWN enabled devices only (no audience, no history row for others)."""
    doc = await c.db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    if not doc:
        c.fail(404, "CAMPAIGN_NOT_FOUND", "Campaign not found")
    if not await devices_for([user["id"]]):
        c.fail(409, "NO_TEST_DEVICE", "Allow notifications on this device first (your account has no enabled device)")
    result = await fan_out(f"campaign-test:{cid}:{secrets.token_hex(4)}", "marketing", [user["id"]], doc["title"], doc["body"],
                           doc["destination"], doc.get("image_url", ""), campaign_id=cid)
    return {"test": True, **result}


class SendConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_users: int = Field(ge=0)


FANOUT_LEASE_SECONDS = 300


def fanout_lease():
    return (c.now() + timedelta(seconds=FANOUT_LEASE_SECONDS)).isoformat()


@router.post("/admin/notifications/campaigns/{cid}/send")
async def send_campaign(cid: str, req: SendConfirmation, user=Depends(c.admin)):
    """draft -> sending atomically (a double tap or a second administrator gets 409); the audience is resolved ONCE
    and frozen (campaign snapshot + fan-out event); the confirmation must carry the user count the administrator
    inspected. The fan-out runs under a durable lease (G04): if this process stops before it finished, the outbox
    worker resumes the same event after the lease expires - same frozen audience, stable batch keys, deterministic
    inbox ids - so a campaign can neither stay in `sending` forever nor be sent twice."""
    draft = await c.db.notification_campaigns.find_one({"id": cid}, {"_id": 0})
    if not draft:
        c.fail(404, "CAMPAIGN_NOT_FOUND", "Campaign not found")
    spec = Audience(**draft["audience"])
    counts = await resolve_audience(spec)
    frozen = await c.db.notification_events.find_one({"id": f"campaign:{cid}"}, {"_id": 0, "recipients": 1})
    if frozen:
        # A resend after an interrupted fan-out completes the audience that was frozen the first time (G04): the
        # confirmation must match THAT audience, and later joiners are not silently added to a half-sent campaign.
        counts = {**counts, "users": len(frozen["recipients"]), "frozen": True}
    if counts["users"] != req.confirm_users:
        c.fail(409, "AUDIENCE_CHANGED", f"The audience is now {counts['users']} users (you confirmed {req.confirm_users}); review and confirm again")
    if not counts["users"]:
        c.fail(409, "AUDIENCE_EMPTY", "No eligible recipients")
    claimed = await c.db.notification_campaigns.find_one_and_update({"id": cid, "status": "draft"},
        {"$set": {"status": "sending", "sent_by": user["id"], "sent_at": c.stamp(), "audience_snapshot": counts,
                  "fanout": {"state": "pending", "lease_until": fanout_lease(), "started_at": c.stamp(), "resumes": 0}}}, projection={"_id": 0})
    if not claimed:
        c.fail(409, "CAMPAIGN_ALREADY_SENT", "This campaign was already sent or is being sent")
    try:
        status, result = await run_campaign_fanout({**claimed, "status": "sending"})
    except Exception as exc:
        # A CAUGHT failure hands the decision back to the administrator: the campaign returns to draft with the error
        # recorded; the event, batches and inbox rows already stored keep their idempotent keys, so a second SEND
        # completes the fan-out without duplicating anything. (A process stop is recovered by the worker instead.)
        await c.db.notification_campaigns.update_one({"id": cid, "status": "sending"},
            {"$set": {"status": "draft", "fanout.state": "failed", "updated_at": c.stamp()}, "$push": {"send_errors": {"at": c.stamp(), "error": type(exc).__name__}}})
        c.fail(503, "FAN_OUT_FAILED", "Queuing the campaign failed before every batch was stored; nothing was sent twice. Review and send again")
    return {"campaign_id": cid, "status": status, **result, "batches": result["batches"] + result["existing_batches"],
            "note": "Queued for the push provider; provider acceptance and receipts are recorded per batch, they are not proof of display"}


async def run_campaign_fanout(campaign):
    """Fan-out + finalisation shared by the inline send and the worker's resume. The recipients computed here are
    used only when the event does not exist yet (nothing was stored); otherwise the event's frozen snapshot wins."""
    cid = campaign["id"]
    recipients = [u["id"] async for u in c.db.users.find(audience_query(Audience(**campaign["audience"])), {"_id": 0, "id": 1})]
    result = await fan_out(f"campaign:{cid}", "marketing", recipients, campaign["title"], campaign["body"], campaign["destination"],
                           campaign.get("image_url", ""), campaign_id=cid)
    ts = c.stamp()
    stats = {} if result.get("duplicate") else {"stats.users": result["users"], "stats.devices": result["devices"], "stats.batches": result["batches"] + result["existing_batches"]}
    await c.db.notification_campaigns.update_one({"id": cid}, {"$set": {"fanout.state": "complete", "fanout.completed_at": ts, "updated_at": ts, **stats}})
    remaining = await c.db.notification_outbox.count_documents({"campaign_id": cid, "status": {"$in": ["pending", "sending"]}})
    status = "queued" if remaining else "sent"
    await c.db.notification_campaigns.update_one({"id": cid, "status": "sending"},
        {"$set": {"status": status, "fanout.lease_until": None, **({"completed_at": ts} if status == "sent" else {})}})
    return status, result


async def recover_campaigns():
    """G04: a campaign left in `sending` by a process that stopped mid fan-out (no exception handler ran) is resumed by
    the worker once its fan-out lease expired. The resume is the same idempotent event, so nothing is queued or listed
    twice, and the campaign is finalised exactly like the inline path. Returns the ids resumed in this pass."""
    resumed = []
    for _ in range(20):
        now = c.stamp()
        doc = await c.db.notification_campaigns.find_one_and_update(
            {"status": "sending", "$or": [{"fanout.lease_until": {"$lt": now}}, {"fanout.lease_until": None}]},
            {"$set": {"fanout.state": "pending", "fanout.lease_until": fanout_lease(), "fanout.resumed_at": now}, "$inc": {"fanout.resumes": 1}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if not doc:
            break
        await run_campaign_fanout(doc)
        resumed.append(doc["id"])
    return resumed


@router.get("/admin/notifications/outbox")
async def outbox_status(user=Depends(c.admin)):
    counts = {r["_id"]: r["n"] async for r in c.db.notification_outbox.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    return {"by_status": counts, "worker": worker_state, "provider": provider_status()}


# ---- worker ---------------------------------------------------------------------------------------------------------

worker_state = {"running": False, "last_tick": None, "sent_batches": 0, "failed_batches": 0, "last_error": None}


def _strip(messages):
    return [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]


async def _invalidate(token, reason):
    await c.db.push_devices.update_one({"token": token}, {"$set": {"enabled": False, "invalid_at": c.stamp(), "unlink_reason": reason}})


INACTIVE = ["inactive", "deleted", "disabled"]
QUERY_WORKER_ROLES = {"telecaller", "executive", "admin"}


async def eligible_messages(job):
    """F02: the outbox froze token + recipient at fan-out time. Immediately before every send/retry each message is
    re-validated against the CURRENT state: the token must still be an enabled device of that same account, the
    account must be usable, marketing recipients must still accept marketing, and operational query alerts only go to
    accounts that still hold a query-worker role. Ineligible messages are dropped from the batch and accounted for
    (never sent to a device that now belongs to someone else, a signed-out phone or an opted-out person)."""
    messages = job["messages"]
    tokens = {m["to"] for m in messages}
    devices = {d["token"]: d async for d in c.db.push_devices.find({"token": {"$in": list(tokens)}}, {"_id": 0, "token": 1, "user_id": 1, "enabled": 1})}
    users = {u["id"]: u async for u in c.db.users.find({"id": {"$in": list({m["_user_id"] for m in messages})}},
                                                       {"_id": 0, "id": 1, "role": 1, "account_status": 1, "status": 1, "notification_prefs": 1})}
    keep, skipped = [], []
    for m in messages:
        device, user = devices.get(m["to"]), users.get(m["_user_id"])
        reason = None
        if not device or not device.get("enabled", False):
            reason = "device_unlinked"
        elif device["user_id"] != m["_user_id"]:
            reason = "device_reassigned"
        elif not user or c.account_status(user) in INACTIVE or user.get("status") in INACTIVE:
            reason = "account_unusable"
        elif job["kind"] == "marketing" and (user.get("notification_prefs") or {}).get("marketing") is False:
            reason = "marketing_opt_out"
        elif job["kind"] == "operational" and job.get("request_id") and ("telecaller" if user.get("role") == "executive" else user.get("role")) not in QUERY_WORKER_ROLES:
            reason = "role_changed"
        if reason:
            skipped.append({"token_tail": m["to"][-6:], "user_id": m["_user_id"], "reason": reason})
            if reason in {"marketing_opt_out", "account_unusable", "role_changed"} and m.get("_notification_id"):
                await c.db.notifications.delete_one({"id": m["_notification_id"], "user_id": m["_user_id"], "read_at": None})
        else:
            keep.append(m)
    return keep, skipped


async def process_job(job):
    messages, skipped = await eligible_messages(job)
    if not messages:
        await c.db.notification_outbox.update_one({"id": job["id"]}, {"$set": {"status": "sent", "sent_at": c.stamp(), "tickets": [], "skipped": skipped,
            "accepted": 0, "errors_count": 0, "invalid_tokens": 0, "skipped_count": len(skipped), "lease_until": None}, "$inc": {"attempts": 1}})
        await _campaign_progress(job, 0, 0, 0, len(skipped))
        return "sent"
    try:
        tickets = []
        for start in range(0, len(messages), BATCH):   # the provider accepts at most BATCH messages per request
            tickets.extend(await transport(_strip(messages[start:start + BATCH])))
    except Exception as exc:  # provider/network failure: retry with backoff, never drop the batch silently
        attempts = job["attempts"] + 1
        status = "failed" if attempts >= MAX_ATTEMPTS else "pending"
        await c.db.notification_outbox.update_one({"id": job["id"]}, {"$set": {"status": status, "attempts": attempts,
            "next_attempt_at": (c.now() + timedelta(seconds=min(600, 10 * 2 ** attempts))).isoformat(), "lease_until": None},
            "$push": {"errors": {"at": c.stamp(), "error": type(exc).__name__}}})
        worker_state["last_error"] = type(exc).__name__
        if status == "failed":
            worker_state["failed_batches"] += 1
        return status
    accepted, invalid, errors, stored = 0, 0, 0, []
    for message, ticket in zip(messages, tickets):
        entry = {"ticket_id": ticket.get("id"), "status": ticket.get("status"), "token_tail": message["to"][-6:], "user_id": message["_user_id"]}
        if ticket.get("status") == "ok":
            accepted += 1
        else:
            errors += 1
            detail = (ticket.get("details") or {}).get("error", "")
            entry["error"] = detail or (ticket.get("message") or "")[:120]
            if detail == "DeviceNotRegistered":
                invalid += 1
                await _invalidate(message["to"], "DeviceNotRegistered")
        stored.append(entry)
    await c.db.notification_outbox.update_one({"id": job["id"]}, {"$set": {"status": "sent", "sent_at": c.stamp(), "tickets": stored, "skipped": skipped,
        "accepted": accepted, "errors_count": errors, "invalid_tokens": invalid, "skipped_count": len(skipped), "lease_until": None}, "$inc": {"attempts": 1}})
    await _campaign_progress(job, accepted, errors, invalid, len(skipped))
    worker_state["sent_batches"] += 1
    return "sent"


async def _campaign_progress(job, accepted, errors, invalid, skipped):
    if not job.get("campaign_id"):
        return
    await c.db.notification_campaigns.update_one({"id": job["campaign_id"]},
        {"$inc": {"stats.accepted": accepted, "stats.errors": errors, "stats.invalid_tokens": invalid, "stats.skipped": skipped}})
    remaining = await c.db.notification_outbox.count_documents({"campaign_id": job["campaign_id"], "status": {"$in": ["pending", "sending"]}})
    if not remaining:
        # Only once the fan-out itself is complete (G04): while batches are still being queued, an empty outbox is not
        # "everything sent". (Campaigns queued by earlier builds carry no fan-out state and finish as before.)
        await c.db.notification_campaigns.update_one({"id": job["campaign_id"], "status": {"$in": ["queued", "sending"]}, "fanout.state": {"$ne": "pending"}},
                                                     {"$set": {"status": "sent", "completed_at": c.stamp()}})


async def claim_job():
    now = c.stamp()
    # Recover a batch whose worker died mid-send (lease expired) before claiming a new one.
    await c.db.notification_outbox.update_many({"status": "sending", "lease_until": {"$lt": now}}, {"$set": {"status": "pending"}})
    return await c.db.notification_outbox.find_one_and_update({"status": "pending", "next_attempt_at": {"$lte": now}},
        {"$set": {"status": "sending", "lease_until": (c.now() + timedelta(seconds=90)).isoformat()}},
        sort=[("created_at", 1)], projection={"_id": 0}, return_document=ReturnDocument.AFTER)


async def check_receipts(limit=20):
    cutoff = (c.now() - timedelta(minutes=RECEIPT_DELAY_MINUTES)).isoformat()
    jobs = await c.db.notification_outbox.find({"status": "sent", "receipts_checked_at": None, "sent_at": {"$lt": cutoff}},
                                               {"_id": 0}).sort("sent_at", 1).limit(limit).to_list(limit)
    for job in jobs:
        ids = [t["ticket_id"] for t in job.get("tickets", []) if t.get("ticket_id")]
        summary = {"ok": 0, "error": 0, "invalid_tokens": 0}
        if ids:
            try:
                receipts = await receipts_transport(ids)
            except Exception as exc:
                worker_state["last_error"] = type(exc).__name__
                continue
            by_ticket = {t["ticket_id"]: t for t in job["tickets"] if t.get("ticket_id")}
            for tid, receipt in receipts.items():
                if receipt.get("status") == "ok":
                    summary["ok"] += 1
                else:
                    summary["error"] += 1
                    if (receipt.get("details") or {}).get("error") == "DeviceNotRegistered" and tid in by_ticket:
                        summary["invalid_tokens"] += 1
                        device = await c.db.push_devices.find_one({"user_id": by_ticket[tid]["user_id"], "token": {"$regex": re.escape(by_ticket[tid]["token_tail"]) + "$"}}, {"_id": 0, "token": 1})
                        if device:
                            await _invalidate(device["token"], "DeviceNotRegistered")
        await c.db.notification_outbox.update_one({"id": job["id"]}, {"$set": {"receipts_checked_at": c.stamp(), "receipts": summary}})


async def tick():
    """One worker pass over every usable data scope: bounded number of batches per pass. Query alerts whose enqueue
    failed at creation time (durable `notify_state=pending` marker on the request, F06) are queued here, and campaigns
    whose fan-out was interrupted by a process stop (expired fan-out lease, G04) are resumed here."""
    from .queries import reconcile_pending_notifications
    for scope in c.scopes():
        with c.scoped(scope):
            await reconcile_pending_notifications()
            await recover_campaigns()
            for _ in range(10):
                job = await claim_job()
                if not job:
                    break
                await process_job(job)
            await check_receipts()
    worker_state["last_tick"] = c.stamp()


async def worker_loop(interval=5):
    worker_state["running"] = True
    try:
        while True:
            try:
                await tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                worker_state["last_error"] = type(exc).__name__
                log.warning("Notification worker pass failed: %s", type(exc).__name__)
            await asyncio.sleep(interval)
    finally:
        worker_state["running"] = False
