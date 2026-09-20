"""Non-mutating configuration checks. Readiness never proves SMS delivery or a role."""
import asyncio

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from . import core as c
from . import owner_admin
from .ai_consent import AI_CONSENT_VERSION

router = APIRouter(prefix="/api", tags=["Capabilities"])
CAPABILITIES = {
    "canonical_auth": 1, "enrollment_grants": 1, "staff_directory": 1, "query_ledger": 1,
    "rates_versioning": 1, "pdf_template": 1, "legacy_units": 1, "catalog_pagination": 1,
    "pdf_authoring": 1, "pdf_source_preview": 1, "media_accounting": 1, "managed_delete": 0,
    "credential_readiness": 1, "customer_id_history": 1, "deletion_outbox_cursor": 1, "review_access": 2,
    "icon_font_fallback": 1, "owner_admin_bootstrap": 1, "review_owner_console": 1, "ai_consent": 1,
}
SECRET_KEYS = ("JWT_SECRET", "ENROLLMENT_INTEGRATION_KEY", "STAFF_SERVICE_KEY")
CONFIG_KEYS = (*SECRET_KEYS, "MSG91_AUTHKEY", "MSG91_TEMPLATE_ID", "MONGO_URL", "DB_NAME")


def configuration():
    values = {key: c.setting(key) for key in CONFIG_KEYS}  # bootstrap placeholders count as absent
    valid = {key: bool(value) for key, value in values.items()}
    for key in SECRET_KEYS:
        valid[key] = len(values[key]) >= 32
    separate = bool(values["STAFF_SERVICE_KEY"] and
                    values["STAFF_SERVICE_KEY"] != values["ENROLLMENT_INTEGRATION_KEY"])
    valid["STAFF_SERVICE_KEY"] = valid["STAFF_SERVICE_KEY"] and separate
    return valid


async def readiness():
    config = configuration()
    try:
        await asyncio.wait_for(c.db.command("ping"), timeout=2)
        database_ready = True
    except Exception:
        database_ready = False
    common = ["JWT_SECRET", "MSG91_AUTHKEY", "MSG91_TEMPLATE_ID", "MONGO_URL", "DB_NAME"]
    flows = {}
    for name, extra in (("mobile", []), ("staff", ["STAFF_SERVICE_KEY"]),
                        ("enrollment", ["ENROLLMENT_INTEGRATION_KEY"]),
                        ("deletion", ["ENROLLMENT_INTEGRATION_KEY"])):
        issues = [key for key in common + extra if not config[key]]
        if not database_ready:
            issues.append("DATABASE_UNAVAILABLE")
        flows[name] = {"ready": not issues, "issues": issues}
    # Store-review sign-in needs JWT, the database and USABLE review storage (REVIEW_ACCESS_ENABLED + initialised
    # `review__*` collections of the same database); never SMS. Isolation is application-enforced by session scope.
    review_issues = [key for key in ("JWT_SECRET", "MONGO_URL", "DB_NAME") if not config[key]]
    review_state = c.review_status()
    if not c.review_available():
        review_issues.append(review_state["reason"])
    if not database_ready:
        review_issues.append("DATABASE_UNAVAILABLE")
    accounts_enabled = None
    if c.review_available() and database_ready:
        try:
            with c.scoped(c.REVIEW):
                accounts_enabled = await asyncio.wait_for(
                    c.db.review_accounts.count_documents({"enabled": True, "revoked_at": None}), timeout=2)
        except Exception:
            accounts_enabled = None
    flows["review"] = {"ready": not review_issues, "issues": review_issues, "optional": True,
                       "enabled": c.review_configured(), "usable": c.review_available(), "storage": c.REVIEW_STORAGE,
                       "isolation": "application_enforced", "accounts_enabled": accounts_enabled, "detail": review_state["detail"]}
    # Default owner administrator (OWNER_ADMIN_PHONE): reports what the startup bootstrap did to the DATABASE
    # record in this process - configured / created / promoted / already admin / refused - never a login.
    owner = owner_admin.status()
    owner_issues = ([] if owner["applied"] else [owner["reason"]]) + ([] if database_ready else ["DATABASE_UNAVAILABLE"])
    flows["owner_admin"] = {"ready": not owner_issues, "issues": owner_issues, "state": owner["action"],
                            "phone_suffix": owner["phone_suffix"], "detail": owner["detail"]}
    # Deployed schedulers: the 03:00 Asia/Kolkata query release and the push outbox worker run inside this process
    # (database leases make them idempotent across several processes). Reported, never assumed.
    from . import notifications, queue_reset
    reset_status = None
    if database_ready:
        try:
            reset_status = await asyncio.wait_for(queue_reset.status(), timeout=2)
        except Exception:
            reset_status = None
    flows["queue_release"] = {"ready": queue_reset.state["running"] and database_ready, "optional": True,
                              "issues": [] if queue_reset.state["running"] else ["RELEASE_WORKER_NOT_RUNNING"], "status": reset_status}
    flows["push_notifications"] = {"ready": notifications.worker_state["running"] and database_ready, "optional": True,
                                   "issues": [] if notifications.worker_state["running"] else ["PUSH_WORKER_NOT_RUNNING"],
                                   "worker": notifications.worker_state, "provider": notifications.provider_status()}
    ready = all(flow["ready"] for name, flow in flows.items() if not flow.get("optional"))
    config["REVIEW_ACCESS_ENABLED"] = c.review_configured()
    config["REVIEW_STORAGE_USABLE"] = c.review_available()
    config["AI_CONSENT_VERSION"] = AI_CONSENT_VERSION
    config["OWNER_ADMIN_PHONE"] = bool(owner_admin.configured_phone())
    config["BUILD_COMMIT"] = bool(c.setting("BUILD_COMMIT"))
    return {"status": "ok" if ready else "not_ready", "ready": ready,
            "build": c.BUILD, "commit": c.setting("BUILD_COMMIT") or "unrecorded",
            "capabilities": CAPABILITIES, "configuration": config, "flows": flows,
            "database_ready": database_ready, "sms_delivery_verified": False,
            "account_role_verified": False, "key_matching_verified_by_this_check": False}


def response(body, ready):
    return JSONResponse(body, status_code=200 if ready else 503,
                        headers={"Cache-Control": "no-store"})


@router.get("/health/live")
async def live():
    """Process liveness only (never authentication readiness). Production evidence 12 Sep 2026: a build whose
    /health answered 503 was deployed and served, so the strict endpoints below stay truthful."""
    return response({"status": "alive", "build": c.BUILD}, True)


@router.get("/health")
@router.get("/health/ready")
async def health():
    """Strict readiness: 503 while any non-optional authentication flow is unconfigured or the database is
    unreachable. Never unconditional 200. The optional review flow is reported but never affects `ready`."""
    body = await readiness()
    return response(body, body["ready"])


async def credential_check(check, supplied, flow):
    try:
        await check(supplied)
    except HTTPException as exc:
        exc.headers = {**(exc.headers or {}), "Cache-Control": "no-store"}
        raise
    body = await readiness()
    scoped = body["flows"][flow]
    return response({"status": "ok" if scoped["ready"] else "not_ready", "flow": flow,
                     **scoped, "build": c.BUILD, "credential_verified": True,
                     "sms_delivery_verified": False, "account_role_verified": False}, scoped["ready"])


@router.get("/integrations/staff/readiness")
async def staff_readiness(x_staff_service_key: str | None = Header(None)):
    return await credential_check(c.service_key, x_staff_service_key, "staff")


@router.get("/integrations/enrollment/readiness")
async def enrollment_readiness(x_integration_key: str | None = Header(None)):
    return await credential_check(c.integration_key, x_integration_key, "enrollment")