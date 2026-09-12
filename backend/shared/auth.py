import secrets
from datetime import timedelta
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument

from . import core as c

router = APIRouter(prefix="/api", tags=["Canonical identity"])


class SendOTP(BaseModel):
    phone: str
    purpose: Literal["login", "enrollment", "deletion"] = "login"
    channel: Literal["mobile", "portal"] = "mobile"


class VerifyOTP(SendOTP):
    otp: str = Field(pattern=r"^[0-9]{4}$")
    challenge_id: str | None = None


async def rate_limit(key, limit, window):
    bucket = int(c.now().timestamp()) // window
    doc = await c.db.otp_limits.find_one_and_update({"_id": c.keyed(f"{key}:{bucket}")},
        {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": c.now() + timedelta(seconds=window * 2)}},
        upsert=True, return_document=ReturnDocument.AFTER)
    if doc["count"] > limit:
        c.fail(429, "OTP_RATE_LIMIT", "Too many attempts; please wait before trying again")


async def start_challenge(number, purpose, subject, request):
    ip = request.client.host if request.client else "unknown"
    # Ignore client-supplied forwarded headers. Proxies need a configured trusted ingress.
    await rate_limit("send-ip:" + ip, 30, 600)
    await rate_limit("send-phone:" + number, 5, 600)
    async with c.lock("otp-send:" + c.keyed(number)):
        recent = await c.db.otp_challenges.find_one({"phone": number,
            "created_at": {"$gt": c.now() - timedelta(seconds=60)}})
        if recent:
            c.fail(429, "OTP_COOLDOWN", "Wait 60 seconds before requesting another OTP")
        cid, otp = secrets.token_urlsafe(24), f"{secrets.randbelow(10000):04d}"
        # No usable challenge is persisted until the provider accepts dispatch.
        await c.send_sms(number, otp, purpose)
        await c.db.otp_challenges.update_many({"phone": number, "purpose": purpose, "subject": subject},
                                              {"$set": {"used": True}})
        await c.db.otp_challenges.insert_one({"id": cid, "phone": number, "purpose": purpose,
            "subject": subject, "hash": c.keyed(f"{cid}:{purpose}:{otp}"), "attempts": 0,
            "used": False, "created_at": c.now(), "expires_at": c.now() + timedelta(minutes=10)})
    return {"message": "OTP accepted by SMS provider", "challenge_id": cid,
            "otp_length": 4, "expires_in": 600, "resend_after": 60}


async def check_challenge(number, purpose, subject, otp, cid=None):
    await rate_limit("verify:" + number, 20, 600)
    query = {"phone": number, "purpose": purpose, "subject": subject,
             "used": False, "expires_at": {"$gt": c.now()}, "attempts": {"$lt": 5}}
    if cid:
        query["id"] = cid
    doc = await c.db.otp_challenges.find_one_and_update(query, {"$inc": {"attempts": 1}},
        sort=[("created_at", -1)], return_document=ReturnDocument.AFTER)
    if not doc or not secrets.compare_digest(doc["hash"], c.keyed(f"{doc['id']}:{purpose}:{otp}")):
        c.fail(400, "OTP_INVALID", "OTP is invalid, expired, or exhausted")
    result = await c.db.otp_challenges.update_one({"id": doc["id"], "used": False}, {"$set": {"used": True}})
    if not result.modified_count:
        c.fail(400, "OTP_USED", "OTP has already been used")


async def make_grant(number, purpose, subject=""):
    raw = secrets.token_urlsafe(32)
    await c.db.auth_grants.insert_one({"hash": c.digest(raw), "phone": number, "purpose": purpose,
        "subject": subject, "used": False, "expires_at": c.now() + timedelta(minutes=5)})
    return {"verification_grant": raw, "expires_in": 300}


async def issue(user, family=None):
    c.usable(user)
    if bool(user.get("review_environment")) != c.in_review():
        c.fail(409, "SESSION_SCOPE_MISMATCH", "Account does not belong to this data environment")
    sid = family or secrets.token_urlsafe(24)
    expiry = c.now() + timedelta(minutes=15)
    if not family:
        await c.db.session_families.insert_one({"id": sid, "user_id": user["id"], "revoked": False,
            "expires_at": (c.now() + timedelta(days=30)).isoformat()})
    claims = {"sub": user["id"], "user_id": user["id"], "role": c.role(user["role"]),
        "sv": user.get("session_version", 0), "sid": sid, "iss": "yash-canonical", "aud": "yash-clients",
        "iat": c.now(), "exp": expiry}
    if c.in_review():
        claims["scope"] = c.REVIEW
    token = jwt.encode(claims, c.secret("JWT_SECRET"), algorithm="HS256")
    # Review refresh tokens carry a routing prefix so /auth/refresh looks them up in the review
    # database; the prefix grants nothing by itself because the stored digest must still match.
    refresh = (REVIEW_REFRESH_PREFIX if c.in_review() else "") + secrets.token_urlsafe(48)
    await c.db.refresh_tokens.insert_one({"hash": c.digest(refresh), "user_id": user["id"], "sid": sid,
        "sv": user.get("session_version", 0), "used": False,
        "expires_at": (c.now() + timedelta(days=30)).isoformat()})
    return {"token": token, "expires_at": expiry.isoformat(), "refresh_token": refresh,
            "user": c.public_user(user)}


REVIEW_REFRESH_PREFIX = "review."


async def validate_channel(req, enrollment_key, staff_key):
    if req.purpose in {"enrollment", "deletion"}:
        await c.integration_key(enrollment_key)
    elif req.channel == "portal":
        await c.service_key(staff_key)


@router.post("/auth/send-otp")
async def send_otp(req: SendOTP, request: Request,
                   x_integration_key: str | None = Header(None), x_staff_service_key: str | None = Header(None)):
    await validate_channel(req, x_integration_key, x_staff_service_key)
    number = c.phone(req.phone, national_only=req.purpose == "enrollment")
    user = await c.by_phone(number)
    if req.purpose != "enrollment" or user:
        c.usable(user)
    if req.purpose == "enrollment" and await c.db.deleted_identities.find_one({"phone_hash": c.keyed(number)}):
        c.fail(409, "DELETED_IDENTITY", "Deleted identity cannot be restored by enrollment retries")
    return await start_challenge(number, req.purpose, user["id"] if user else "", request)


@router.post("/auth/verify-otp")
async def verify_otp(req: VerifyOTP, request: Request,
                     x_integration_key: str | None = Header(None), x_staff_service_key: str | None = Header(None)):
    await validate_channel(req, x_integration_key, x_staff_service_key)
    number = c.phone(req.phone, national_only=req.purpose == "enrollment")
    user = await c.by_phone(number)
    if req.purpose != "enrollment" or user:
        c.usable(user)
    await rate_limit("verify-ip:" + (request.client.host if request.client else "unknown"), 100, 600)
    await check_challenge(number, req.purpose, user["id"] if user else "", req.otp, req.challenge_id)
    if req.purpose != "login":
        return await make_grant(number, req.purpose, user["id"] if user else "")
    if req.channel == "portal" and c.role(user["role"]) not in c.STAFF:
        c.fail(403, "STAFF_ONLY", "Customers enroll on the website and use the mobile app")
    ts = c.stamp()
    changes = {"phone_verified": True, "verified_at": user.get("verified_at") or ts, "last_login": ts}
    if req.channel == "mobile":
        changes.update(last_mobile_login_at=ts, first_mobile_login_at=user.get("first_mobile_login_at") or ts,
                       has_logged_in=True)
    else:
        changes["last_portal_login_at"] = ts
    await c.db.users.update_one({"id": user["id"]}, {"$set": changes})
    fresh = await c.db.users.find_one({"id": user["id"]}, {"_id": 0})
    return await issue(fresh)


class Refresh(BaseModel):
    refresh_token: str


@router.post("/auth/refresh")
async def refresh(req: Refresh):
    with c.scoped(c.REVIEW if req.refresh_token.startswith(REVIEW_REFRESH_PREFIX) else None):
        return await rotate_refresh(req.refresh_token)


async def rotate_refresh(refresh_token):
    old = await c.db.refresh_tokens.find_one_and_update(
        {"hash": c.digest(refresh_token), "used": False, "expires_at": {"$gt": c.stamp()}},
        {"$set": {"used": True}}, return_document=ReturnDocument.AFTER)
    if not old:
        hit = await c.db.refresh_tokens.find_one({"hash": c.digest(refresh_token)}, {"_id": 0})
        if hit:
            await c.db.session_families.update_one({"id": hit["sid"]}, {"$set": {"revoked": True}})
        c.fail(401, "REFRESH_INVALID", "Refresh token expired or reused; sign in again")
    family = await c.db.session_families.find_one({"id": old["sid"], "revoked": False,
                                                  "expires_at": {"$gt": c.stamp()}}, {"_id": 0})
    user = await c.db.users.find_one({"id": old["user_id"]}, {"_id": 0})
    if not family or not user or user.get("session_version", 0) != old["sv"]:
        c.fail(401, "SESSION_REVOKED", "Session revoked; sign in again")
    return await issue(user, old["sid"])


@router.post("/auth/logout")
async def logout(user=Depends(c.current_user)):
    await c.db.session_families.update_one({"id": user["_session_id"]}, {"$set": {"revoked": True}})
    return {"logged_out": True}


@router.get("/auth/me")
async def me(user=Depends(c.current_user)):
    return c.public_user(user)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    shop_name: str = Field(min_length=1, max_length=160)
    location: str = Field(min_length=1, max_length=160)
    city: str | None = Field(None, max_length=160)


def profile_fields(req, existing=None):
    fields = {k: v.strip() for k, v in req.model_dump(exclude_none=True).items()}
    if not all(fields.get(k) for k in ("name", "shop_name", "location")):
        c.fail(422, "PROFILE_REQUIRED", "Name, shop name and location are mandatory")
    fields["city"] = fields.get("city") or (existing or {}).get("city") or fields["location"]
    return fields


@router.put("/auth/profile")
async def profile(req: Profile, user=Depends(c.current_user)):
    await c.db.users.update_one({"id": user["id"]}, {"$set": {**profile_fields(req, user), "updated_at": c.stamp()},
                                                     "$inc": {"profile_version": 1}})
    return c.public_user(await c.db.users.find_one({"id": user["id"]}, {"_id": 0}))


class Enrollment(Profile):
    phone: str
    verification_grant: str
    idempotency_key: str = Field(min_length=8, max_length=120)
    consent_version: str = Field(min_length=1, max_length=40)
    consent_terms: Literal[True]
    consent_privacy: Literal[True]


@router.post("/integrations/enrollments", dependencies=[Depends(c.integration_key)])
async def enroll(req: Enrollment):
    number = c.phone(req.phone, national_only=True)
    async with c.lock("identity:" + number):
        key = c.digest(req.verification_grant)
        grant = await c.db.auth_grants.find_one({"hash": key, "phone": number, "purpose": "enrollment"}, {"_id": 0})
        payload_hash = c.digest(req.model_dump_json())
        if not grant:
            c.fail(401, "VERIFICATION_REQUIRED", "A canonical enrollment verification grant is required")
        if grant.get("used"):
            if grant.get("payload_hash") == payload_hash:
                existing = await c.by_phone(number)
                c.usable(existing)
                return {"created": grant.get("created", False), "customer": c.public_user(existing), "replayed": True}
            c.fail(409, "GRANT_USED", "Verification grant was already consumed")
        expiry = grant["expires_at"].replace(tzinfo=c.timezone.utc)
        if expiry <= c.now():
            c.fail(401, "GRANT_EXPIRED", "Verification expired; verify your phone again")
        if await c.db.deleted_identities.find_one({"phone_hash": c.keyed(number)}):
            c.fail(409, "DELETED_IDENTITY", "Enrollment retries cannot restore deleted accounts")
        existing = await c.by_phone(number)
        if grant.get("subject") and (not existing or existing["id"] != grant["subject"]):
            c.fail(409, "GRANT_SUBJECT_CHANGED", "The verified identity changed; start a fresh verification")
        if existing:
            c.usable(existing)
            if c.role(existing["role"]) != "customer":
                c.fail(409, "STAFF_IDENTITY", "Existing staff identity cannot be changed by public enrollment")
        ts = c.stamp()
        fields = profile_fields(Profile(**{k: getattr(req, k) for k in Profile.model_fields}), existing)
        uid = existing["id"] if existing else secrets.token_hex(16)
        fields.update(phone=number, phone_normalized=number, phone_verified=True,
            verified_at=(existing or {}).get("verified_at") or ts, onboarding_status="completed", updated_at=ts)
        await c.db.users.update_one({"id": uid}, {"$set": fields, "$inc": {"profile_version": 1},
            "$setOnInsert": {"id": uid, "role": "customer", "account_status": "active", "status": "active",
                "created_at": ts, "registered_at": ts, "registration_source": "website", "session_version": 0,
                "has_logged_in": False, "lead_status": "new", "reward_points": 0, "is_new": True},
            "$addToSet": {"consent_history": {"version": req.consent_version, "terms": True, "privacy": True,
                "at": ts, "source": "website", "grant_hash": key}}}, upsert=True)
        await c.db.auth_grants.update_one({"hash": key}, {"$set": {"used": True, "payload_hash": payload_hash,
            "created": not bool(existing), "user_id": uid}})
        return {"created": not bool(existing), "customer": c.public_user(await c.by_phone(number))}


@router.get("/integrations/customers/{number}", dependencies=[Depends(c.integration_key)])
async def integration_customer(number: str):
    user = await c.by_phone(c.phone(number))
    if not user or c.role(user["role"]) != "customer":
        c.fail(404, "USER_NOT_FOUND", "Customer not found")
    return {"customer": c.public_user(user)}


class PhoneChange(BaseModel):
    new_phone: str


class PhoneVerify(PhoneChange):
    otp: str = Field(pattern=r"^[0-9]{4}$")
    challenge_id: str | None = None


@router.post("/auth/phone-change/request")
async def change_start(req: PhoneChange, request: Request, user=Depends(c.current_user)):
    number = c.phone(req.new_phone)
    if await c.by_phone(number) or await c.db.deleted_identities.find_one({"phone_hash": c.keyed(number)}):
        c.fail(409, "PHONE_CONFLICT", "This phone is already associated with an identity")
    return await start_challenge(number, "phone_change", user["id"], request)


@router.post("/auth/phone-change/verify")
async def change_verify(req: PhoneVerify, user=Depends(c.current_user)):
    number = c.phone(req.new_phone)
    async with c.lock("identity:" + number):
        if await c.by_phone(number):
            c.fail(409, "PHONE_CONFLICT", "This phone is already associated with an identity")
        await check_challenge(number, "phone_change", user["id"], req.otp, req.challenge_id)
        result = await c.db.users.update_one({"id": user["id"], "phone": user["phone"],
            "session_version": user.get("session_version", 0)} if "session_version" in user else
            {"id": user["id"], "phone": user["phone"], "session_version": {"$exists": False}},
            {"$set": {"phone": number, "phone_normalized": number, "phone_verified": True,
                "verified_at": c.stamp(), "updated_at": c.stamp()}, "$inc": {"session_version": 1, "profile_version": 1}})
        if not result.modified_count:
            c.fail(409, "VERSION_CONFLICT", "Identity changed; sign in and retry")
        await c.db.session_families.update_many({"user_id": user["id"]}, {"$set": {"revoked": True}})
        return {"id": user["id"], "phone": number, "reauthentication_required": True}