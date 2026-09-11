import re
import secrets

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field

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
                    onboarding_status: str = "", assigned_to: str = "", user=Depends(c.admin)):
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
        query["assigned_salesperson"] = assigned_to
    total = await c.db.users.count_documents(query)
    rows = await c.db.users.find(query, {"_id": 0}).sort([("created_at", -1), ("id", 1)]).skip((page-1)*limit).limit(limit).to_list(limit)
    return {"customers": [{**c.public_user(u), "number": (page-1)*limit+i+1} for i, u in enumerate(rows)],
            "total": total, "page": page, "limit": limit, "pages": (total+limit-1)//limit}


@router.get("/customers/{uid}")
async def customer_detail(uid: str, user=Depends(c.admin)):
    person = await identity(uid)
    queries = await c.db.requests.find({"user_id": person["id"]}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    notes = await c.db.telecaller_activity.find({"customer_id": person["id"]}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    return {**c.public_user(person), "queries": queries, "activity": notes, "detail_limit": 100}


@router.patch("/customers/{uid}")
async def customer_update(uid: str, updates: dict, user=Depends(c.admin)):
    allowed = {"name", "shop_name", "location", "city", "assigned_salesperson", "account_status", "status"}
    if set(updates) - allowed:
        c.fail(422, "READ_ONLY_FIELD", "Unsupported customer update fields")
    old = await identity(uid)
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
    return c.public_user(await identity(uid))


async def erase(user, source):
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


@router.get("/integrations/deletions", dependencies=[Depends(c.integration_key)])
async def deletion_outbox():
    rows = await c.db.integration_outbox.find({"type": "account_erased", "status": "pending"}, {"_id": 0}).limit(100).to_list(100)
    return {"events": rows}


@router.post("/integrations/deletions/{event_id}/ack", dependencies=[Depends(c.integration_key)])
async def deletion_ack(event_id: str):
    await c.db.integration_outbox.update_one({"id": event_id}, {"$addToSet": {"acknowledged": "website"}})
    return {"acknowledged": "website", "event_id": event_id}


async def deletion_retry_loop():
    """Durable local cleanup retries; provider acknowledgement remains a separate operation."""
    import asyncio
    import logging
    while True:
        try:
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