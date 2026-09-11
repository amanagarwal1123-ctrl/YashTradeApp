"""Add explicit response contracts for additive dict-based legacy adapters."""
from fastapi.openapi.utils import get_openapi

from .core import BUILD


def install_openapi(app):
    def schema():
        if app.openapi_schema:
            return app.openapi_schema
        doc = get_openapi(title="Yash canonical shared API", version=BUILD, routes=app.routes,
            description="Canonical role/session authority. See YASH_SHARED_API_CONTRACT.md for migration and website cutover requirements.")
        text = {"type": "string"}
        integer = {"type": "integer"}
        def obj(properties, required=()):
            return {"type": "object", "properties": properties, "required": list(required)}
        def ref(name):
            return {"$ref": f"#/components/schemas/{name}"}
        def arr(item):
            return {"type": "array", "items": item}
        user = obj({**{k: text for k in ["id", "phone", "name", "shop_name", "location", "city", "code", "created_at", "updated_at"]},
            "role": {"type": "string", "enum": ["customer", "admin", "telecaller", "billing_executive"]},
            "account_status": {"type": "string", "enum": ["active", "inactive", "pending", "deleted"]},
            "phone_verified": {"type": "boolean"}, "has_logged_in": {"type": "boolean"},
            "step1_complete": {"type": "boolean"}, "profile_version": integer,
            **{k: {"type": ["string", "null"], "format": "date-time"} for k in ["registered_at", "verified_at", "first_mobile_login_at", "last_mobile_login_at", "last_portal_login_at", "last_login"]}}, ["id", "role", "account_status"])
        event = obj({**{k: text for k in ["id", "type", "request_id", "actor_id", "actor_role", "actor_name", "notes", "status", "timestamp"]}, "old": {}, "new": {}}, ["id", "type", "timestamp"])
        request = obj({**{k: text for k in ["id", "customer_id", "user_id", "request_type", "customer_name", "customer_phone", "customer_shop_name", "customer_location", "user_name", "user_phone", "user_city", "assignee_id", "resolver_id", "created_at", "pending_since"]},
            "status": {"type": "string", "enum": ["pending", "in_progress", "contacted", "no_response", "resolved", "cancelled"]},
            "events": arr(ref("CanonicalRequestEvent")), "version": integer, "linked_products": arr({"type": "object"}),
            "pending_seconds": {"type": ["integer", "null"]}, "handling_seconds": {"type": ["integer", "null"]}}, ["id", "status", "version"])
        pagination = {"page": integer, "limit": integer, "total": integer, "pages": integer}
        definitions = {
            "CanonicalUser": user, "CanonicalRequestEvent": event, "CanonicalRequest": request,
            "SharedError": obj({"code": text, "detail": text, "fields": arr(text)}, ["code", "detail"]),
            "CanonicalTokens": obj({"token": text, "refresh_token": text, "expires_at": text, "user": ref("CanonicalUser")}, ["token", "refresh_token", "expires_at", "user"]),
            "CanonicalRequestPage": obj({**pagination, "requests": arr(ref("CanonicalRequest")), "open_counts_by_type": {"type": "object", "additionalProperties": integer}, "server_time": text}),
            "CanonicalCustomerPage": obj({**pagination, "customers": arr(ref("CanonicalUser"))}),
            "CanonicalStaffDirectory": obj({"users": arr(ref("CanonicalUser"))}),
            "CanonicalHistory": obj({"request": ref("CanonicalRequest"), "history": arr(ref("CanonicalRequestEvent"))}),
            "ImportCommitResult": obj({**{k: integer for k in ["created", "updated", "skipped", "failed"]}, "rows": arr(obj({"row_id": text, "status": text, "reason": text, "product_id": text}))}),
            "ImportJobStatus": obj({**{k: text for k in ["upload_id", "phase", "upload_status", "sha256", "filename", "updated_at"]},
                **{k: integer for k in ["file_size", "bytes_received", "total_chunks", "pages_processed", "product_count", "version"]},
                "total_pages": {"type": ["integer", "null"]}, "received_chunk_indices": arr(integer), "limits": {"type": "object"}, "result": ref("ImportCommitResult"), "error": {"type": ["string", "null"]}}),
        }
        doc.setdefault("components", {}).setdefault("schemas", {}).update(definitions)
        response_map = {("/api/auth/me", "get"): "CanonicalUser", ("/api/auth/refresh", "post"): "CanonicalTokens",
            ("/api/auth/profile", "put"): "CanonicalUser", ("/api/requests", "get"): "CanonicalRequestPage",
            ("/api/requests/my", "get"): "CanonicalRequestPage", ("/api/requests/{rid}/history", "get"): "CanonicalHistory",
            ("/api/customers", "get"): "CanonicalCustomerPage", ("/api/integrations/staff", "get"): "CanonicalStaffDirectory",
            ("/api/pdf-upload/{jid}/status", "get"): "ImportJobStatus", ("/api/pdf-upload/{jid}/commit", "post"): "ImportCommitResult"}
        for path, operations in doc["paths"].items():
            for method, operation in operations.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                for code in ("401", "403", "409", "422", "503"):
                    operation.setdefault("responses", {})[code] = {"description": "Canonical JSON error", "content": {"application/json": {"schema": ref("SharedError")}}}
                model = response_map.get((path, method))
                if model:
                    operation["responses"]["200"] = {"description": "Canonical response", "content": {"application/json": {"schema": ref(model)}}}
        app.openapi_schema = doc
        return doc
    app.openapi = schema