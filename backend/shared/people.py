import asyncio
import base64
import re
import secrets
import time

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from . import core as c
from . import provider_erasure as pe
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
            c.fail(409, "PHONE_CHANGE_OPERATION_REQUIRED", "Login numbers change through the audited administrator operation "
                   "(POST /integrations/staff/{ref}/phone/preview then /phone) or the staff member's own verified self-service flow")
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
        await c.db.refresh_tokens.update_many({"user_id": old["id"], "used": False}, {"$set": {"used": True}})
        released = 0
        if new_status != "active" or new_role not in {"admin", "telecaller"}:
            from .notifications import detach_devices
            from .queries import release_assignments
            await detach_devices(old["id"], "account_disabled" if new_status != "active" else "role_changed")
            released = await release_assignments(old["id"], user, f"Staff account {'disabled' if new_status != 'active' else 'role changed to ' + new_role} by administrator")
        elif new_role != c.role(old["role"]):
            from .notifications import detach_devices
            await detach_devices(old["id"], "role_changed")
        return {"user": c.public_user(await identity(old["id"])), "sessions_revoked": True, "queries_released": released}


@router.delete("/integrations/staff/{ref}")
async def staff_disable(ref: str, user=Depends(c.admin)):
    """LEGACY alias kept for already-deployed website consumers: this DISABLES (reversible) and never deletes.
    Real deletion is the explicit, step-up-authenticated POST /integrations/staff/{ref}/delete."""
    result = await staff_update(ref, {"status": "inactive"}, user)
    return {**result, "disabled": True, "deleted": False, "note": "Reversible disable. Use POST /integrations/staff/{ref}/delete to delete the account."}


class AccountDeletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=500)
    confirm_user_id: str
    confirm_phone_last4: str = Field(min_length=4, max_length=4)


async def admin_delete(ref, req: AccountDeletion, user, expected_roles):
    async with c.lock("staff-directory", wait_seconds=5):
        old = await identity(ref)
        if req.confirm_user_id != old["id"]:
            c.fail(409, "CONFIRMATION_REQUIRED", "Confirm the account's canonical ID and the last four digits of its number")
        if c.account_status(old) == "deleted":
            # Idempotent retry after a completed or interrupted deletion (the tombstone no longer carries the number).
            existing = await c.db.deletion_requests.find_one({"reference": "DEL-" + old["id"]}, {"_id": 0})
            return {"deleted": True, "already_deleted": True, "reference": "DEL-" + old["id"], "status": (existing or {}).get("status"),
                    "cleanup": pe.cleanup_of(existing) if existing else None}
        if str(old.get("phone", ""))[-4:] != req.confirm_phone_last4:
            c.fail(409, "CONFIRMATION_REQUIRED", "Confirm the account's canonical ID and the last four digits of its number")
        if old["id"] == user["id"]:
            c.fail(409, "SELF_DELETION_DENIED", "Administrators cannot delete their own account here")
        role = c.role(old["role"])
        if role not in expected_roles:
            c.fail(409, "ROLE_MISMATCH", "Use the matching customer or staff deletion operation")
        await last_admin_guard(old, "customer", "inactive")
        from .notifications import detach_devices
        from .queries import release_assignments
        released = await release_assignments(old["id"], user, "Staff account deleted by administrator") if role in c.STAFF else 0
        await detach_devices(old["id"], "account_deleted")
        await c.db.users.update_one({"id": old["id"]}, {"$push": {"identity_events": {"type": "admin_deletion", "actor_id": user["id"],
            "reason": req.reason, "role": role, "at": c.stamp()}}})
        result = await erase(old, "admin")
        await c.db.identity_audit.insert_one({"type": "admin_account_deletion", "target_id": old["id"], "target_role": role, "actor_id": user["id"],
                                              "actor_role": user["role"], "reason": req.reason, "at": c.stamp(), "queries_released": released})
        return {**result, "queries_released": released, "reference_role": role}


@router.post("/integrations/staff/{ref}/delete")
async def staff_delete(ref: str, req: AccountDeletion, user=Depends(c.recent_admin)):
    """Actual deletion of a staff account (telecaller, billing, upload executive, non-owner administrator): sessions and
    devices revoked, open queries released to the shared queue, personal data removed/anonymized through the same
    erasure workflow as customers, completion attribution kept in the immutable ledger. Idempotent on retry."""
    return await admin_delete(ref, req, user, c.STAFF)


@router.post("/customers/{uid}/delete")
async def customer_delete(uid: str, req: AccountDeletion, user=Depends(c.recent_admin)):
    """Administrator deletion of a customer account through the existing erasure workflow (tombstone, anonymized
    queries, provider-erasure ledger, website outbox event). Re-registration with the same number is a NEW account."""
    await customer_ref(uid)
    return await admin_delete(uid, req, user, {"customer"})


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


# ---- Administrator-controlled login-number change for ORDINARY staff (telecaller / billing) -------------------------
# The staff member keeps the same canonical ID, role, code, assignments and history: only the login number changes.
# Nothing here merges people. A number that belongs to a customer is offered as an explicit PROMOTION of that customer
# (their own account, via the existing conversion operation); a number owned by another staff account is refused.

class StaffPhonePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_phone: str


class StaffPhoneChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_phone: str
    reason: str = Field(min_length=10, max_length=500)
    confirm_user_id: str
    expected_phone: str
    idempotency_key: str = Field(min_length=8, max_length=120)
    preview_token: str = Field(min_length=8, max_length=200)


PREVIEW_MINUTES = 10


def preview_token(target_id, current, number, expires):
    """Binds the confirmation an administrator saw to the exact target account, its current number and the new number."""
    return f"{expires}.{c.keyed(f'staff-phone-preview:{target_id}:{current}:{number}:{expires}')}"


def check_preview_token(token, target_id, current, number):
    expires, _, signature = str(token).partition(".")
    if expires.isdigit() and int(expires) < int(c.now().timestamp()):
        c.fail(409, "PREVIEW_EXPIRED", "The confirmation has expired; check the number again")
    if not expires.isdigit() or not secrets.compare_digest(preview_token(target_id, current, number, int(expires)), token):
        c.fail(409, "PREVIEW_MISMATCH", "The confirmation you saw described a different account or number; check the number again")


def phone_change_target(old):
    """Only ordinary staff accounts are renumbered by an administrator."""
    from .owner_admin import is_owner
    role = c.role(old["role"])
    if role == "customer":
        c.fail(409, "EXPLICIT_CONVERSION_REQUIRED", "This is a customer account; use the explicit promotion operation")
    if is_owner(old):
        c.fail(409, "OWNER_ADMIN_PROTECTED", "The owner administrator's login number is never changed by another administrator")
    if role == "admin":
        c.fail(409, "ADMIN_SELF_SERVICE_REQUIRED", "Administrators change their own number through the verified self-service flow")
    return role


def person(user, number=None):
    return {"id": user["id"], "name": user.get("name") or "", "role": c.role(user["role"]), "account_status": c.account_status(user),
            "masked_phone": c.phone_masked(number or user.get("phone") or ""), "code": user.get("code", user.get("customer_code", ""))}


async def classify_number(number, target):
    """Who owns the requested number relative to the staff member being edited."""
    found = await c.by_phone(number)
    if not found:
        return {"status": "available"}
    if found["id"] == target["id"]:
        return {"status": "unchanged"}
    if c.role(found["role"]) == "customer":
        return {"status": "customer", "customer": person(found, number)}
    return {"status": "staff", "owner": person(found, number)}


@router.post("/integrations/staff/{ref}/phone/preview")
async def staff_phone_preview(ref: str, req: StaffPhonePreview, user=Depends(c.admin)):
    old = await identity(ref)
    phone_change_target(old)
    number = c.phone(req.new_phone)
    result = await classify_number(number, old)
    result.update(staff=person(old), new_phone=number, new_phone_display=c.phone_display(number))
    if result["status"] == "available":
        expires = int(c.now().timestamp()) + PREVIEW_MINUTES * 60
        result.update(preview_token=preview_token(old["id"], c.phone(old["phone"]), number, expires), preview_expires_in=PREVIEW_MINUTES * 60)
        result["outcome"] = (f"{old.get('name') or 'This staff member'} keeps the same account, role, code, assignments and history. "
            "Only the login number changes. All their current sessions (app and website) are signed out, the old number can no "
            "longer sign in to this account, and the new number must be verified by OTP at the next sign-in.")
    elif result["status"] == "customer":
        result["outcome"] = (f"This number belongs to existing customer {result['customer']['name'] or '(no name)'}. Promoting keeps the "
            f"customer's own account and history and gives it the chosen staff role. {old.get('name') or 'The staff member being edited'} "
            "is NOT changed and keeps their current number. If these two records are the same person, stop here: identity "
            "reconciliation needs an explicit owner decision - nothing is merged automatically.")
    elif result["status"] == "staff":
        result["outcome"] = (f"This number already belongs to staff member {result['owner']['name'] or '(no name)'} "
            f"({result['owner']['role'].replace('_', ' ')}). Disable or renumber that account first; two staff accounts cannot share a login number.")
    else:
        result["outcome"] = "This is already the staff member's current login number."
    return result


OPERATION_WAIT_SECONDS = 8


async def operation_replay(doc):
    return {**doc["result"], "replayed": True}


async def operation_applied(doc):
    """The account update is the point of no return; it carries the operation key inside the pushed identity event."""
    return bool(doc.get("target_id")) and await c.db.users.find_one(
        {"id": doc["target_id"], "identity_events": {"$elemMatch": {"operation_key": doc["key"]}}}, {"_id": 0, "id": 1}) is not None


async def finish_phone_change(doc, recovered=False):
    """Every step after the account update is idempotent, so an interrupted operation (audit or replay record not
    written) is completed by any later request that carries the same key or touches the same staff member."""
    target_id, key = doc["target_id"], doc["key"]
    await c.db.session_families.update_many({"user_id": target_id}, {"$set": {"revoked": True}})
    await c.db.refresh_tokens.update_many({"user_id": target_id, "used": False}, {"$set": {"used": True}})
    if not await c.db.identity_audit.find_one({"operation_key": key}, {"_id": 0, "operation_key": 1}):
        await c.db.identity_audit.insert_one({**doc["event"], "target_id": target_id, "target_role": doc["target_role"],
                                              "actor_role": doc["actor_role"], "operation_key": key, "surface": "admin_staff_phone_change"})
    fresh = await identity(target_id)
    body = {"user": c.public_user(fresh), "old_phone_masked": c.phone_masked(doc["old_phone"]), "new_phone": doc["new_phone"],
            "new_phone_display": c.phone_display(doc["new_phone"]), "verification_required": True, "sessions_revoked": True}
    await c.db.identity_operations.update_one({"key": key}, {"$set": {"state": "done", "result": body, "finished_at": c.stamp()}})
    return {**body, "recovered": True} if recovered else body


async def reconcile_phone_operations(target_id):
    """Complete earlier operations on this staff member whose account update succeeded but whose bookkeeping did not."""
    async for doc in c.db.identity_operations.find({"target_id": target_id, "state": "validated"}, {"_id": 0}):
        if await operation_applied(doc):
            await finish_phone_change(doc, recovered=True)


@router.post("/integrations/staff/{ref}/phone")
async def staff_phone_change(ref: str, req: StaffPhoneChange, user=Depends(c.recent_admin)):
    number = c.phone(req.new_phone)
    key = c.digest(f"{user['id']}:{req.idempotency_key}")
    payload_hash = c.digest(req.model_dump_json())
    # Reserve the key BEFORE any check: simultaneous requests with the same key never run the operation twice - the
    # later one waits for the first and returns its result (a refusal releases the key, so the waiter then runs the
    # same validation itself and receives the same refusal).
    reserved_here = False
    deadline = time.monotonic() + OPERATION_WAIT_SECONDS
    while not reserved_here:
        try:
            await c.db.identity_operations.insert_one({"key": key, "payload_hash": payload_hash, "state": "pending", "actor_id": user["id"],
                                                       "at": c.stamp(), "expires_at": c.now() + c.timedelta(days=7)})
            reserved_here = True
        except DuplicateKeyError:
            prior = await c.db.identity_operations.find_one({"key": key}, {"_id": 0})
            if not prior:
                continue
            if prior["payload_hash"] != payload_hash:
                c.fail(409, "IDEMPOTENCY_MISMATCH", "This idempotency key was already used for a different request")
            if prior["state"] == "done":
                return await operation_replay(prior)
            if time.monotonic() >= deadline:
                break  # interrupted earlier request: the locked section below recovers or completes it
            await asyncio.sleep(0.2)
    applied = False
    try:
        async with c.lock("staff-directory", wait_seconds=5):
            async with c.lock("identity:" + number, wait_seconds=5):
                current_op = await c.db.identity_operations.find_one({"key": key}, {"_id": 0})
                if current_op and current_op["state"] == "done":
                    return await operation_replay(current_op)
                if current_op and await operation_applied(current_op):
                    applied = True
                    return await complete_or_503(current_op, recovered=True)
                old = await identity(ref)
                await reconcile_phone_operations(old["id"])
                role = phone_change_target(old)
                if req.confirm_user_id != old["id"]:
                    c.fail(409, "CONFIRMATION_REQUIRED", "Confirm the staff member's canonical ID")
                current = c.phone(old["phone"])
                if c.phone(req.expected_phone) != current:
                    c.fail(409, "VERSION_CONFLICT", "The staff member's number changed since you opened the form; review and retry")
                if number == current:
                    c.fail(409, "PHONE_UNCHANGED", "This is already the current login number")
                owner = await classify_number(number, old)
                if owner["status"] == "customer":
                    c.fail(409, "CUSTOMER_PROMOTION_REQUIRED", "This number belongs to an existing customer. Promote that customer "
                           "to staff explicitly (their own account) or choose another number; the staff member being edited is unchanged")
                if owner["status"] == "staff":
                    c.fail(409, "PHONE_OWNED_BY_STAFF", f"This number already belongs to staff member {owner['owner']['name'] or '(no name)'}; "
                           "disable or renumber that account first")
                check_preview_token(req.preview_token, old["id"], current, number)
                ts = c.stamp()
                event = {"type": "staff_phone_changed", "actor_id": user["id"], "old_phone": old["phone"], "new_phone": number,
                         "reason": req.reason, "at": ts, "operation_key": key}
                intent = {"state": "validated", "target_id": old["id"], "target_role": role, "actor_role": user["role"],
                          "old_phone": old["phone"], "new_phone": number, "event": event}
                await c.db.identity_operations.update_one({"key": key}, {"$set": intent})
                try:
                    result = await c.db.users.update_one(
                        {"id": old["id"], "phone": old["phone"], "session_version": old.get("session_version", 0)},
                        {"$set": {"phone": number, "phone_normalized": number, "phone_verified": False, "updated_at": ts},
                         "$unset": {"verified_at": ""}, "$inc": {"session_version": 1, "profile_version": 1},
                         "$push": {"identity_events": event}})
                except DuplicateKeyError:
                    c.fail(409, "PHONE_CONFLICT", "This number was claimed by another account a moment ago; refresh and retry")
                if not result.modified_count:
                    c.fail(409, "VERSION_CONFLICT", "The staff record changed concurrently; review and retry")
                applied = True
                return await complete_or_503({"key": key, **intent})
    finally:
        if reserved_here and not applied:
            # refused before any change: release the key so a corrected retry is not answered with a stale replay
            await c.db.identity_operations.delete_one({"key": key, "state": {"$in": ["pending", "validated"]}})


async def complete_or_503(doc, recovered=False):
    """Every existing session of the affected account ends (app, website portal, refresh tokens) and the audit/replay
    records are written; if that bookkeeping fails the change itself stands and the caller is told how to finish it."""
    try:
        return await finish_phone_change(doc, recovered=recovered)
    except Exception:
        c.fail(503, "OPERATION_INCOMPLETE", "The login number was changed but the audit record could not be completed; "
               "submit again with the same idempotency key to finish the operation")


@router.get("/executives")
async def executives(status: str = "", user=Depends(c.admin)):
    """Legacy panel route: every staff account WITH its account status (disabled accounts stay visible so they can be
    re-enabled); `status=active|inactive` narrows the list."""
    return {"executives": (await staff_list("", status, user))["users"]}


@router.post("/executives")
async def legacy_create(req: StaffCreate, user=Depends(c.admin)):
    try:
        result = await staff_create(req, user)
    except c.HTTPException as exc:
        if isinstance(exc.detail, dict) and exc.detail.get("code") == "EXPLICIT_CONVERSION_REQUIRED":
            existing = await c.by_phone(c.phone(req.phone))
            raise c.HTTPException(409, {**exc.detail, "detail": "This number belongs to an existing customer. Promote that customer "
                                  "explicitly (their account, history and ID are kept) instead of creating a second person.",
                                  "customer": {"id": existing["id"], "name": existing.get("name", "")} if existing else {}})
        raise
    return {**result["user"], "created": result["created"]}


@router.put("/executives/{ref}")
async def legacy_update(ref: str, updates: dict, user=Depends(c.admin)):
    result = await staff_update(ref, updates, user)
    return {**result["user"], "sessions_revoked": result["sessions_revoked"], "queries_released": result["queries_released"]}


@router.delete("/executives/{ref}")
async def legacy_disable(ref: str, user=Depends(c.admin)):
    """DISABLES (reversible). Never deletes: actual deletion is POST /integrations/staff/{ref}/delete."""
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
    if fields.get("account_status") == "inactive":
        # Disabling blocks further sign-in immediately: sessions, refresh tokens and this account's devices are cut.
        await c.revoke(uid)
    return c.public_user(await customer_ref(uid))


async def erase(user, source):
    from .owner_admin import is_owner
    if is_owner(user):
        c.fail(409, "OWNER_ADMIN_PROTECTED", "The default owner administrator cannot be deleted; change OWNER_ADMIN_PHONE first")
    uid, number = user["id"], c.phone(user["phone"])
    ref = "DEL-" + uid
    # Which providers hold this account's data is recorded BEFORE the cleanup deletes the evidence. Their entries start
    # as not_requested (outstanding) - the ledger, not the website acknowledgement, tracks provider erasure.
    providers = await pe.snapshot(user, uid, number)
    # Tombstone and revocation happen BEFORE cleanup. Retried enrollment cannot resurrect it.
    # Latest deletion wins: a grant issued before this moment can never resurrect the account (auth.stale_after_deletion);
    # a fresh OTP after it is the person's explicit new sign-up and starts a new account.
    await c.db.deleted_identities.update_one({"phone_hash": c.keyed(number)},
        {"$set": {"user_id": uid, "deleted_at": c.stamp()}}, upsert=True)
    await c.db.users.update_one({"id": uid}, {"$set": {"account_status": "deleted", "status": "deleted"}})
    await c.revoke(uid)  # session version, families, refresh tokens and push devices
    await c.db.deletion_requests.update_one({"reference": ref}, {"$setOnInsert": {
        "id": ref, "reference": ref, "user_id": uid, "source": source, "requested_at": c.stamp(), "providers": providers},
        "$set": {"status": "local_cleanup_pending"}}, upsert=True)
    await cleanup_deletion(uid, number, ref)
    deletion = await c.db.deletion_requests.find_one({"reference": ref}, {"_id": 0})
    return {"deleted": True, "reference": ref, "status": "external_erasure_pending",
            "cleanup": pe.cleanup_of(deletion), "provider_erasure": pe.summary(deletion.get("providers")),
            "detail": "Data held by the app deleted or anonymized now; the enrolment website's erasure acknowledgement is pending. "
                      "Provider-held copies (SMS delivery logs, AI provider/gateway) are tracked separately in the provider-erasure "
                      "ledger and are NOT erased by this request; a manual request to each provider is recorded there.",
            "erasure": await erasure_report(uid)}


# The only outbox consumer that can acknowledge an erasure event is the enrolment website (its integration credential).
REQUIRED_ACKNOWLEDGEMENTS = ["website"]


async def mark_cleanup_completed(ref):
    """App + website cleanup done. Touches ONLY the cleanup outcome - provider ledger entries keep their own states."""
    ts = c.stamp()
    return (await c.db.deletion_requests.update_one({"reference": ref, "status": "external_erasure_pending"},
        {"$set": {"status": "cleanup_completed", "cleanup.website_acknowledged_at": ts, "cleanup.completed_at": ts}})).modified_count


async def reconcile_outbox_acknowledgements():
    """One-shot, idempotent correction for erasure events written by builds before 14 Sep 2026, which required
    acknowledgements from the SMS and AI providers that can never arrive. Requirements are set to the website only;
    events the website has already acknowledged complete the CLEANUP outcome. Historical deletion requests are then
    migrated to the two-outcome model (provider_erasure.reconcile) with every provider state preserved as outstanding."""
    fixed = (await c.db.integration_outbox.update_many(
        {"type": "account_erased", "required_acknowledgements": {"$ne": REQUIRED_ACKNOWLEDGEMENTS}},
        {"$set": {"required_acknowledgements": REQUIRED_ACKNOWLEDGEMENTS}})).modified_count
    completed = 0
    async for event in c.db.integration_outbox.find({"type": "account_erased", "status": "pending", "acknowledged": "website"}, {"_id": 0, "id": 1}):
        await c.db.integration_outbox.update_one({"id": event["id"], "status": "pending"}, {"$set": {"status": "acknowledged", "completed_at": c.stamp()}})
        await mark_cleanup_completed(event["id"])
        completed += 1
    return {"requirements_corrected": fixed, "cleanup_completed": completed, **await pe.reconcile()}


# Personal-data locations covered by local cleanup. `analytics` is the legacy event collection the app wrote
# before the analytics_events rename; both are purged so old rows never survive a deletion.
PERSONAL_COLLECTIONS = (("cart", "user_id"), ("wishlists", "user_id"), ("telecaller_activity", "customer_id"),
                        ("analytics_events", "user_id"), ("analytics", "user_id"), ("reward_transactions", "user_id"),
                        ("refresh_tokens", "user_id"), ("ai_reports", "user_id"), ("push_devices", "user_id"),
                        ("notifications", "user_id"), ("product_impressions", "user_id"), ("discovery_sessions", "user_id"),
                        ("discovery_cursors", "user_id"))


EXTERNAL_DETAIL = {
    "object_storage": "Customers cannot upload photos or files; catalogue media is uploaded by staff and belongs to the business. "
                      "Any object owned by a deleted account is detached and access-revoked; byte erasure is not provided by this storage adapter.",
    "ai_provider": "Only message text typed by the user, earlier turns of the same conversation and a fixed system instruction "
                   "were transmitted (no phone, name or account identifier is attached; user-typed text is sent as written). "
                   "No per-user provider deletion API exists. Provider retention follows the provider's own policy and is not proven erased.",
    "sms_provider": "Delivery logs for the one-time codes sent to the number are held by the provider under its own terms and are not erased by this request.",
}


async def erasure_report(uid):
    """Truthful post-deletion inventory: what is proven gone locally, what is anonymized, and - per provider - the
    ledger state of the manual erasure request (not_requested / requested / confirmed / refused / no_procedure /
    not_applicable). Only `confirmed` is an erased copy; the website acknowledgement is a separate outcome."""
    remaining = {coll: await c.db[coll].count_documents({field: uid}) for coll, field in PERSONAL_COLLECTIONS}
    remaining["ai_chat_history"] = await c.db.ai_chat_history.count_documents({"$or": [{"user_id": uid}, {"session_id": f"jeweller-{uid}"}]})
    remaining["request_completions_with_personal_data"] = await c.db.request_completions.count_documents({"customer_id": uid, "customer_anonymized": {"$ne": True}})
    remaining["notification_outbox_unsent_messages"] = await c.db.notification_outbox.count_documents({"status": {"$in": ["pending", "failed"]}, "messages._user_id": uid})
    media = await c.db.media_assets.count_documents({"owner_id": uid})
    deletion = await c.db.deletion_requests.find_one({"reference": "DEL-" + uid}, {"_id": 0, "providers": 1, "status": 1}) or {}
    ledger = deletion.get("providers") or {}
    external = {}
    for key, meta in pe.PROVIDER_META.items():
        state = (ledger.get(key) or {}).get("state", "not_requested")
        external[key] = {"provider": meta["provider"], "delete_api": False, "erasure": state, "erasure_completed": state == "confirmed",
                         "requested_at": (ledger.get(key) or {}).get("requested_at"), "outcome": (ledger.get(key) or {}).get("outcome"),
                         "retention_exception": (ledger.get(key) or {}).get("retention_exception"),
                         "procedure": meta["procedure"], "detail": EXTERNAL_DETAIL[key]}
    external["object_storage"]["personal_uploads_supported_by_app"] = False
    external["website"] = {"acknowledgement": "acknowledged" if deletion.get("status") == "cleanup_completed" else
                           "pending until the enrollment website acknowledges the erasure event",
                           "implies_provider_erasure": False}
    return {"local_personal_records_remaining": sum(remaining.values()), "by_collection": remaining,
            "requests_anonymized": await c.db.requests.count_documents({"user_id": uid, "anonymized": True}),
            "personal_media_objects": media,
            "provider_erasure": pe.summary(ledger),
            "retained_by_app": {
                "deleted_identities": "keyed hash of the phone number + canonical ID + deletion time (blocks silent re-enrolment)",
                "deletion_requests": "reference, canonical ID, source, timestamps, cleanup status and the provider-erasure ledger (no name/phone)",
                "requests": "anonymized enquiry rows: type, status, dates, assignee (name/phone/shop/notes blanked)",
                "request_completions": "completion ledger rows: completing staff member, time, request type, outcome (customer name/shop blanked)",
                "integration_outbox": "account_erased event for the website, kept until acknowledged"},
            "external": external}


async def cleanup_deletion(uid, number, ref):
    for coll, field in PERSONAL_COLLECTIONS:
        await c.db[coll].delete_many({field: uid})
    await c.db.ai_chat_history.delete_many({"$or": [{"user_id": uid}, {"session_id": f"jeweller-{uid}"}]})
    for coll, query in (("otp_challenges", {"phone": number}), ("auth_grants", {"phone": number}), ("sms_log", {"phone": number})):
        if number:
            await c.db[coll].delete_many(query)
    # Media accounting rows owned by the account lose their owner link (no customer upload feature exists today;
    # the guard keeps any future personal object detached). The managed store cannot delete bytes (managed_delete=0).
    await c.db.media_assets.update_many({"owner_id": uid}, {"$set": {"owner_id": f"deleted:{uid}", "owner_erased_at": c.stamp(),
                                                                       "access_revoked": True}})
    # Completion ledger rows keep the staff attribution (reports) but lose the customer's name / shop (F07).
    await c.db.request_completions.update_many({"customer_id": uid}, {"$set": {"customer_name": "Deleted customer", "shop_name": "", "customer_anonymized": True}})
    # Notification history addressed to the account and any not-yet-sent outbox messages for it are dropped
    # (the outbox worker re-validates recipients before every send as well).
    await c.db.notification_outbox.update_many({"status": {"$in": ["pending", "failed"]}, "messages._user_id": uid},
                                               [{"$set": {"messages": {"$filter": {"input": "$messages", "as": "m", "cond": {"$ne": ["$$m._user_id", uid]}}}}}])
    # A fan-out still in progress never reaches the erased account either (its frozen audience snapshot loses the id).
    await c.db.notification_events.update_many({"recipients": uid}, {"$pull": {"recipients": uid}})
    # Preserve anonymous operational totals, not personal/free-text trade snapshots.
    async for q in c.db.requests.find({"user_id": uid}, {"_id": 0}):
        events = [{k: v for k, v in e.items() if k not in {"notes", "old", "new", "actor_name"}}
                  for e in q.get("events", [])]
        await c.db.requests.update_one({"id": q["id"]}, {"$set": {"user_name": "Deleted customer",
            "user_phone": "", "user_city": "", "shop_name": "", "location": "", "customer_snapshot": {},
            "notes": "", "admin_notes": "", "notes_history": [], "events": events, "anonymized": True},
            "$unset": {"customer_name": "", "customer_phone": "", "customer_shop_name": "", "customer_location": "",
                       "cart_items": "", "preferred_time": "", "category": "", "payload_hash": ""}})
    # The tombstone keeps a session_version ABOVE every issued token, so any surviving token is refused as a revoked
    # session (401), never evaluated as an "inactive account" (403).
    current = await c.db.users.find_one({"id": uid}, {"_id": 0, "session_version": 1}) or {}
    await c.db.users.replace_one({"id": uid}, {"id": uid, "phone": f"deleted:{uid}", "role": "customer", "name": "Deleted customer",
        "account_status": "deleted", "status": "deleted", "deleted_at": c.stamp(), "onboarding_status": "deleted",
        "session_version": int(current.get("session_version", 0)) + 1})
    await c.db.deletion_requests.update_one({"reference": ref}, {"$set": {
        "status": "external_erasure_pending", "local_completed_at": c.stamp()},
        "$unset": {"phone": "", "name": "", "shop_name": ""}})
    # Only consumers that can actually acknowledge are required (REQUIRED_ACKNOWLEDGEMENTS). The SMS and AI providers
    # expose no per-user deletion request, so listing them would leave every deletion "pending" forever; their copies
    # are disclosed as retained under provider terms (erasure_report) instead. `$set` (not `$setOnInsert`) so a retried
    # cleanup converges an event written by an older build.
    await c.db.integration_outbox.update_one({"id": ref}, {"$setOnInsert": {"id": ref, "type": "account_erased",
        "user_id": uid, "created_at": c.stamp(), "status": "pending"},
        "$set": {"required_acknowledgements": REQUIRED_ACKNOWLEDGEMENTS}}, upsert=True)


class DeleteConfirm(BaseModel):
    otp: str = Field(pattern=r"^[0-9]{4}$")
    challenge_id: str | None = None


@router.post("/auth/delete-account/request")
async def delete_start(request: Request, user=Depends(c.allow("customer"))):
    return await start_challenge(c.phone(user["phone"]), "account_deletion", user["id"], request, disclose_to=user["id"])


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
        # App + website CLEANUP is complete. Provider-held copies are a separate outcome (provider-erasure ledger) and
        # are never marked erased by this acknowledgement.
        await mark_cleanup_completed(event_id)
    return {"acknowledged": consumer, "event_id": event_id, "acknowledged_by": sorted(set(doc.get("acknowledged", []))),
            "required_acknowledgements": sorted(required), "all_acknowledged": bool(complete)}


@router.post("/admin/deletion-requests/{reference}/cleanup", tags=["Account deletion ledger"])
async def deletion_resume(reference: str, user=Depends(c.admin)):
    """Explicit, reviewed completion of an INTERRUPTED app cleanup (a deletion the customer already confirmed with an
    OTP, or a legacy request converged at startup). No background worker deletes anything on its own: cleanup runs
    inline with the explicit deletion request and, if that was interrupted, only through this administrator action
    or the customer's next explicit deletion request. Provider erasure remains a separate ledger."""
    deletion = await c.db.deletion_requests.find_one({"reference": reference}, {"_id": 0})
    if not deletion:
        c.fail(404, "DELETION_NOT_FOUND", "Unknown deletion reference")
    if deletion.get("status") != "local_cleanup_pending":
        c.fail(409, "CLEANUP_NOT_PENDING", "App cleanup for this request is not interrupted; nothing to resume")
    async with c.lock("deletion:" + deletion["user_id"], seconds=120):
        person = await c.db.users.find_one({"id": deletion["user_id"]}, {"_id": 0}) or {}
        number = person.get("phone", "")
        if number.startswith("deleted:"):
            number = ""
        await c.db.deletion_requests.update_one({"reference": reference},
            {"$push": {"cleanup.resumed": {"at": c.stamp(), "actor_id": user["id"]}}})
        await cleanup_deletion(deletion["user_id"], number, reference)
    fresh = await c.db.deletion_requests.find_one({"reference": reference}, {"_id": 0})
    return pe.describe(fresh)