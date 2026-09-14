"""Owner console for store-review access (App Store / Play reviewer accounts).

Authorisation is decided SERVER-SIDE on the canonical record: the caller must hold a production-scope admin
session AND be the configured owner administrator (OWNER_ADMIN_PHONE). Reviewer administrators run in review
scope and are refused before any lookup. Key generation, rotation and revocation additionally require FRESH
authentication: a single-use OTP challenge (purpose `review_keys`) sent to the owner's own registered number
through the normal SMS transport, so an idle admin session on a shared device can never mint reviewer keys.
Plaintext keys appear once in the response body and nowhere else (only bcrypt hashes are stored; the shared
error handlers never echo bodies).
"""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from . import core as c
from . import review_seed
from .auth import check_challenge, start_challenge
from .owner_admin import is_owner

router = APIRouter(prefix="/api/admin/review", tags=["Store review owner console"])
PURPOSE = "review_keys"


async def owner_console(user=Depends(c.current_user)):
    # Scope first: EVERY reviewer account (any role) gets the same answer, so the console never leaks whether a
    # sample account happens to carry the admin role. Then the production role and owner checks.
    if c.in_review():
        c.fail(403, "REVIEW_SCOPE_FORBIDDEN", "Reviewer accounts cannot manage store-review access")
    if user["role"] != "admin":
        c.fail(403, "PERMISSION_DENIED", "You do not have permission for this action")
    if not is_owner(user):
        c.fail(403, "OWNER_ADMIN_REQUIRED", "Only the owner administrator can manage store-review access")
    return user


def require_review_storage():
    if not c.review_available():
        state = c.review_status()
        c.fail(503, "REVIEW_UNAVAILABLE", f"Store-review storage is not available on this server ({state['reason']})")


async def account_table():
    with c.scoped(c.REVIEW):
        table = await review_seed.status()
    known = {row["reviewer_id"]: row for row in table["accounts"]}
    rows = []
    for role, meta in review_seed.ACCOUNTS.items():
        row = known.get(meta["reviewer_id"])
        rows.append({"reviewer_id": meta["reviewer_id"], "role": role, "role_label": review_seed.ROLE_LABELS[role],
                     "exists": row is not None, "enabled": bool(row and row.get("enabled") and not row.get("revoked_at")),
                     "created_at": row.get("created_at") if row else None, "rotated_at": row.get("rotated_at") if row else None,
                     "revoked_at": row.get("revoked_at") if row else None, "last_login_at": row.get("last_login_at") if row else None})
    return rows, table["dataset"]


@router.get("/status")
async def status(user=Depends(owner_console)):
    body = {"enabled": c.review_configured(), "usable": c.review_available(), "storage": c.REVIEW_STORAGE,
            "isolation": "application_enforced", "review_state": c.review_status(), "database": c.db.name,
            "sign_in_steps": review_seed.SIGN_IN_STEPS, "store_form_text": review_seed.STORE_FORM_TEXT,
            "fresh_authentication": "OTP to the owner's registered number, single use, 10 minutes"}
    if not c.review_available():
        return {**body, "accounts": [], "dataset": None}
    accounts, dataset = await account_table()
    return {**body, "accounts": accounts, "dataset": dataset,
            "missing_accounts": [a["reviewer_id"] for a in accounts if not a["exists"]]}


@router.post("/challenge")
async def challenge(request: Request, user=Depends(owner_console)):
    require_review_storage()
    return await start_challenge(c.phone(user["phone"]), PURPOSE, user["id"], request)


class KeyAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["provision", "rotate", "revoke", "reset_data"]
    reviewer_id: str = Field("", max_length=64)
    otp: str = Field(pattern=r"^[0-9]{4}$")
    challenge_id: str | None = None
    environment: Literal["preview", "production"] = "production"
    api_base_url: str = Field("", max_length=200)


@router.post("/keys")
async def keys(req: KeyAction, user=Depends(owner_console)):
    require_review_storage()
    if req.action in {"rotate", "revoke"} and review_seed.role_of(req.reviewer_id) == "unknown":
        c.fail(422, "UNKNOWN_REVIEWER", "Choose one of the four reviewer accounts")
    # Fresh authentication: the OTP challenge is bound to THIS owner record and this purpose, and is consumed here.
    await check_challenge(c.phone(user["phone"]), PURPOSE, user["id"], req.otp, req.challenge_id)
    issued, revoked, reset = {}, None, None
    async with c.lock("review-console"):
        with c.scoped(c.REVIEW):
            if req.action == "provision":
                await review_seed.seed_dataset()
                issued = await review_seed.provision_accounts()  # existing accounts and their keys are untouched
            elif req.action == "rotate":
                try:
                    issued[req.reviewer_id] = await review_seed.rotate(req.reviewer_id)
                except ValueError:
                    c.fail(404, "REVIEWER_NOT_PROVISIONED", "Provision the reviewer accounts before rotating a key")
            elif req.action == "reset_data":
                # Same as the CLI --reset-data: only the allow-listed review__ collections are emptied and reseeded; the
                # four credentials (review_accounts) keep their hashes; every review session/refresh token is gone.
                reset = await review_seed.seed_dataset(reset=True)
            else:
                try:
                    revoked = await review_seed.revoke(req.reviewer_id)
                except ValueError:
                    c.fail(404, "REVIEWER_NOT_PROVISIONED", "This reviewer account does not exist")
            await c.db.review_access_log.insert_one({"event": f"owner_console_{req.action}", "reviewer_id": req.reviewer_id or "*",
                "ip": "owner-console", "success": True, "detail": f"issued={sorted(issued)} revoked={bool(revoked)} reset={bool(reset)}", "created_at": c.stamp()})
    accounts, dataset = await account_table()
    unchanged = [a["reviewer_id"] for a in accounts if a["exists"] and a["reviewer_id"] not in issued]
    note = review_seed.note_lines(req.environment, req.api_base_url, c.db.name, issued, unchanged, None) if issued else None
    detail = ("Keys are shown once; only hashes are stored." if issued else
              "Sample data rebuilt: the four access keys are unchanged and every reviewer session was signed out." if reset else
              "No key was issued: existing accounts keep their keys. Use rotate to issue a new key.")
    return {"action": req.action, "accounts": accounts, "dataset": dataset, "revoked": revoked, "reset": reset,
            "issued": [{"reviewer_id": rid, "role": review_seed.role_of(rid), "role_label": review_seed.ROLE_LABELS[review_seed.role_of(rid)],
                        "access_key": secret} for rid, secret in issued.items()],
            "unchanged": unchanged, "note_text": "\n".join(note) if note else None, "shown_once": True, "detail": detail}
