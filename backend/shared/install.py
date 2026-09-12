from fastapi import Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from . import core as c
from .auth import router as auth
from .people import router as people
from .queries import router as queries
from .commerce import router as commerce
from .catalog import router as catalog
from .pdf_authoring import router as pdf_authoring
from .media_lifecycle import router as media_lifecycle
from .pdf_jobs import router as pdf, worker_loop
from .readiness import router as readiness
from .review import router as review
from .fonts import router as fonts


class DataScopeMiddleware:
    """Binds the request task to the data scope of its signature-verified bearer session BEFORE any
    route or dependency touches the database. Requests without a verifiable review session run in
    production scope, where review users do not exist."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        authorization = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"authorization"), None)
        with c.scoped(c.scope_of_authorization(authorization)):
            await self.app(scope, receive, send)


def install_shared(app, legacy, db, sender, put, get, review_db=None, review_blobs=None):
    c.configure(db, sender, put, get, review_database=review_db, review_blobs=review_blobs)
    app.add_middleware(DataScopeMiddleware)
    routers = [readiness, fonts, auth, review, people, queries, commerce, catalog, pdf, pdf_authoring, media_lifecycle]
    replacement_names = {
        "health", "send_otp", "verify_otp", "get_me", "update_profile", "phone_change_request", "phone_change_verify",
        "delete_account_request", "delete_account_confirm", "integration_upsert_enrollment", "integration_get_customer",
        "integration_delete_customer", "create_executive", "list_executives", "update_executive", "disable_executive",
        "executive_performance", "list_customers", "get_customer", "update_customer", "create_request", "my_requests",
        "list_requests", "update_request", "get_request_history", "update_product", "serve_file", "get_latest_rates",
        "update_rates", "create_rate_slab", "update_rate_slab", "delete_rate_slab", "seed_data", "seed_expand",
        "pdf_upload_init", "pdf_upload_chunk", "pdf_upload_complete", "pdf_upload_status", "import_pdf_to_batch",
        "list_products", "create_product", "get_rate_list", "search_customers",
    }
    legacy.routes[:] = [r for r in legacy.routes if r.name not in replacement_names]
    for router in routers:
        app.include_router(router)
    app.include_router(legacy)
    from .openapi_contract import install_openapi
    install_openapi(app)

    @app.get("/api/openapi.json", include_in_schema=False)
    async def public_contract():
        return app.openapi()

    @app.get("/", include_in_schema=False)
    @app.get("/api", include_in_schema=False)
    @app.get("/api/", include_in_schema=False)
    async def root_liveness():
        # Process liveness for platform probes that hit the service root; readiness lives at /api/health/ready.
        return JSONResponse({"status": "alive", "build": c.BUILD, "report": "/api/health", "strict_readiness": "/api/health/ready"},
                            headers={"Cache-Control": "no-store"})

    @app.on_event("startup")
    async def start_worker():
        import asyncio
        from .people import deletion_retry_loop
        # Optional review storage: prove it or disable it for this process. A review database the deployment's
        # Mongo user may not touch (authorisation failure) must never crash startup or reach production data;
        # workers only iterate scopes that are actually usable. Primary-database failures are NOT absorbed here
        # (they surface from the primary ensure_indexes() at startup as before).
        await c.initialize_review()
        app.state.pdf_worker = asyncio.create_task(worker_loop())
        app.state.deletion_worker = asyncio.create_task(deletion_retry_loop())

    @app.on_event("shutdown")
    async def stop_worker():
        import asyncio
        app.state.pdf_worker.cancel()
        app.state.deletion_worker.cancel()
        try:
            await app.state.pdf_worker
        except asyncio.CancelledError:
            pass
        try:
            await app.state.deletion_worker
        except asyncio.CancelledError:
            pass

    @app.exception_handler(HTTPException)
    async def error_handler(request, exc):
        body = exc.detail if isinstance(exc.detail, dict) else {"code": f"HTTP_{exc.status_code}", "detail": str(exc.detail)}
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        # Never echo OTPs, keys, tokens or complete submitted bodies from Pydantic errors.
        fields = [".".join(str(k) for k in e["loc"]) for e in exc.errors()]
        return JSONResponse({"code": "VALIDATION_ERROR", "detail": "Check the required fields", "fields": fields}, status_code=422)

    @app.exception_handler(Exception)
    async def internal_handler(request, exc):
        # Error categories, not provider payloads, stack traces, files or personal fields.
        import logging
        logging.getLogger("shared").error("Unhandled service error: %s", type(exc).__name__)
        return JSONResponse({"code": "SERVICE_ERROR", "detail": "The operation did not complete. Please retry or contact support."}, status_code=500)

    @app.post("/api/ai/reports", tags=["AI moderation"])
    async def report(body: dict, user=Depends(c.current_user)):
        message = await db.ai_chat_history.find_one({"id": body.get("message_id"), "user_id": user["id"], "role": "assistant"}, {"_id": 0})
        if not message:
            c.fail(404, "MESSAGE_NOT_FOUND", "Message does not belong to you")
        await db.ai_reports.update_one({"message_id": message["id"], "user_id": user["id"]},
            {"$setOnInsert": {"reason": str(body.get("reason", "Problematic content"))[:1000], "status": "pending", "created_at": c.stamp()}}, upsert=True)
        await db.ai_chat_history.update_one({"id": message["id"]}, {"$set": {"moderation_status": "hidden"}})
        return {"reported": True, "status": "pending_review"}

    @app.get("/api/admin/ai/reports", tags=["AI moderation"])
    async def reports(user=Depends(c.admin)):
        return {"reports": await db.ai_reports.find({"status": "pending"}, {"_id": 0}).limit(100).to_list(100)}