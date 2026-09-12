"""Non-mutating configuration checks. Readiness never proves SMS delivery or a role."""
import asyncio

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from . import core as c

router = APIRouter(prefix="/api", tags=["Capabilities"])
CAPABILITIES = {
    "canonical_auth": 1, "enrollment_grants": 1, "staff_directory": 1, "query_ledger": 1,
    "rates_versioning": 1, "pdf_template": 1, "legacy_units": 1, "catalog_pagination": 1,
    "pdf_authoring": 1, "pdf_source_preview": 1, "media_accounting": 1, "managed_delete": 0,
    "credential_readiness": 1, "customer_id_history": 1, "deletion_outbox_cursor": 1, "review_access": 1,
    "icon_font_fallback": 1,
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
    # Store-review sign-in needs JWT, the database and a DISTINCT, USABLE review database; never SMS.
    # A configured name is not proof of usability: an unauthorised/unreachable review database is reported here.
    review_issues = [key for key in ("JWT_SECRET", "MONGO_URL", "DB_NAME") if not config[key]]
    review_state = c.review_status()
    if not c.review_available():
        review_issues.append(review_state["reason"])
    if not database_ready:
        review_issues.append("DATABASE_UNAVAILABLE")
    flows["review"] = {"ready": not review_issues, "issues": review_issues, "optional": True,
                       "configured": c.review_configured(), "usable": c.review_available(), "detail": review_state["detail"]}
    ready = all(flow["ready"] for name, flow in flows.items() if name != "review")
    config["REVIEW_DB_NAME"] = c.review_configured()
    config["REVIEW_DB_USABLE"] = c.review_available()
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