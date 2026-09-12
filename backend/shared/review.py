"""Store-review access: isolated reviewer accounts with reusable hashed secrets.

Reviewer sessions run entirely inside the separate review database selected by the server from
the signature-verified session scope (see core.scoped/current_user). Ordinary customer and staff
authentication is untouched: review users do not exist in the production database, so an OTP
request for their phone is refused there, and no production record is ever readable here.
"""
import secrets

import bcrypt
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from . import core as c
from .auth import issue, rate_limit

router = APIRouter(prefix="/api", tags=["Store review access"])
ROUNDS = 12
REVIEW_ROLES = ("customer", "admin", "telecaller", "billing_executive")
# Constant-cost verification for unknown reviewer IDs (created once per process, never issued).
DUMMY_HASH = bcrypt.hashpw(secrets.token_urlsafe(32).encode(), bcrypt.gensalt(ROUNDS)).decode()


def new_secret():
    return secrets.token_urlsafe(32)  # 43 URL-safe characters, well under bcrypt's 72-byte limit


def hash_secret(secret):
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt(ROUNDS)).decode()


def verify_secret(secret, stored_hash):
    try:
        return bcrypt.checkpw(secret.encode(), stored_hash.encode())
    except ValueError:
        return False


class ReviewLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    access_key: str = Field(min_length=20, max_length=72)


async def audit(event, reviewer_id, ip, success, detail=""):
    await c.db.review_access_log.insert_one({"event": event, "reviewer_id": reviewer_id, "ip": ip,
        "success": success, "detail": detail, "created_at": c.stamp()})


@router.post("/auth/review/login")
async def review_login(req: ReviewLogin, request: Request):
    """Reviewer ID + reusable access key -> normal canonical session bound to the review scope.
    Missing review configuration denies access; it never falls back to production data."""
    if not c.review_configured():
        c.fail(503, "REVIEW_UNAVAILABLE", "The store-review environment is not configured on this server")
    ip = request.client.host if request.client else "unknown"
    with c.scoped(c.REVIEW):
        await rate_limit("review-ip:" + ip, 30, 60)
        await rate_limit("review-account:" + req.reviewer_id, 5, 60)
        account = await c.db.review_accounts.find_one({"reviewer_id": req.reviewer_id}, {"_id": 0})
        valid = await run_in_threadpool(verify_secret, req.access_key, account["secret_hash"] if account else DUMMY_HASH)
        active = bool(account and account.get("enabled") and not account.get("revoked_at"))
        user = await c.db.users.find_one({"id": account["user_id"]}, {"_id": 0}) if (valid and active) else None
        if not user or not user.get("review_environment") or c.account_status(user) != "active":
            await audit("review_login_failed", req.reviewer_id, ip, False,
                        "unknown_or_revoked" if not (valid and active) else "review_user_unavailable")
            c.fail(401, "REVIEW_CREDENTIALS_INVALID", "Reviewer ID or access key is incorrect")
        ts = c.stamp()
        await c.db.users.update_one({"id": user["id"]}, {"$set": {"last_login": ts, "last_mobile_login_at": ts,
            "first_mobile_login_at": user.get("first_mobile_login_at") or ts, "has_logged_in": True}})
        await c.db.review_accounts.update_one({"reviewer_id": req.reviewer_id}, {"$set": {"last_login_at": ts}})
        await audit("review_login_succeeded", req.reviewer_id, ip, True)
        session = await issue(await c.db.users.find_one({"id": user["id"]}, {"_id": 0}))
        return {**session, "review_environment": True,
                "notice": "Store-review environment: synthetic records only; SMS, calls and messages are simulated."}
