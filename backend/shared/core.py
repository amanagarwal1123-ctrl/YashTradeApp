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
BUILD = "shared-v1-store-submission-2026-09-13"
ROLES = {"customer", "admin", "telecaller", "billing_executive"}
STAFF = ROLES - {"customer"}

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


async def send_sms(number, otp, purpose):
    """Transport gate: review sessions never reach the SMS provider; the message is recorded instead."""
    if in_review():
        entry = {"id": secrets.token_hex(12), "phone": number, "purpose": purpose, "status": "simulated",
                 "simulated": True, "provider": "none", "sent_ts": stamp(), "review_environment": True}
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


def phone(value, national_only=False):
    text = str(value).strip()
    if not national_only:
        text = re.sub(r"[ ()-]", "", text)
        if text.startswith("+91"):
            text = text[3:]
        elif len(text) == 12 and text.startswith("91"):
            text = text[2:]
    if not re.fullmatch(r"[6-9][0-9]{9}", text):
        fail(422, "INVALID_PHONE", "Enter exactly 10 Indian mobile digits (6–9 first)")
    return text


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
                  "assigned_salesperson lead_status follow_up_at profile_version review_environment".split())


def public_user(user):
    out = {k: v for k, v in user.items() if k in USER_FIELDS}
    out.update(role=role(user.get("role")), account_status=account_status(user),
               status=account_status(user), code=user.get("code", user.get("customer_code", "")))
    out["location"] = user.get("location") or user.get("city", "")
    out["has_logged_in"] = bool(user.get("first_mobile_login_at"))
    out["step1_complete"] = bool(user.get("phone_verified") and
        user.get("onboarding_status") == "completed" and all(out.get(k) for k in ("name", "phone", "shop_name", "location")))
    return out


async def by_phone(number):
    # Read old formats without mutating existing records or guessing duplicate identity.
    pattern = r"^(?:\+?91[ ()-]*)?" + r"[ ()-]*".join(number) + r"$"
    docs = await db.users.find({"$or": [{"phone_normalized": number},
        {"phone": {"$regex": pattern}}]}, {"_id": 0}).limit(3).to_list(3)
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


async def indexes():
    # Never normalize/merge existing identities during application startup.
    await db.users.create_index("phone_normalized", unique=True, sparse=True)
    await db.otp_challenges.create_index("expires_at", expireAfterSeconds=0)
    await db.otp_limits.create_index("expires_at", expireAfterSeconds=0)
    await db.auth_grants.create_index("expires_at", expireAfterSeconds=0)
    await db.refresh_tokens.create_index("hash", unique=True)
    await db.requests.create_index([("created_at", -1), ("id", 1)])
    await db.requests.create_index([("events.type", 1), ("events.timestamp", 1)])
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