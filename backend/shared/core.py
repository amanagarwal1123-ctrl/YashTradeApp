import asyncio
import contextvars
import hashlib
import hmac
import os
import re
import secrets
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone

import jwt
from bson import Binary
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException
from pymongo import ReturnDocument
from pymongo.errors import AutoReconnect, DuplicateKeyError

dispatch_sms = None
put_object = None
get_object = None
load_dotenv()
BUILD = "shared-v2-operations-2026-09-20"
# `upload_executive` (displayed "Upload Executive") owns the CONTENT domain only: PDF/photo imports, products, banners
# and the other Contents pages. It is staff for sign-in/portal purposes but receives no people, query, billing,
# marketing or reporting access - every guard below is explicit, nothing is granted through the generic STAFF set.
ROLES = {"customer", "admin", "telecaller", "billing_executive", "upload_executive"}
STAFF = ROLES - {"customer"}
ROLE_LABELS = {"customer": "Customer", "admin": "Administrator", "telecaller": "Telecaller",
               "billing_executive": "Billing Executive", "upload_executive": "Upload Executive"}

# Data scope of the CURRENT request/task. None = genuine production data; "review" = the
# isolated store-review copy. It is derived ONLY from a signature-verified session or a
# stored review refresh token, never from a client-supplied role, flag or collection name.
REVIEW = "review"
# APPLICATION-ENFORCED isolation (not database-level): every collection touched in review scope is the
# same-named collection of the PRIMARY database carrying this prefix. The deployment's MongoDB user
# needs no rights beyond its main database. Nothing in production scope ever resolves a prefixed name.
REVIEW_PREFIX = "review__"
REVIEW_STORAGE = "prefixed_collections"
_scope = contextvars.ContextVar("yash_data_scope", default=None)
_primary_db = None
_review_db = None
REVIEW_BLOB_LIMIT = 5 * 1024 * 1024
REVIEW_BLOB_TOTAL_LIMIT = 256 * 1024 * 1024


def scope():
    return _scope.get()


def in_review():
    return _scope.get() == REVIEW


def collection_name(name):
    """Physical collection name of `name` in the CURRENT scope (for aggregation `$lookup` targets, which
    MongoDB resolves by literal name and therefore bypass the database proxy)."""
    return REVIEW_PREFIX + name if in_review() else name


def review_enabled_setting():
    """REVIEW_ACCESS_ENABLED=true|1|yes|on switches the optional store-review environment on for a deployment."""
    return setting("REVIEW_ACCESS_ENABLED").lower() in {"1", "true", "yes", "on"}


def review_configured():
    """The store-review environment is switched on for this process (REVIEW_ACCESS_ENABLED). Says nothing about usability."""
    return _review_db is not None


def review_available():
    """Review storage was initialised successfully in THIS process; only then may any code touch it."""
    return _review_db is not None and _review_state["available"]


def review_status():
    """Machine-readable availability for readiness: reason codes, never provider payloads."""
    if _review_db is None:
        return {"available": False, "reason": "REVIEW_ACCESS_DISABLED", "detail": "store-review environment is switched off (REVIEW_ACCESS_ENABLED)"}
    return dict(_review_state)


class _PrefixedDatabase:
    """The store-review view of the primary database: `view.users` is `primary["review__users"]`.
    Only attribute/item access, `command` (ping) and `list_collection_names` are exposed, so no code
    path can reach an unprefixed collection through this handle."""

    def __init__(self, database):
        self._database = database

    @property
    def name(self):
        return self._database.name

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._database[REVIEW_PREFIX + name]

    def __getitem__(self, name):
        return self._database[REVIEW_PREFIX + name]

    async def command(self, *args, **kwargs):
        return await self._database.command(*args, **kwargs)

    async def list_collection_names(self, **kwargs):
        names = await self._database.list_collection_names(**kwargs)
        return [n[len(REVIEW_PREFIX):] for n in names if n.startswith(REVIEW_PREFIX)]


def review_view(database):
    return _PrefixedDatabase(database)


@contextmanager
def scoped(value):
    token = _scope.set(value)
    try:
        yield
    finally:
        _scope.reset(token)


def scopes():
    """Every data scope a background worker must serve: production, then the review copy — but only
    when review storage is actually usable in this process (an unauthorised review database is never
    polled again and again by workers)."""
    return [None] + ([REVIEW] if review_available() else [])


def active_db():
    if in_review():
        if not review_available():
            fail(503, "REVIEW_UNAVAILABLE", "The store-review environment is not available on this server")
        return _review_db
    return _primary_db


class _DatabaseProxy:
    """Resolves to the database of the current data scope on every attribute access."""

    def __getattr__(self, name):
        return getattr(active_db(), name)

    def __getitem__(self, name):
        return active_db()[name]

    def __bool__(self):
        return _primary_db is not None


db = _DatabaseProxy()


def configure(database, sender, put, get, review_enabled=False, review_blobs=None):
    """review_enabled: switch the store-review environment on; its data is the `review__*` collections of
    `database`. review_blobs: a SYNCHRONOUS pymongo handle of `database["review__review_blobs"]` used by the
    thread-based media functions. Enabling does NOT make review usable: initialize_review() must prove it first."""
    global _primary_db, _review_db, _review_blobs, dispatch_sms, put_object, get_object
    _primary_db = database
    _review_db = review_view(database) if review_enabled else None
    _review_blobs = review_blobs if review_enabled else None
    _review_state.update(available=False, reason="REVIEW_STORAGE_UNINITIALIZED" if review_enabled else "REVIEW_ACCESS_DISABLED",
                         detail="review storage not initialised in this process" if review_enabled
                         else "store-review environment is switched off (REVIEW_ACCESS_ENABLED)")
    dispatch_sms, put_object, get_object = sender, put, get


_review_blobs = None
_review_state = {"available": False, "reason": "REVIEW_ACCESS_DISABLED", "detail": "store-review environment is switched off (REVIEW_ACCESS_ENABLED)"}


async def initialize_review():
    """Optional store-review storage: prove the prefixed review collections are usable (ping + indexes) or mark
    them UNAVAILABLE for this process. Only MongoDB failures are absorbed (logged as sanitized warnings, never
    aborting startup); programming errors propagate. Never touches an unprefixed collection and never falls back
    to production scope. Returns True when review storage is usable."""
    import logging
    from pymongo.errors import PyMongoError

    log = logging.getLogger("shared")
    if _review_db is None:
        _review_state.update(available=False, reason="REVIEW_ACCESS_DISABLED",
                             detail="store-review environment is switched off (REVIEW_ACCESS_ENABLED)")
        return False
    _review_state.update(available=True, reason=None, detail="initialising")  # lets ensure_indexes() reach the review handle
    try:
        with scoped(REVIEW):
            await ensure_indexes()
    except PyMongoError as exc:
        code = getattr(exc, "code", None)
        _review_state.update(available=False, reason="REVIEW_STORAGE_UNAVAILABLE",
                             detail=f"review collections rejected initialisation ({type(exc).__name__}{f', MongoDB code {code}' if code else ''})")
        log.warning("Store-review storage DISABLED for this process: the review__ collections refused initialisation (%s). "
                    "Reviewer sign-in answers 503; production data is unaffected.", type(exc).__name__)
        return False
    _review_state.update(available=True, reason=None, detail=f"review storage initialised ({REVIEW_STORAGE} in the primary database)")
    return True


SMS_LOG_RETENTION_DAYS = 90


async def send_sms(number, otp, purpose):
    """Transport gate: review sessions never reach the SMS provider; the message is recorded instead."""
    if in_review():
        entry = {"id": secrets.token_hex(12), "phone": number, "purpose": purpose, "status": "simulated",
                 "simulated": True, "provider": "none", "sent_ts": stamp(), "review_environment": True,
                 "expires_at": now() + timedelta(days=SMS_LOG_RETENTION_DAYS)}
        await db.sms_log.insert_one(dict(entry))
        return entry
    return await dispatch_sms(number, otp, purpose)


def store_object(path, data, content_type):
    """Media gate: review uploads persist inside the review database, never in production storage."""
    if not in_review():
        return put_object(path, data, content_type)
    if _review_blobs is None or not review_available():
        fail(503, "REVIEW_UNAVAILABLE", "Review media storage is not available")
    if len(data) > REVIEW_BLOB_LIMIT:
        fail(413, "REVIEW_STORAGE_LIMIT", "Review uploads are limited to 5 MiB per file")
    used = list(_review_blobs.aggregate([{"$group": {"_id": None, "n": {"$sum": "$size"}}}]))
    if (used[0]["n"] if used else 0) + len(data) > REVIEW_BLOB_TOTAL_LIMIT:
        fail(413, "REVIEW_STORAGE_LIMIT", "Review storage budget exhausted; reset the review environment")
    _review_blobs.replace_one({"_id": path}, {"_id": path, "data": Binary(bytes(data)), "content_type": content_type,
                                              "size": len(data), "created_at": stamp()}, upsert=True)
    return {"path": path, "size": len(data), "review_environment": True}


def fetch_object(path):
    if not in_review():
        return get_object(path)
    doc = _review_blobs.find_one({"_id": path}) if (_review_blobs is not None and review_available()) else None
    if not doc:
        raise FileNotFoundError(path)
    return bytes(doc["data"]), doc.get("content_type", "application/octet-stream")


def now():
    return datetime.now(timezone.utc)


def stamp():
    return now().isoformat()


def fail(status, code, detail):
    raise HTTPException(status, {"code": code, "detail": detail})


def secret(name):
    value = setting(name)
    if len(value) < 32:
        fail(503, "CONFIGURATION_REQUIRED", f"Server requires a strong {name}")
    return value


# Bootstrap placeholders declared in the preview .env so the platform registers the key NAME.
# They are never valid configuration: a setting that carries one is treated as absent.
PLACEHOLDER_MARKERS = ("SET_IN_PUBLISH_SECRETS", "PLACEHOLDER", "REPLACE_ME", "CHANGE_ME", "UNCONFIGURED")


def is_placeholder(value):
    upper = (value or "").strip().upper()
    return not upper or any(marker in upper for marker in PLACEHOLDER_MARKERS)


def setting(name):
    """Configured value of an environment setting, or "" when missing or a bootstrap placeholder."""
    value = os.environ.get(name, "").strip()
    return "" if is_placeholder(value) else value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def keyed(value):
    return hmac.new(secret("JWT_SECRET").encode(), value.encode(), hashlib.sha256).hexdigest()


def role(value):
    if not isinstance(value, str):
        fail(403, "UNKNOWN_ROLE", "Account role is not recognized")
    value = "telecaller" if value == "executive" else value
    if value not in ROLES:
        fail(403, "UNKNOWN_ROLE", "Account role is not recognized; contact the administrator")
    return value


SUPPORTED_REGIONS = {"IN": "+91", "US": "+1", "CA": "+1", "AU": "+61"}


def phone(value, national_only=False):
    """Canonical login number. India (the default country) keeps the historical 10-digit national form so every
    existing Indian account and index stays valid; USA / Canada (+1) and Australia (+61) are stored in E.164
    (`+14155552671`, `+61412345678`) - never truncated to their last ten digits. Any other country is refused.
    `national_only` (website enrollment) keeps accepting bare 10-digit Indian numbers; E.164 is always unambiguous."""
    import phonenumbers
    text = re.sub(r"[ ()\-\u00a0]", "", str(value).strip())
    if text.startswith("00"):
        text = "+" + text[2:]
    if not text.startswith("+"):
        digits = text
        if not national_only and len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if not re.fullmatch(r"[6-9][0-9]{9}", digits):
            fail(422, "INVALID_PHONE", "Enter exactly 10 Indian mobile digits (6–9 first), or an international number with its country code (+1 USA/Canada, +61 Australia)")
        return digits
    try:
        parsed = phonenumbers.parse(text, None)
    except phonenumbers.NumberParseException:
        fail(422, "INVALID_PHONE", "Enter a valid phone number with its country code")
    if parsed.country_code not in {1, 61, 91}:
        fail(422, "UNSUPPORTED_COUNTRY", "Supported countries: India (+91), USA and Canada (+1), Australia (+61)")
    if not phonenumbers.is_valid_number(parsed):
        fail(422, "INVALID_PHONE", "This is not a valid phone number for its country")
    region = phonenumbers.region_code_for_number(parsed)
    if region not in SUPPORTED_REGIONS:
        fail(422, "UNSUPPORTED_COUNTRY", "Supported countries: India (+91), USA and Canada (+1), Australia (+61)")
    if region == "IN":
        national = str(parsed.national_number)
        if not re.fullmatch(r"[6-9][0-9]{9}", national):
            fail(422, "INVALID_PHONE", "Enter exactly 10 Indian mobile digits (6–9 first)")
        return national
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def phone_display(number):
    """Human form of a canonical number (+91 98765 43210 / +1 415 555 2671)."""
    import phonenumbers
    try:
        parsed = phonenumbers.parse(number if str(number).startswith("+") else "+91" + str(number), None)
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except phonenumbers.NumberParseException:
        return str(number)


def phone_masked(number):
    text = str(number)
    return ("*" * max(0, len(text) - 4)) + text[-4:] if len(text) > 4 else "****"


def sms_destination(number):
    """MSG91 `mobiles` value: country code + national digits, no plus. Indian canonical numbers carry no code."""
    text = str(number)
    return text[1:] if text.startswith("+") else "91" + text


def account_status(user):
    # A blocked legacy flag wins over a contradictory active flag until reconciliation.
    values = {user.get("account_status"), user.get("status")}
    if "deleted" in values:
        return "deleted"
    if user.get("disabled") or values & {"disabled", "inactive", "blocked"}:
        return "inactive"
    status = user.get("account_status") or "active"
    return status if status in {"active", "pending"} else "inactive"


def usable(user):
    if not user:
        fail(404, "USER_NOT_FOUND", "This number is not registered. Please enroll first.")
    if account_status(user) != "active":
        fail(403, "ACCOUNT_INACTIVE", "Account is inactive or deleted; contact support")
    role(user.get("role"))


USER_FIELDS = set("id phone name shop_name location city role code customer_code customer_type "
                  "phone_verified verified_at onboarding_status account_status registration_source "
                  "registered_at created_at updated_at first_mobile_login_at last_mobile_login_at "
                  "last_portal_login_at last_login has_logged_in reward_points is_new "
                  "assigned_salesperson lead_status follow_up_at profile_version review_environment profile_conflicts".split())


def public_user(user):
    out = {k: v for k, v in user.items() if k in USER_FIELDS}
    out.update(role=role(user.get("role")), account_status=account_status(user),
               status=account_status(user), code=user.get("code", user.get("customer_code", "")))
    out["location"] = user.get("location") or user.get("city", "")
    out["has_logged_in"] = bool(user.get("first_mobile_login_at"))
    out["step1_complete"] = bool(user.get("phone_verified") and
        user.get("onboarding_status") == "completed" and all(out.get(k) for k in ("name", "phone", "shop_name", "location")))
    # Customer-facing completeness (name, shop name, place): drives the Home "complete your profile" card and the
    # request gate (call / video call / cart selection) - independent of how the account was created.
    out["profile_complete"] = all(out.get(k) for k in ("name", "shop_name", "location"))
    out["profile_conflicts"] = user.get("profile_conflicts") or {}
    return out


def require_complete_profile(user):
    """Customers must have name, shop name and place before a request reaches the team (the app opens the profile
    form and re-sends the request afterwards). Staff are never gated."""
    if role(user.get("role")) == "customer" and not all(user.get(k) or (k == "location" and user.get("city"))
                                                       for k in ("name", "shop_name", "location")):
        fail(428, "PROFILE_INCOMPLETE", "Complete your profile (name, shop name and place) to send this request")


async def by_phone(number):
    # Read old formats without mutating existing records or guessing duplicate identity.
    if str(number).startswith("+"):
        # International canonical numbers are stored verbatim in E.164; a digits-only legacy copy is matched too.
        query = {"$or": [{"phone_normalized": number}, {"phone": number}, {"phone": number[1:]}]}
    else:
        pattern = r"^(?:\+?91[ ()-]*)?" + r"[ ()-]*".join(number) + r"$"
        query = {"$or": [{"phone_normalized": number}, {"phone": {"$regex": pattern}}]}
    docs = await db.users.find(query, {"_id": 0}).limit(3).to_list(3)
    if len(docs) > 1:
        fail(409, "IDENTITY_CONFLICT", "Multiple records require approved identity reconciliation")
    return docs[0] if docs else None


@asynccontextmanager
async def lock(key, seconds=30, wait_seconds=0):
    owner = secrets.token_hex(16)
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            await db.operation_locks.insert_one({"_id": key, "owner": owner,
                                                 "expires_at": now() + timedelta(seconds=seconds)})
            break
        except DuplicateKeyError:
            found = await db.operation_locks.find_one_and_update(
                {"_id": key, "expires_at": {"$lt": now()}},
                {"$set": {"owner": owner, "expires_at": now() + timedelta(seconds=seconds)}},
                return_document=ReturnDocument.AFTER)
            if found:
                break
            if time.monotonic() >= deadline:
                fail(409, "OPERATION_IN_PROGRESS", "Another update is in progress; retry shortly")
            await asyncio.sleep(0.1)
    try:
        async def renew():
            while True:
                await asyncio.sleep(max(1, seconds//3))
                await db.operation_locks.update_one({"_id": key, "owner": owner},
                    {"$set": {"expires_at": now() + timedelta(seconds=seconds)}})
        heartbeat = asyncio.create_task(renew())
        yield
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
        await db.operation_locks.delete_one({"_id": key, "owner": owner})


def decode_session(token):
    return jwt.decode(token, secret("JWT_SECRET"), algorithms=["HS256"], audience="yash-clients",
                      issuer="yash-canonical", options={"require": ["exp", "sub", "sv", "sid"]})


def scope_of_authorization(authorization):
    """Data scope carried by a signature-verified bearer token; anything unverifiable is production
    scope, where the normal session checks will reject it."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return REVIEW if decode_session(authorization[7:]).get("scope") == REVIEW else None
    except (jwt.PyJWTError, HTTPException):
        return None


async def current_user(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        fail(401, "AUTH_REQUIRED", "Sign in to continue")
    try:
        payload = decode_session(authorization[7:])
    except jwt.PyJWTError:
        fail(401, "TOKEN_INVALID", "Session expired or invalid; sign in again")
    token_scope = REVIEW if payload.get("scope") == REVIEW else None
    if token_scope != scope():
        fail(401, "SESSION_SCOPE_MISMATCH", "Session does not belong to this data environment; sign in again")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user or user.get("session_version", 0) != payload["sv"]:
        fail(401, "SESSION_REVOKED", "Session revoked; sign in again")
    if bool(user.get("review_environment")) != in_review():
        fail(401, "SESSION_SCOPE_MISMATCH", "Account environment mismatch; sign in again")
    usable(user)
    session = await db.session_families.find_one({"id": payload["sid"], "revoked": False,
                                                "expires_at": {"$gt": stamp()}}, {"_id": 0})
    if not session or session["user_id"] != user["id"]:
        fail(401, "SESSION_REVOKED", "Session revoked; sign in again")
    user["role"] = role(user.get("role"))
    user["_session_id"] = payload["sid"]
    return user


def allow(*roles):
    async def permission(user=Depends(current_user)):
        if user["role"] not in roles:
            fail(403, "PERMISSION_DENIED", "You do not have permission for this action")
        return user
    return permission


admin = allow("admin")
staff = allow(*STAFF)
billing = allow("admin", "billing_executive")
# Content domain (catalogue imports, products, banners, Contents pages): administrators and Upload Executives.
content = allow("admin", "upload_executive")
# Central query workspace readers: administrators, telecallers and billing (least privilege: billing reads only).
operations = allow("admin", "telecaller", "billing_executive")
# Query WORK actions (claim, notes, heads, completion): telecallers and administrators only.
query_workers = allow("admin", "telecaller")

RECENT_AUTH_MINUTES = 30


async def recent_admin(user=Depends(admin)):
    """Step-up for sensitive administrator actions: the session family must come from an OTP sign-in within the last
    RECENT_AUTH_MINUTES (families issued by older builds carry no sign-in time and therefore never qualify)."""
    family = await db.session_families.find_one({"id": user["_session_id"]}, {"_id": 0, "authenticated_at": 1})
    at = (family or {}).get("authenticated_at")
    if not at or at < (now() - timedelta(minutes=RECENT_AUTH_MINUTES)).isoformat():
        fail(403, "RECENT_AUTH_REQUIRED", f"Sign in again with OTP to confirm this change (verification must be within the last {RECENT_AUTH_MINUTES} minutes)")
    return user


async def integration_key(x_integration_key: str | None = Header(None)):
    if not hmac.compare_digest(x_integration_key or "", secret("ENROLLMENT_INTEGRATION_KEY")):
        fail(401, "INTEGRATION_KEY_INVALID", "Invalid enrollment integration credential")


async def service_key(x_staff_service_key: str | None = Header(None)):
    if hmac.compare_digest(secret("STAFF_SERVICE_KEY"), os.environ.get("ENROLLMENT_INTEGRATION_KEY", "").strip()):
        fail(503, "CONFIGURATION_REQUIRED", "STAFF_SERVICE_KEY must differ from enrollment credential")
    if not hmac.compare_digest(x_staff_service_key or "", secret("STAFF_SERVICE_KEY")):
        fail(401, "SERVICE_KEY_INVALID", "A separate staff-service credential is required")


async def revoke(uid):
    await db.users.update_one({"id": uid}, {"$inc": {"session_version": 1}})
    await db.session_families.update_many({"user_id": uid}, {"$set": {"revoked": True}})
    await db.refresh_tokens.update_many({"user_id": uid, "used": False}, {"$set": {"used": True}})
    # A revoked account must not keep receiving that account's alerts on any device.
    await db.push_devices.update_many({"user_id": uid}, {"$set": {"enabled": False, "unlinked_at": stamp(), "unlink_reason": "revoked"}})


async def indexes():
    # Never normalize/merge existing identities during application startup.
    await db.users.create_index("phone_normalized", unique=True, sparse=True)
    await db.otp_challenges.create_index("expires_at", expireAfterSeconds=0)
    await db.identity_operations.create_index("key", unique=True)
    await db.identity_operations.create_index("expires_at", expireAfterSeconds=0)
    await db.identity_audit.create_index([("target_id", 1), ("at", -1)])
    await db.otp_limits.create_index("expires_at", expireAfterSeconds=0)
    await db.auth_grants.create_index("expires_at", expireAfterSeconds=0)
    await db.refresh_tokens.create_index("hash", unique=True)
    await db.requests.create_index([("created_at", -1), ("id", 1)])
    await db.requests.create_index([("events.type", 1), ("events.timestamp", 1)])
    # Central query workspace: fresh-first queue order, per-assignee pending views and the daily release scan.
    await db.requests.create_index([("status", 1), ("queue_sort_at", -1), ("created_at", -1), ("id", 1)])
    await db.requests.create_index([("assignee_id", 1), ("status", 1), ("queue_sort_at", -1)])
    await db.requests.create_index([("status", 1), ("created_at", 1), ("reset_cycle", 1)])
    # Completion ledger recovery (G02): indexed durable intents + the cursor walk over resolved requests.
    await db.requests.create_index("ledger_pending.at", sparse=True)
    await db.requests.create_index([("status", 1), ("resolved_at", 1), ("id", 1)])
    await db.request_completions.create_index([("request_id", 1), ("completed_at", -1)])
    await db.request_completions.create_index([("actor_id", 1), ("completed_at", -1)])
    await db.request_completions.create_index("key", unique=True)
    # Notifications: one row per device token, per-user inbox, durable outbox with idempotent keys.
    await db.push_devices.create_index("token", unique=True)
    await db.push_devices.create_index([("user_id", 1), ("enabled", 1)])
    await db.notifications.create_index([("user_id", 1), ("created_at", -1), ("id", 1)])
    await db.notifications.create_index("id", unique=True)
    await db.notifications.create_index("expires_at", expireAfterSeconds=0)
    await db.notification_outbox.create_index("key", unique=True)
    await db.notification_outbox.create_index([("status", 1), ("next_attempt_at", 1)])
    await db.notification_outbox.create_index("campaign_id", sparse=True)
    await db.notification_campaigns.create_index([("created_at", -1), ("id", 1)])
    # Durable fan-out events (G04): frozen audience + completion state per event key; campaigns in flight are leased.
    await db.notification_events.create_index("id", unique=True)
    await db.notification_events.create_index([("state", 1), ("updated_at", 1)])
    await db.notification_campaigns.create_index([("status", 1), ("fanout.lease_until", 1)])
    # Discovery: what each signed-in user has actually seen, and the bounded per-refresh ordering sessions.
    await db.product_impressions.create_index([("user_id", 1), ("product_id", 1)], unique=True)
    await db.product_impressions.create_index([("user_id", 1), ("seen_at", -1)])
    await db.discovery_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.discovery_sessions.create_index([("user_id", 1), ("created_at", -1)])
    await db.discovery_cursors.create_index([("user_id", 1), ("filter_key", 1)], unique=True)
    await db.products.create_index([("batch_id", 1), ("created_at", -1)])
    await db.products.create_index([("created_at", -1), ("id", 1)])
    await db.products.create_index([("metal_type", 1), ("category", 1), ("created_at", -1), ("id", 1)])
    await db.products.create_index([("title", "text"), ("tags", "text"), ("product_code", "text"), ("category", "text")], name="catalog_search_v1")
    for field in ("storage_path", "thumbnail_path", "original_source_storage_path", "images"):
        await db.products.create_index(field)
    await db.banners.create_index("image_url")
    await db.media_assets.create_index("path", unique=True, sparse=True)
    await db.media_assets.create_index([("purpose", 1), ("created_at", 1)])
    await db.users.create_index([("assigned_salesperson", 1)])
    await db.telecaller_activity.create_index([("customer_id", 1), ("created_at", -1)])
    await db.import_jobs.create_index("id", unique=True)
    await db.products.create_index("product_code", unique=True, partialFilterExpression={"product_code": {"$type": "string"}})
    # SMS delivery logs carry a phone number and exist only for OTP-delivery diagnostics. New rows are written with
    # `expires_at` (SMS_LOG_RETENTION_DAYS); the TTL index that enforces the window and the expiry back-fill for older
    # rows are an explicit admin action (shared/maintenance.py) - startup never deletes or rewrites records.


async def ensure_indexes():
    """Retry only idempotent DDL transport errors, never business requests or failed assertions."""
    import logging
    for attempt in range(3):
        try:
            await db.command("ping")
            await indexes()
            return
        except AutoReconnect:
            if attempt == 2:
                raise
            logging.getLogger("shared").warning("Index setup connection interrupted; retry %s/2", attempt+1)
            await asyncio.sleep(0.25 * 2**attempt)