"""Default owner administrator.

`OWNER_ADMIN_PHONE` (backend/.env, one Indian mobile number) is admin in EVERY environment this backend runs in.
Applied once per process start, after the primary indexes exist, and idempotent:
  * exactly one existing record for that phone -> promoted to admin ON THE SAME RECORD (canonical id and all
    business history preserved, audit event appended, session version bumped and open sessions revoked once);
    an active admin is left untouched (sessions kept);
  * no record -> an active admin record is created so the FIRST genuine OTP login already carries the role
    (no password, no OTP, no token is created here);
  * several records for the phone, or a deleted/inactive record -> nothing is changed; the condition is reported
    by /api/health (flows.owner_admin) and the log. Identities are never merged or resurrected here.
Only the production scope is touched (never the store-review copy) and never any other account. Sign-in stays the
normal MSG91 OTP flow: the mobile app (channel "mobile") and the website's staff exchange (channel "portal" with the
staff service key) both read the role from this record, so one bootstrap serves both surfaces. The record is also
protected from demotion/disabling through the staff API (people.last_admin_guard).
"""
import logging
import secrets

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError, PyMongoError

from . import core as c

EVENT = "owner_admin_bootstrap"
ACTOR = "system:" + EVENT
_state = {"applied": False, "reason": "OWNER_ADMIN_UNINITIALIZED", "action": None, "phone_suffix": None,
          "detail": "owner admin bootstrap has not run in this process", "at": None}


def configured_phone():
    """The configured owner phone as 10 national digits, or "" when missing, a placeholder or invalid."""
    value = c.setting("OWNER_ADMIN_PHONE")
    if not value:
        return ""
    try:
        return c.phone(value)
    except HTTPException:
        return ""


def is_owner(user):
    """True for the record carrying the configured owner phone (protected from demotion and disabling)."""
    number = configured_phone()
    if not number or not user:
        return False
    try:
        return c.phone(user.get("phone_normalized") or user.get("phone") or "") == number
    except HTTPException:
        return False


def status():
    return dict(_state)


def _set(applied, reason, action, detail, suffix):
    _state.update(applied=applied, reason=reason, action=action, detail=detail, phone_suffix=suffix, at=c.stamp())
    return applied


async def _records(number):
    # Same lookup as core.by_phone: normalized field or any stored formatting of the number; never merges.
    pattern = r"^(?:\+?91[ ()-]*)?" + r"[ ()-]*".join(number) + r"$"
    return await c.db.users.find({"$or": [{"phone_normalized": number}, {"phone": {"$regex": pattern}}]},
                                 {"_id": 0}).limit(3).to_list(3)


async def ensure_owner_admin():
    """Idempotent startup step. Returns True when the owner record is admin after the call."""
    log = logging.getLogger("shared")
    if c.in_review():
        raise RuntimeError("owner admin bootstrap runs in production scope only")
    raw = c.setting("OWNER_ADMIN_PHONE")
    number = configured_phone()
    suffix = number[-4:] if number else None
    if not number:
        detail = "OWNER_ADMIN_PHONE is not a valid Indian mobile number" if raw else "OWNER_ADMIN_PHONE not configured"
        log.warning("Owner admin bootstrap skipped: %s", detail)
        return _set(False, "OWNER_ADMIN_PHONE", None, detail, None)
    try:
        rows = await _records(number)
        ts = c.stamp()
        if not rows:
            # A deleted identity is never resurrected by the bootstrap (same rule as enrollment retries).
            if await c.db.deleted_identities.find_one({"phone_hash": c.keyed(number)}, {"_id": 1}):
                log.error("Owner admin bootstrap refused: the owner phone (...%s) belongs to a deleted identity; nothing created", suffix)
                return _set(False, "OWNER_ADMIN_DELETED_IDENTITY", None, "owner phone belongs to a deleted identity; nothing created", suffix)
            doc = {"id": secrets.token_hex(16), "phone": number, "phone_normalized": number, "name": "Owner", "role": "admin",
                   "account_status": "active", "status": "active", "session_version": 0, "phone_verified": False,
                   "onboarding_status": "completed", "registration_source": EVENT, "created_at": ts, "registered_at": ts,
                   "updated_at": ts, "identity_events": [{"type": EVENT, "at": ts, "actor_id": ACTOR, "old_role": None,
                                                          "new_role": "admin", "created": True}]}
            try:
                await c.db.users.insert_one(dict(doc))
            except DuplicateKeyError:
                rows = await _records(number)  # another worker created it first (unique phone_normalized index)
            else:
                log.info("Owner admin bootstrap: created the owner administrator (...%s); sign-in is the normal OTP flow", suffix)
                return _set(True, None, "created", "owner administrator record created; sign in with the normal OTP flow", suffix)
        if len(rows) != 1:
            log.error("Owner admin bootstrap refused: %s records carry the owner phone (...%s); reconcile identities first", len(rows), suffix)
            return _set(False, "OWNER_ADMIN_IDENTITY_CONFLICT", None, f"{len(rows)} records carry the owner phone; nothing changed", suffix)
        user = rows[0]
        if c.account_status(user) != "active":
            log.error("Owner admin bootstrap refused: the owner record (...%s) is %s; nothing changed", suffix, c.account_status(user))
            return _set(False, "OWNER_ADMIN_ACCOUNT_INACTIVE", None, f"owner record is {c.account_status(user)}; nothing changed", suffix)
        old_role = user.get("role")
        if old_role == "admin":
            log.info("Owner admin bootstrap: owner record (...%s) already admin; nothing changed", suffix)
            return _set(True, None, "already_admin", "owner record already admin; sessions untouched", suffix)
        event = {"type": EVENT, "at": ts, "actor_id": ACTOR, "old_role": old_role, "new_role": "admin"}
        result = await c.db.users.update_one({"id": user["id"], "role": old_role}, {
            "$set": {"role": "admin", "updated_at": ts}, "$inc": {"session_version": 1}, "$push": {"identity_events": event}})
        if result.modified_count != 1:
            fresh = await c.db.users.find_one({"id": user["id"]}, {"_id": 0})
            if fresh and fresh.get("role") == "admin":
                return _set(True, None, "already_admin", "owner record promoted concurrently; nothing overwritten", suffix)
            return _set(False, "OWNER_ADMIN_NOT_APPLIED", None, "owner record changed during bootstrap; nothing overwritten", suffix)
        # The session-version bump already invalidates old access and refresh tokens; close the families too.
        await c.db.session_families.update_many({"user_id": user["id"]}, {"$set": {"revoked": True}})
        log.info("Owner admin bootstrap: promoted the existing owner record (...%s) from %s to admin on the same id; open sessions revoked",
                 suffix, old_role)
        return _set(True, None, "promoted", f"existing record promoted from {old_role} to admin; re-authentication required", suffix)
    except PyMongoError as exc:
        log.error("Owner admin bootstrap failed: %s", type(exc).__name__)
        return _set(False, "OWNER_ADMIN_NOT_APPLIED", None, f"database error during bootstrap ({type(exc).__name__})", suffix)
    except HTTPException as exc:  # c.keyed() needs a strong JWT_SECRET; configuration gaps are reported, never fatal here
        code = exc.detail.get("code") if isinstance(exc.detail, dict) else "CONFIGURATION_REQUIRED"
        log.error("Owner admin bootstrap not applied: %s", code)
        return _set(False, "OWNER_ADMIN_NOT_APPLIED", None, f"bootstrap blocked by configuration ({code})", suffix)
