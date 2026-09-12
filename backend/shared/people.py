import base64
import re
import secrets

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument

from . import core as c
from .auth import check_challenge, issue, start_challenge

router = APIRouter(prefix="/api", tags=["People and integration"])


async def identity(ref):
    found = await c.db.users.find_one({"id": ref}, {"_id": 0})
    if not found:
        found = await c.by_phone(c.phone(ref))
    if not found:
        c.fail(404, "USER_NOT_FOUND", "Identity not found")
    return found


async def customer_ref(uid):
    """Customer routes address records by canonical ID only: an unknown ID is 404, never a phone parse error."""
    found = await c.db.users.find_one({"id": uid}, {"_id": 0})
    if not found:
        c.fail(404, "CUSTOMER_NOT_FOUND", "No customer exists with this canonical ID")
    return found


class StaffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str
    name: str = Field(min_length=1, max_length=120)
    role: str
    code: str = Field("", max_length=40)
    status: str = "active"


def status_value(value):
    value = "inactive" if value == "disabled" else value
    if value not in {"active", "inactive"}:
        c.fail(422, "INVALID_ACCOUNT_STATUS", "Use active or inactive for account status")
    return value


@router.get("/integrations/staff")
async def staff_list(role: str = "", status: str = "", user=Depends(c.admin)):
    query = {"role": {"$in": [*c.STAFF, "executive"]}}
    if role:
        normalized = c.role(role)
        query["role"] = {"$in": ["executive", "telecaller"]} if normalized == "telecaller" else normalized
    rows = [c.public_user(u) async for u in c.db.users.find(query, {"_id": 0}).sort([("name", 1), ("id", 1)])]
    if status:
        rows = [u for u in rows if u["status"] == status_value(status)]
    return {"users": rows}


@router.post("/integrations/staff")
async def staff_create(req: StaffCreate, user=Depends(c.admin)):
    number, role = c.phone(req.phone), c.role(req.role)
    if role not in c.STAFF:
        c.fail(422, "STAFF_ROLE_REQUIRED", "Select a staff role")
    async with c.lock("identity:" + number):
        old = await c.by_phone(number)
        if old:
            if c.role(old["role"]) == "customer":
                c.fail(409, "EXPLICIT_CONVERSION_REQUIRED", "Use the admin conversion operation; customer ID must be preserved")
            if c.role(old["role"]) != role:
                c.fail(409, "ROLE_CONFLICT", "Existing staff role differs; use an explicit audited update")
            return {"created": False, "user": c.public_user(old)}
        ts = c.stamp()
        doc = {"id": secrets.token_hex(16), "phone": number, "phone_normalized": number,
            "name": req.name.strip(), "role": role, "code": req.code, "customer_code": req.code,
            "account_status": status_value(req.status), "status": status_value(req.status),
            "session_version": 0, "created_at": ts, "updated_at": ts, "phone_verified": False,
            "identity_events": [{"type": "staff_created", "actor_id": user["id"], "at": ts}]}
        await c.db.users.insert_one(dict(doc))
        return {"created": True, "user": c.public_user(doc)}


async def last_admin_guard(old, new_role, new_status):
    if new_role != "admin" or new_status != "active":
        from .owner_admin import is_owner
        if is_owner(old):
            c.fail(409, "OWNER_ADMIN_PROTECTED", "The default owner administrator cannot be demoted or disabled")
    if c.role(old["role"]) == "admin" and (new_role != "admin" or new_status != "active"):
        admins = await c.db.users.find({"role": "admin", "id": {"$ne": old["id"]}}, {"_id": 0}).to_list(None)
        if not any(c.account_status(a) == "active" for a in admins):
            c.fail(409, "LAST_ADMIN", "The last usable administrator cannot be disabled or demoted")


@router.patch("/integrations/staff/{ref}")
async def staff_update(ref: str, updates: dict, user=Depends(c.admin)):
    if set(updates) - {"name", "role", "code", "customer_code", "status", "account_status", "phone"}:
        c.fail(422, "READ_ONLY_FIELD", "Only name, role, code and status may be changed")
    async with c.lock("staff-directory"):
        old = await identity(ref)
        if c.role(old["role"]) not in c.STAFF:
            c.fail(409, "EXPLICIT_CONVERSION_REQUIRED", "Use the explicit customer conversion operation")
        if "phone" in updates and c.phone(updates["phone"]) != c.phone(old["phone"]):
            c.fail(409, "PHONE_VERIFICATION_REQUIRED", "Phone changes require the authenticated verification flow")
        new_role = c.role(updates.get("role", old["role"]))
        new_status = status_value(updates.get("account_status", updates.get("status", c.account_status(old))))
        await last_admin_guard(old, new_role, new_status)
        fields = {"role": new_role, "account_status": new_status, "status": new_status, "updated_at": c.stamp()}
        if "name" in updates:
            if not str(updates["name"]).strip():
                c.fail(422, "NAME_REQUIRED", "Name cannot be blank")
            fields["name"] = str(updates["name"]).strip()[:120]
        if "code" in updates or "customer_code" in updates:
            fields["code"] = str(updates.get("code", updates.get("customer_code")))[:40]
            fields["customer_code"] = fields["code"]
        await c.db.users.update_one({"id": old["id"]}, {"$set": fields, "$inc": {"session_version": 1},
            "$push": {"identity_events": {"type": "staff_updated", "actor_id": user["id"],
                "old_role": c.role(old["role"]), "new_role": new_role, "old_status": c.account_status(old),
                "new_status": new_status, "at": c.stamp()}}})
        await c.db.session_families.update_many({"user_id": old["id"]}, {"$set": {"revoked": True}})
        return {"user": c.public_user(await identity(old["id"]))}


@router.delete("/integrations/staff/{ref}")
async def staff_disable(ref: str, user=Depends(c.admin)):
    return await staff_update(ref, {"status": "inactive"}, user)


class Conversion(BaseModel):
    role: str
    reason: str = Field(min_length=10, max_length=500)
    confirm_user_id: str


@router.post("/integrations/staff/{ref}/convert")
async def convert(ref: str, req: Conversion, user=Depends(c.admin)):
    async with c.lock("staff-directory"):
        old = await identity(ref)
        target = c.role(req.role)
        if req.confirm_user_id != old["id"] or target not in c.STAFF or c.role(old["role"]) != "customer":
            c.fail(409, "CONVERSION_CONFLICT", "Confirm the existing customer ID and a staff role")
        c.usable(old)
        await c.db.users.update_one({"id": old["id"], "role": "customer"}, {"$set": {"role": target, "updated_at": c.stamp()},
            "$inc": {"session_version": 1}, "$push": {"identity_events": {"type": "conversion", "at": c.stamp(),
                "actor_id": user["id"], "old_role": "customer", "new_role": target, "reason": req.reason}}})
        await c.db.session_families.update_many({"user_id": old["id"]}, {"$set": {"revoked": True}})
        return {"user": c.public_user(await identity(old["id"]))}


@router.post("/integrations/staff/{ref}/token", dependencies=[Depends(c.service_key)])
async def exchange(ref: str, user=Depends(c.staff)):
    other = await identity(ref)
    if other["id"] != user["id"]:
        c.fail(403, "SAME_SUBJECT_REQUIRED", "A service key cannot impersonate another staff member")
    return await issue(user, user["_session_id"])


@router.get("/executives")
async def executives(user=Depends(c.admin)):
    return {"executives": (await staff_list(user=user))["users"]}


@router.post("/executives")
async def legacy_create(req: StaffCreate, user=Depends(c.admin)):
    return (await staff_create(req, user))["user"]


@router.put("/executives/{ref}")
async def legacy_update(ref: str, updates: dict, user=Depends(c.admin)):
    return (await staff_update(ref, updates, user))["user"]


@router.delete("/executives/{ref}")
async def legacy_disable(ref: str, user=Depends(c.admin)):
    return await staff_disable(ref, user)


@router.get("/customers")
async def customers(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                    search: str = "", account_status: str = "", login_state: str = "",
                    onboarding_status: str = "", assigned_to: str = "", registered_from: str = "", registered_to: str = "",
                    login_from: str = "", login_to: str = "", user=Depends(c.admin)):
    query = {"role": "customer"}
    if search:
        query["$or"] = [{k: {"$regex": re.escape(search[:120]), "$options": "i"}}
                         for k in ("name", "phone", "shop_name", "location", "city")]
    if account_status:
        query["account_status"] = status_value(account_status)
    if login_state:
        query["first_mobile_login_at"] = {"$nin": [None, ""]} if login_state == "logged_in" else {"$in": [None, ""]}
    if onboarding_status:
        query["onboarding_status"] = onboarding_status
    if assigned_to:
        query["assigned_salesperson"] = {"$in": [None, ""]} if assigned_to == "unassigned" else assigned_to
    from .queries import date_bounds
    for field, lo, hi in [("registered_at", registered_from, registered_to), ("last_mobile_login_at", login_from, login_to)]:
        if lo or hi:
            lower, upper, _ = date_bounds(lo, hi)
            query[field] = {"$gte": lower, "$lt": upper}
    total = await c.db.users.count_documents(query)
    rows = await c.db.users.find(query, {"_id": 0}).sort([("created_at", -1), ("id", 1)]).skip((page-1)*limit).limit(limit).to_list(limit)
    return {"customers": [{**c.public_user(u), "number": (page-1)*limit+i+1} for i, u in enumerate(rows)],
            "total": total, "page": page, "limit": limit, "pages": (total+limit-1)//limit}


@router.get("/customers/search")
async def customer_search(q: str = Query("", max_length=120), user=Depends(c.billing)):
    """Static reward/billing lookup. Registered BEFORE /customers/{uid} so the literal `search`
    segment can never be handled as a customer reference (website dependency D2)."""
    term = q.strip()
    if len(term) < 2:
        return {"customers": [], "query": term, "limit": 20, "minimum_length": 2}
    pattern = {"$regex": re.escape(term), "$options": "i"}
    query = {"role": "customer", "account_status": {"$ne": "deleted"}, "status": {"$ne": "deleted"},
             "$or": [{k: pattern} for k in ("phone", "name", "customer_code", "code", "city", "location", "shop_name")]}
    rows = await c.db.users.find(query, {"_id": 0}).sort([("name", 1), ("id", 1)]).limit(20).to_list(20)
    return {"customers": [c.public_user(u) for u in rows], "query": term, "limit": 20, "minimum_length": 2}


@router.get("/customers/{uid}")
async def customer_detail(uid: str, user=Depends(c.admin)):
    person = await customer_ref(uid)
    queries = await c.db.requests.find({"user_id": person["id"]}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    notes = await c.db.telecaller_activity.find({"customer_id": person["id"]}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    return {**c.public_user(person), "queries": queries, "activity": notes, "detail_limit": 100,
            "complete_history": f"/api/requests?customer_id={person['id']}&status=all&sort=newest"}


@router.patch("/customers/{uid}")
async def customer_update(uid: str, updates: dict, user=Depends(c.admin)):
    allowed = {"name", "shop_name", "location", "city", "assigned_salesperson", "account_status", "status"}
    if set(updates) - allowed:
        c.fail(422, "READ_ONLY_FIELD", "Unsupported customer update fields")
    old = await customer_ref(uid)
    if c.role(old["role"]) != "customer" or c.account_status(old) == "deleted":
        c.fail(409, "CUSTOMER_STATE_CONFLICT", "Cannot edit this customer through this operation")
    fields = dict(updates)
    if fields.get("assigned_salesperson"):
        assignee = await identity(fields["assigned_salesperson"])
        c.usable(assignee)
        if c.role(assignee["role"]) != "telecaller":
            c.fail(422, "INVALID_ASSIGNEE", "Assign a currently active telecaller")
    if "account_status" in fields or "status" in fields:
        fields["account_status"] = fields["status"] = status_value(fields.get("account_status", fields.get("status")))
    for k in {"name", "shop_name", "location", "city"} & set(fields):
        if not isinstance(fields[k], str) or not fields[k].strip():
            c.fail(422, "PROFILE_REQUIRED", f"{k} cannot be blank")
        fields[k] = fields[k].strip()[:160]
    fields["updated_at"] = c.stamp()
    inc = {"profile_version": 1}
    if "account_status" in fields:
        inc["session_version"] = 1
    await c.db.users.update_one({"id": uid}, {"$set": fields, "$inc": inc,
        "$push": {"identity_events": {"type": "customer_updated", "actor_id": user["id"], "at": c.stamp(), "fields": sorted(updates)}}})
    return c.public_user(await customer_ref(uid))


async def erase(user, source):
    from .owner_admin import is_owner
    if is_owner(user):
        c.fail(409, "OWNER_ADMIN_PROTECTED", "The default owner administrator cannot be deleted; change OWNER_ADMIN_PHONE first")
    uid, number = user["id"], c.phone(user["phone"])
    ref = "DEL-" + uid
    # Tombstone and revocation happen BEFORE cleanup. Retried enrollment cannot resurrect it.
    await c.db.deleted_identities.update_one({"phone_hash": c.keyed(number)},
        {"$setOnInsert": {"user_id": uid, "deleted_at": c.stamp()}}, upsert=True)
    await c.db.users.update_one({"id": uid}, {"$set": {"account_status": "deleted", "status": "deleted"}, "$inc": {"session_version": 1}})
    await c.db.session_families.update_many({"user_id": uid}, {"$set": {"revoked": True}})
    await c.db.deletion_requests.update_one({"reference": ref}, {"$setOnInsert": {
        "id": ref, "reference": ref, "user_id": uid, "source": source, "requested_at": c.stamp()},
        "$set": {"status": "local_cleanup_pending"}}, upsert=True)
    await cleanup_deletion(uid, number, ref)
    return {"deleted": True, "reference": ref, "status": "external_erasure_pending",
            "detail": "Local profile anonymized; website/provider erasure requires acknowledgement"}


async def cleanup_deletion(uid, number, ref):
    for coll, query in (("cart", {"user_id": uid}), ("wishlists", {"user_id": uid}),
        ("ai_chat_history", {"$or": [{"user_id": uid}, {"session_id": f"jeweller-{uid}"}]}),
        ("telecaller_activity", {"customer_id": uid}), ("analytics_events", {"user_id": uid}),
        ("reward_transactions", {"user_id": uid}), ("otp_challenges", {"phone": number}),
        ("auth_grants", {"phone": number}), ("sms_log", {"phone": number}),
        ("refresh_tokens", {"user_id": uid}), ("ai_reports", {"user_id": uid})):
        await c.db[coll].delete_many(query)
    # Preserve anonymous operational totals, not personal/free-text trade snapshots.
    async for q in c.db.requests.find({"user_id": uid}, {"_id": 0}):
        events = [{k: v for k, v in e.items() if k not in {"notes", "old", "new", "actor_name"}}
                  for e in q.get("events", [])]
        await c.db.requests.update_one({"id": q["id"]}, {"$set": {"user_name": "Deleted customer",
            "user_phone": "", "user_city": "", "shop_name": "", "location": "", "customer_snapshot": {},
            "notes": "", "admin_notes": "", "notes_history": [], "events": events, "anonymized": True},
            "$unset": {"customer_name": "", "customer_phone": "", "customer_shop_name": "", "customer_location": "",
                       "cart_items": "", "preferred_time": "", "category": "", "payload_hash": ""}})
    await c.db.users.replace_one({"id": uid}, {"id": uid, "phone": f"deleted:{uid}", "role": "customer", "name": "Deleted customer",
        "account_status": "deleted", "status": "deleted", "deleted_at": c.stamp(), "onboarding_status": "deleted"})
    await c.db.deletion_requests.update_one({"reference": ref}, {"$set": {
        "status": "external_erasure_pending", "local_completed_at": c.stamp()},
        "$unset": {"phone": "", "name": "", "shop_name": ""}})
    await c.db.integration_outbox.update_one({"id": ref}, {"$setOnInsert": {"id": ref, "type": "account_erased",
        "user_id": uid, "created_at": c.stamp(), "status": "pending", "required_acknowledgements": ["website", "sms_provider", "ai_provider"]}}, upsert=True)


class DeleteConfirm(BaseModel):
    otp: str = Field(pattern=r"^[0-9]{4}$")
    challenge_id: str | None = None


@router.post("/auth/delete-account/request")
async def delete_start(request: Request, user=Depends(c.allow("customer"))):
    return await start_challenge(c.phone(user["phone"]), "account_deletion", user["id"], request)


@router.post("/auth/delete-account/confirm")
async def delete_confirm(req: DeleteConfirm, user=Depends(c.allow("customer"))):
    await check_challenge(c.phone(user["phone"]), "account_deletion", user["id"], req.otp, req.challenge_id)
    return await erase(user, "app")


@router.delete("/integrations/customers/{number}", dependencies=[Depends(c.integration_key)])
async def web_delete(number: str, x_verification_grant: str | None = Header(None)):
    normalized = c.phone(number)
    if not x_verification_grant:
        c.fail(401, "VERIFICATION_REQUIRED", "Deletion requires a canonical deletion verification grant")
    async with c.lock("identity:" + normalized):
        grant = await c.db.auth_grants.find_one({"hash": c.digest(x_verification_grant), "phone": normalized,
            "purpose": "deletion", "used": False, "expires_at": {"$gt": c.now()}}, {"_id": 0})
        if not grant:
            c.fail(401, "GRANT_INVALID", "Deletion verification grant expired or invalid")
        user = await c.by_phone(normalized)
        if not user or c.role(user["role"]) != "customer":
            c.fail(404, "USER_NOT_FOUND", "Customer not found")
        return await erase(user, "website")


async def outbox_consumer(x_integration_key: str | None = Header(None)):
    """The consumer identity is derived from WHICH server credential authenticated, never from a
    query parameter. The enrollment integration credential belongs to the website."""
    await c.integration_key(x_integration_key)
    return "website"


def encode_cursor(doc):
    return base64.urlsafe_b64encode(f"{doc.get('created_at', '')}|{doc['id']}".encode()).decode().rstrip("=")


def decode_cursor(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_at, event_id = raw.split("|", 1)
    except (ValueError, UnicodeDecodeError):
        c.fail(422, "INVALID_CURSOR", "Use the after cursor returned by the previous page")
    return created_at, event_id


@router.get("/integrations/deletions")
async def deletion_outbox(limit: int = Query(100, ge=1, le=500), after: str = "", consumer: str = Depends(outbox_consumer)):
    """Pending erasure events NOT yet acknowledged by the calling consumer, in stable
    (created_at, id) order with an opaque cursor. Other providers' pending states are untouched."""
    query = {"type": "account_erased", "status": "pending", "acknowledged": {"$ne": consumer}}
    if after:
        created_at, event_id = decode_cursor(after)
        query["$or"] = [{"created_at": {"$gt": created_at}}, {"created_at": created_at, "id": {"$gt": event_id}}]
    rows = await c.db.integration_outbox.find(query, {"_id": 0}).sort([("created_at", 1), ("id", 1)]).limit(limit + 1).to_list(limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    remaining = await c.db.integration_outbox.count_documents({"type": "account_erased", "status": "pending", "acknowledged": {"$ne": consumer}})
    return {"events": rows, "consumer": consumer, "limit": limit, "has_more": has_more,
            "next_cursor": encode_cursor(rows[-1]) if has_more and rows else None, "remaining_for_consumer": remaining}


@router.post("/integrations/deletions/{event_id}/ack")
async def deletion_ack(event_id: str, consumer: str = Depends(outbox_consumer)):
    """Idempotent, consumer-specific acknowledgement. It never marks the global erasure complete;
    status stays pending until every required acknowledgement is recorded."""
    doc = await c.db.integration_outbox.find_one_and_update({"id": event_id, "type": "account_erased"},
        {"$addToSet": {"acknowledged": consumer}, "$set": {f"acknowledged_at.{consumer}": c.stamp()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not doc:
        c.fail(404, "EVENT_NOT_FOUND", "Unknown erasure event")
    required = set(doc.get("required_acknowledgements", []))
    complete = required and required <= set(doc.get("acknowledged", []))
    if complete and doc.get("status") == "pending":
        await c.db.integration_outbox.update_one({"id": event_id}, {"$set": {"status": "acknowledged", "completed_at": c.stamp()}})
    return {"acknowledged": consumer, "event_id": event_id, "acknowledged_by": sorted(set(doc.get("acknowledged", []))),
            "required_acknowledgements": sorted(required), "all_acknowledged": bool(complete)}


async def deletion_retry_loop():
    """Durable local cleanup retries; provider acknowledgement remains a separate operation."""
    import asyncio
    import logging
    while True:
        for data_scope in c.scopes():
            try:
                with c.scoped(data_scope):
                    async for deletion in c.db.deletion_requests.find({"status": "local_cleanup_pending"}, {"_id": 0}).limit(10):
                        async with c.lock("deletion:" + deletion["user_id"], seconds=120):
                            person = await c.db.users.find_one({"id": deletion["user_id"]}, {"_id": 0}) or {}
                            number = person.get("phone", "")
                            if number.startswith("deleted:"):
                                number = ""
                            await cleanup_deletion(deletion["user_id"], number, deletion["reference"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.getLogger("shared").warning("Deletion retry deferred: %s", type(exc).__name__)
        await asyncio.sleep(60)